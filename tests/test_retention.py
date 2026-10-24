import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from chakshu.api import deps
from chakshu.db.models import GithubTeam, PrEvent, Repo, Run, TeamMembership, User
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


async def test_retention_also_clears_pr_event_people_and_ended_memberships(db, seed_runs):
    (run_id,) = await seed_runs(1)
    repo = await db.get(Repo, (await db.get(Run, run_id)).repo_id)
    now = datetime.now(UTC)
    old, recent = now - timedelta(days=100), now - timedelta(days=5)
    db.add(
        GithubTeam(
            id=1, installation_id=repo.installation_id, org="acme", slug="web", name="Web", synced_at=now
        )
    )
    db.add_all(
        [
            PrEvent(id=uuid.uuid4(), repo_id=repo.id, pr_number=1, kind="opened", at=old, actor="alice"),
            PrEvent(id=uuid.uuid4(), repo_id=repo.id, pr_number=2, kind="opened", at=recent, actor="alice"),
            TeamMembership(id=uuid.uuid4(), team_id=1, login="alice", login_lower="alice", valid_to=old),
            TeamMembership(id=uuid.uuid4(), team_id=1, login="bob", login_lower="bob", valid_to=recent),
            TeamMembership(id=uuid.uuid4(), team_id=1, login="carol", login_lower="carol"),
        ]
    )
    await store.put(db, Key.ANALYTICS_RETENTION_DAYS, "90")
    await db.commit()
    await retention.apply(db)

    actors = {
        e.pr_number: e.actor
        for e in (await db.scalars(select(PrEvent).execution_options(populate_existing=True))).all()
    }
    assert actors == {1: None, 2: "alice"}
    kept = set((await db.scalars(select(TeamMembership.login))).all())
    assert kept == {"bob", "carol"}  # only memberships that ended before the cutoff go


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
