"""Teams and dated memberships: the sync, the webhooks, attribution at the time of the run, and privacy."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from githubkit.exception import RequestError
from sqlalchemy import select

from chakshu.api import deps
from chakshu.db.models import (
    GithubTeam,
    Installation,
    JobStatus,
    Repo,
    Reviewer,
    Run,
    TeamMembership,
    User,
)
from chakshu.handlers import team as team_handler
from chakshu.handlers.context import Context
from chakshu.services import analytics, teams
from chakshu.services import settings_store as store
from chakshu.services.analytics import Filters
from chakshu.services.github import AppCredentials
from chakshu.services.settings_store import Key
from chakshu.services.teams import Team

CREDS = AppCredentials(1, "chakshu", "cid", "secret", "key", None)


@pytest.fixture
async def org(db):
    installation = Installation(
        id=uuid.uuid4(), github_id=21, account_github_id=22, account_login="acme", account_type="Organization"
    )
    repo = Repo(id=uuid.uuid4(), github_id=23, installation_id=installation.id, full_name="acme/api")
    reviewer = Reviewer(
        id=uuid.uuid4(),
        installation_id=installation.id,
        name="default",
        owner_team="core",
        source_path="reviewers/default",
        source_sha="a" * 40,
    )
    db.add_all([installation, repo, reviewer])
    await db.commit()

    async def run(author, ago, asked=None, cost="1.00", pr=1):
        db.add(
            Run(
                id=uuid.uuid4(),
                work_key=uuid.uuid4(),
                repo_id=repo.id,
                reviewer_id=reviewer.id,
                pr_number=pr,
                head_sha="b" * 40,
                reviewer_sha="a" * 40,
                trigger="auto",
                requested_by=asked,
                pr_author=author,
                cost_usd=Decimal(cost),
                status=JobStatus.SUCCEEDED,
                created_at=datetime.now(UTC) - ago,
            )
        )
        await db.commit()

    installation.add_run = run
    return installation


def _fake(monkeypatch, listing):
    async def fetch_org(creds, installation_id, org):
        return listing()

    monkeypatch.setattr(teams, "fetch_org", fetch_org)


async def _memberships(db, login):
    rows = await db.scalars(
        select(TeamMembership).where(TeamMembership.login_lower == login).order_by(TeamMembership.team_id)
    )
    return [(m.team_id, m.valid_from is not None, m.valid_to is not None) for m in rows.all()]


async def test_sync_dates_memberships_and_closes_what_is_gone(db, org, monkeypatch):
    listing = [Team(1, "web", "Web", None, ["Mona"]), Team(2, "api", "API", None, ["hubot"])]
    _fake(monkeypatch, lambda: listing)
    await teams.sync(db, CREDS)
    # The first sync can't know when memberships began.
    assert await _memberships(db, "mona") == [(1, False, False)]

    # Mona moves from Web to API, and Web is deleted.
    listing = [Team(2, "api", "API", None, ["hubot", "mona"])]
    source = await teams.sync(db, CREDS)
    assert source["stale"] is False and source["synced_at"]
    assert await _memberships(db, "mona") == [(1, False, True), (2, True, False)]
    web = await db.get(GithubTeam, 1, populate_existing=True)
    assert web.deleted_at is not None


async def test_sync_keeps_the_last_list_when_github_fails(db, org, monkeypatch):
    _fake(monkeypatch, lambda: [Team(1, "web", "Web", None, ["mona"])])
    await teams.sync(db, CREDS)

    async def broken(*args):
        raise RequestError(Exception("down"))

    monkeypatch.setattr(teams, "fetch_org", broken)
    assert (await teams.sync(db, CREDS))["stale"] is True
    assert await _memberships(db, "mona") == [(1, False, False)]


async def test_runs_stay_with_the_team_their_author_was_in_at_the_time(db, org):
    await store.put(db, Key.ANALYTICS_MIN_GROUP, "1")
    now = datetime.now(UTC)
    db.add_all(
        [
            GithubTeam(id=1, installation_id=org.id, org="acme", slug="web", name="Web", synced_at=now),
            GithubTeam(id=2, installation_id=org.id, org="acme", slug="api", name="API", synced_at=now),
            TeamMembership(
                id=uuid.uuid4(), team_id=1, login="mona", login_lower="mona", valid_to=now - timedelta(days=5)
            ),
            TeamMembership(
                id=uuid.uuid4(),
                team_id=2,
                login="mona",
                login_lower="mona",
                valid_from=now - timedelta(days=5),
            ),
            TeamMembership(id=uuid.uuid4(), team_id=2, login="hubot", login_lower="hubot"),
        ]
    )
    await db.commit()
    await org.add_run("Mona", timedelta(days=10), cost="2.00")  # while on Web
    await org.add_run("mona", timedelta(days=1), cost="3.00", pr=2)  # after the move
    await org.add_run(
        "someone", timedelta(days=1), asked="hubot", cost="4.00", pr=3
    )  # asked by an API member

    rows = {r["key"]: r for r in await analytics.by_team(db, Filters.last(30), min_group=1)}
    assert rows["Web"]["spend"] == 2.0 and rows["Web"]["people"] == 1
    assert rows["API"]["spend"] == 7.0 and rows["API"]["people"] == 2

    on_web = await analytics.totals(db, Filters.last(30, team_id=1))
    assert on_web["reviews"] == 1 and on_web["spend"] == 2.0
    assert await analytics.team_people(db, Filters.last(30, team_id=2)) == 2


async def test_small_teams_are_hidden(db, org):
    now = datetime.now(UTC)
    db.add_all(
        [
            GithubTeam(id=1, installation_id=org.id, org="acme", slug="web", name="Web", synced_at=now),
            TeamMembership(id=uuid.uuid4(), team_id=1, login="mona", login_lower="mona"),
        ]
    )
    await db.commit()
    await org.add_run("mona", timedelta(days=1))
    (row,) = await analytics.by_team(db, Filters.last(30), min_group=5)
    assert row["hidden"] is True and "spend" not in row and "people" not in row


@pytest.fixture
def as_admin(client):
    app = client._transport.app
    app.dependency_overrides[deps.optional_user] = lambda: User(
        id=uuid.uuid4(), github_id=1, login="owner", is_admin=True
    )
    yield client
    app.dependency_overrides.clear()


async def test_team_filter_refuses_slices_under_the_minimum_group(db, org, as_admin):
    now = datetime.now(UTC)
    db.add_all(
        [
            GithubTeam(id=1, installation_id=org.id, org="acme", slug="web", name="Web", synced_at=now),
            TeamMembership(id=uuid.uuid4(), team_id=1, login="mona", login_lower="mona"),
        ]
    )
    await db.commit()
    await org.add_run("mona", timedelta(days=1))
    assert (await as_admin.get("/api/analytics/overview?team=1")).status_code == 403

    await store.put(db, Key.ANALYTICS_MIN_GROUP, "1")
    await db.commit()
    overview = await as_admin.get("/api/analytics/overview?team=1")
    assert overview.status_code == 200 and overview.json()["totals"]["reviews"] == 1
    listed = (await as_admin.get("/api/analytics/teams")).json()
    assert [r["key"] for r in listed["rows"]] == ["Web"] and listed["min_group"] == 1
    assert (await as_admin.get("/api/analytics/teams/options")).json()[0]["slug"] == "web"


async def test_webhooks_open_and_close_memberships(db, org):
    ctx = Context(db, CREDS, "delivery")
    payload_team = {"id": 7, "slug": "infra", "name": "Infra", "parent": None}
    base = {"installation": {"id": org.github_id}, "scope": "team", "team": payload_team}
    await team_handler.handle_membership(ctx, base | {"action": "added", "member": {"login": "Mona"}})
    await db.commit()
    assert await _memberships(db, "mona") == [(7, True, False)]

    await team_handler.handle_membership(ctx, base | {"action": "removed", "member": {"login": "mona"}})
    await db.commit()
    assert await _memberships(db, "mona") == [(7, True, True)]

    await team_handler.handle_team(
        ctx, {"installation": {"id": org.github_id}, "action": "deleted", "team": payload_team}
    )
    await db.commit()
    assert (await db.get(GithubTeam, 7, populate_existing=True)).deleted_at is not None
