import uuid
from datetime import UTC, datetime, timedelta

import pytest

from chakshu.api import deps
from chakshu.db.models import Run, User
from chakshu.services import analytics, pr_authors, retention
from chakshu.services import settings_store as store
from chakshu.services.settings_store import Key


async def _runs(db, seed_runs, ages_in_days: list[int]) -> list[uuid.UUID]:
    ids = await seed_runs(len(ages_in_days))
    for run_id, age in zip(ids, ages_in_days, strict=True):
        run = await db.get(Run, run_id)
        run.requested_by, run.pr_author = "alice", "bob"
        run.created_at = datetime.now(UTC) - timedelta(days=age)
    await db.commit()
    return ids


async def test_retention_clears_people_only_on_older_runs(db, seed_runs):
    old, recent = await _runs(db, seed_runs, [100, 5])
    assert await retention.apply(db) == 0  # no retention set: keep everything

    await store.put(db, Key.ANALYTICS_RETENTION_DAYS, "90")
    await db.commit()
    assert await retention.apply(db) == 1

    old_run = await db.get(Run, old, populate_existing=True)
    recent_run = await db.get(Run, recent, populate_existing=True)
    assert (old_run.requested_by, old_run.pr_author) == (None, pr_authors.UNKNOWN)
    assert (recent_run.requested_by, recent_run.pr_author) == ("alice", "bob")
    assert old_run.cost_usd == recent_run.cost_usd  # only the person fields go
    assert await retention.apply(db) == 0  # nothing left to clear


@pytest.fixture
def as_admin(client):
    app = client._transport.app
    app.dependency_overrides[deps.optional_user] = lambda: User(
        id=uuid.uuid4(), github_id=1, login="owner", is_admin=True
    )
    yield client
    app.dependency_overrides.clear()


async def _csrf(client) -> dict:
    return {"X-CSRF-Token": (await client.get("/api/session")).json()["csrf_token"]}


async def test_retention_period_is_validated_and_zero_keeps_everything(as_admin):
    headers = await _csrf(as_admin)
    too_short = await as_admin.patch("/api/settings/analytics", json={"retention_days": 7}, headers=headers)
    assert too_short.status_code == 422
    saved = (
        await as_admin.patch("/api/settings/analytics", json={"retention_days": 180}, headers=headers)
    ).json()
    assert saved["retention_days"] == 180
    cleared = (
        await as_admin.patch("/api/settings/analytics", json={"retention_days": 0}, headers=headers)
    ).json()
    assert cleared["retention_days"] is None


async def test_works_council_mode_and_the_audit_log(db, as_admin):
    headers = await _csrf(as_admin)
    await as_admin.patch("/api/settings/analytics", json={"min_group": 1}, headers=headers)

    result = (await as_admin.post("/api/settings/analytics/works-council", headers=headers)).json()
    assert result == result | {"show_names": False, "min_group": 10, "export_people": False}
    assert (await analytics.privacy(db)).export_people is False

    export = await as_admin.get("/api/analytics/people.csv")
    assert export.status_code == 403

    log = (await as_admin.get("/api/settings/analytics/audit")).json()
    assert [row["action"] for row in log[:2]] == [
        "settings.analytics.works_council",
        "settings.analytics.update",
    ]
    assert log[0]["user"] == "owner" and log[0]["details"]["new"]["show_names"] is False
