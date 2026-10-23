import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select

from chakshu.api import deps
from chakshu.db.models import AnalyticsAudit, JobStatus, PostedFinding, Run
from chakshu.helpers import analytics as calc
from chakshu.helpers.findings import Finding, Identified
from chakshu.services import analytics, finding_stats
from chakshu.services import settings_store as store
from chakshu.services.analytics import Filters
from chakshu.services.settings_store import Key


def test_rates_leave_open_findings_out():
    assert calc.fix_rate(3, 1) == 0.75
    assert calc.dismissed_rate(3, 1) == 0.25
    assert calc.fix_rate(0, 0) is None
    assert calc.per_unit(Decimal("1.50"), 3) == 0.5
    assert calc.per_unit(2, 0) is None


def test_change_against_the_previous_period():
    assert calc.change(15, 10) == 0.5
    assert calc.change(5, 0) is None  # no honest percentage from zero
    assert calc.change(None, 3) is None


@pytest.mark.parametrize(("people", "k", "shown"), [(0, 5, True), (4, 5, False), (5, 5, True), (2, 1, False)])
def test_small_groups_are_hidden_and_the_floor_is_three(people, k, shown):
    assert calc.visible(people, k) is shown


def test_forecast_projects_the_month_and_the_day_the_cap_is_hit():
    result = calc.forecast(spent=10.0, cap=30.0, today=date(2026, 10, 10))
    assert result.projected == 31.0  # $1 a day over 31 days
    assert result.cap_hit_on == date(2026, 10, 31)
    assert calc.forecast(10.0, cap=100.0, today=date(2026, 10, 10)).cap_hit_on is None  # not this month
    assert calc.forecast(40.0, cap=30.0, today=date(2026, 10, 10)).cap_hit_on == date(2026, 10, 10)


def test_csv_keeps_column_order_and_drops_extras():
    text = calc.to_csv([{"b": 2, "a": 1, "x": 9}], ["a", "b"])
    assert text == "a,b\n1,2\n"


async def _seed(db, seed_runs) -> list[uuid.UUID]:
    """Three runs: two reviews asked for by alice and bob on carol's PRs, one automatic on dave's."""
    ids = await seed_runs(3)
    details = [
        ("mention", "alice", "carol", Decimal("0.40")),
        ("portal", "bob", "carol", Decimal("0.20")),
        ("auto", None, "dave", Decimal("0.10")),
    ]
    for run_id, (trigger, asked, author, cost) in zip(ids, details, strict=True):
        run = await db.get(Run, run_id)
        run.trigger, run.requested_by, run.pr_author, run.cost_usd = trigger, asked, author, cost
        run.status = JobStatus.SUCCEEDED
    await db.commit()
    first = await db.get(Run, ids[0])
    items = [
        Identified(Finding("a.py", n, "high", "bug", f"t{n}", "b", skill="money"), uuid.uuid4())
        for n in range(3)
    ]
    await finding_stats.record_posted(db, first, items)
    await finding_stats.record_outcomes(db, fixed={str(items[0].id)}, dismissed={str(items[1].id)})
    await db.commit()
    return ids


async def test_totals_and_breakdowns(db, seed_runs):
    await _seed(db, seed_runs)
    f = Filters.last(30)

    totals = await analytics.totals(db, f)
    assert (totals["reviews"], totals["prs"], totals["engaged"]) == (3, 3, 2)
    assert totals["spend"] == 0.7
    assert (totals["posted"], totals["fixed"], totals["dismissed"], totals["open"]) == (3, 1, 1, 1)
    assert totals["fix_rate"] == 0.5
    assert totals["cost_per_fixed"] == 0.7

    by_trigger = {r["key"]: r for r in await analytics.breakdown(db, f, "trigger")}
    assert by_trigger["mention"]["posted"] == 3 and by_trigger["auto"]["posted"] == 0
    assert [r["key"] for r in await analytics.breakdown(db, f, "skill")] == ["money"]
    assert (await analytics.breakdown(db, f, "repo"))[0]["key"] == "acme/api"

    overview = await analytics.overview(db, f)
    assert overview["tiles"]["reviews"] == {"value": 3, "previous": 0, "change": None}
    assert len(overview["daily"]) == 31 and sum(d["reviews"] for d in overview["daily"]) == 3


async def test_people_are_a_usage_ledger_sorted_by_name(db, seed_runs):
    await _seed(db, seed_runs)
    rows = await analytics.people(db, Filters.last(30))
    assert [r["login"] for r in rows] == ["alice", "bob", "carol", "dave"]
    carol = rows[2]
    assert carol["prs_reviewed"] == 2 and carol["requested"] == 0 and carol["engaged"] is False
    assert rows[0]["cost_triggered"] == 0.4
    assert "posted" not in carol and "fixed" not in carol  # never findings per author
    assert [r["login"] for r in await analytics.people(db, Filters.last(30), login="dave")] == ["dave"]


@pytest.fixture
async def as_user(client):
    """Sign the test client in as someone, admin or not."""
    from chakshu.db.models import User

    app = client._transport.app

    def sign_in(login: str, admin: bool) -> httpx.AsyncClient:
        user = User(id=uuid.uuid4(), github_id=1, login=login, is_admin=admin)
        app.dependency_overrides[deps.optional_user] = lambda: user
        return client

    yield sign_in
    app.dependency_overrides.clear()


async def test_org_views_are_for_admins_and_self_view_is_for_everyone(db, seed_runs, as_user):
    await _seed(db, seed_runs)
    member = as_user("carol", admin=False)
    assert (await member.get("/api/analytics/overview")).status_code == 403
    assert (await member.get("/api/analytics/people")).status_code == 403
    me = (await member.get("/api/analytics/me")).json()["row"]
    assert me["login"] == "carol" and me["prs_reviewed"] == 2


async def test_people_view_respects_names_switch_group_size_and_is_audited(db, seed_runs, as_user):
    await _seed(db, seed_runs)
    admin = as_user("owner", admin=True)

    hidden = (await admin.get("/api/analytics/people")).json()  # 4 people, default k = 5
    assert hidden["hidden"] == "small_group" and hidden["rows"] == []

    await store.put(db, Key.ANALYTICS_MIN_GROUP, "3")
    await db.commit()
    shown = (await admin.get("/api/analytics/people?days=7")).json()
    assert shown["hidden"] is None and len(shown["rows"]) == 4
    export = await admin.get("/api/analytics/people.csv")
    assert export.status_code == 200 and export.text.startswith("# Chakshu usage per person")

    audit = (await db.scalars(select(AnalyticsAudit).order_by(AnalyticsAudit.created_at))).all()
    assert [(a.user_login, a.action, a.view) for a in audit] == [
        ("owner", "view", "people"),
        ("owner", "export", "people"),
    ]

    await store.put(db, Key.ANALYTICS_SHOW_NAMES, "false")
    await db.commit()
    assert (await admin.get("/api/analytics/people")).json()["hidden"] == "names_off"


async def test_findings_drill_down_and_cost(db, seed_runs, as_user):
    await _seed(db, seed_runs)
    admin = as_user("owner", admin=True)
    found = (await admin.get("/api/analytics/findings?outcome=fixed")).json()
    assert len(found) == 1 and found[0]["outcome_source"] == "code_change"
    cost = (await admin.get("/api/analytics/cost")).json()
    assert cost["forecast"]["month_to_date"] == pytest.approx(0.7)
    assert set(cost["by"]) == {"repo", "reviewer", "model", "trigger"}
    rows = (await db.scalars(select(PostedFinding))).all()
    assert len(rows) == 3


def test_previous_period_has_the_same_length():
    f = Filters(start=datetime(2026, 10, 1, tzinfo=UTC), end=datetime(2026, 10, 11, tzinfo=UTC))
    before = f.previous()
    assert before.end == f.start and before.end - before.start == timedelta(days=10)
