import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from chakshu.api import deps
from chakshu.db.models import FindingOutcome, JobStatus, PostedFinding, Run, User
from chakshu.helpers import analytics as calc
from chakshu.runner import engine
from chakshu.runner.protocol import Result
from chakshu.services import analytics
from chakshu.services.analytics import Filters


def test_sdk_usage_maps_to_protocol_names():
    message = SimpleNamespace(
        usage={
            "input_tokens": 1200,
            "output_tokens": 300,
            "cache_read_input_tokens": 9000,
            "cache_creation_input_tokens": 400,
        }
    )
    assert engine.usage_of(message) == {
        "input_tokens": 1200,
        "output_tokens": 300,
        "cache_read_tokens": 9000,
        "cache_write_tokens": 400,
    }
    assert engine.usage_of(SimpleNamespace(usage=None)) is None


def test_results_from_older_runners_still_parse():
    assert Result.model_validate({"summary": "ok"}).usage is None
    with_usage = Result.model_validate({"summary": "ok", "usage": {"input_tokens": 5}})
    assert with_usage.usage.input_tokens == 5 and with_usage.usage.cache_read_tokens == 0


def test_roi_values_fixes_with_the_admins_assumptions():
    result = calc.roi({"high": 2, "low": 3}, {"high": 30, "low": 5}, hourly_rate=60, spend=10)
    assert result == {"hours_saved": 1.25, "gross_value": 75.0, "net_value": 65.0}


async def _seed(db, seed_runs) -> None:
    (run_id,) = await seed_runs(1)
    run = await db.get(Run, run_id)
    run.status, run.cost_usd = JobStatus.SUCCEEDED, Decimal("0.50")
    run.input_tokens, run.output_tokens, run.cache_read_tokens, run.cache_write_tokens = 100, 20, 900, 10
    db.add(
        PostedFinding(
            id=uuid.uuid4(),
            run_id=run_id,
            reviewer_id=run.reviewer_id,
            severity="high",
            category="bug",
            outcome=FindingOutcome.FIXED,
            closed_at=datetime.now(UTC),
        )
    )
    await db.commit()


async def test_totals_carry_tokens_and_roi_uses_fixed_findings(db, seed_runs):
    await _seed(db, seed_runs)
    f = Filters.last(30)
    totals = await analytics.totals(db, f)
    assert (totals["input_tokens"], totals["output_tokens"], totals["cache_read_tokens"]) == (100, 20, 900)
    assert await analytics.fixed_by_severity(db, f) == {"high": 1}

    unset = await analytics.roi(db, f)
    assert unset["estimate"] is None  # no hourly rate yet: show the facts, no estimate


@pytest.fixture
def as_admin(client):
    app = client._transport.app
    app.dependency_overrides[deps.optional_user] = lambda: User(
        id=uuid.uuid4(), github_id=1, login="owner", is_admin=True
    )
    yield client
    app.dependency_overrides.clear()


async def test_roi_assumptions_are_validated_and_used(db, seed_runs, as_admin):
    await _seed(db, seed_runs)
    headers = {"X-CSRF-Token": (await as_admin.get("/api/session")).json()["csrf_token"]}
    bad = await as_admin.put("/api/settings/analytics/roi", json={"minutes": {"high": 9999}}, headers=headers)
    assert bad.status_code == 422
    saved = await as_admin.put(
        "/api/settings/analytics/roi", json={"minutes": {"high": 60}, "hourly_rate": 50}, headers=headers
    )
    assert saved.json()["minutes"]["high"] == 60 and saved.json()["minutes"]["low"] == 5

    roi = (await as_admin.get("/api/analytics/roi?days=30")).json()
    assert roi["fixed_by_severity"] == {"high": 1}
    assert roi["estimate"] == {"hours_saved": 1.0, "gross_value": 50.0, "net_value": 49.5}
