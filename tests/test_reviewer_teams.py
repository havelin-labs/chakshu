"""One GitHub team per reviewer, so each can be requested from a pull request's Reviewers box."""

import uuid
from types import SimpleNamespace

import httpx
import pytest
from githubkit.exception import RequestFailed
from githubkit.response import Response

from chakshu.db.models import Installation, Reviewer
from chakshu.handlers import pull_request
from chakshu.handlers.context import Context
from chakshu.helpers import mentions
from chakshu.services import github, orgs, triggers


def test_reviewer_team_names_round_trip():
    assert mentions.reviewer_team("security") == "chakshu-security"
    assert mentions.reviewer_from_team("chakshu-portal-test") == "portal-test"
    assert mentions.reviewer_from_team("chakshu") is None
    assert mentions.reviewer_from_team("platform") is None
    assert mentions.reviewer_from_team(None) is None


class FakeTeams:
    def __init__(self, children):
        self.children = children  # slug -> description
        self.created, self.deleted = [], []

    async def async_get_by_name(self, org, slug):
        return SimpleNamespace(parsed_data=SimpleNamespace(id=7, slug=slug))

    async def async_list_child_in_org(self, **kwargs):  # only used through paginate
        raise AssertionError

    async def async_create(self, org, **body):
        self.created.append(body)

    async def async_delete_in_org(self, org, slug):
        self.deleted.append(slug)


class FakeClient:
    def __init__(self, teams):
        self.rest = SimpleNamespace(teams=teams, paginate=self._paginate)
        self._teams = teams

    async def _paginate(self, fn, **kwargs):
        for slug, description in self._teams.children.items():
            yield SimpleNamespace(slug=slug, description=description)


@pytest.fixture
async def org(db):
    install = Installation(
        id=uuid.uuid4(), github_id=51, account_github_id=52, account_login="acme", account_type="Organization"
    )
    db.add(install)
    for name, errors in [("default", []), ("security", []), ("broken", ["bad yaml"])]:
        db.add(
            Reviewer(
                id=uuid.uuid4(),
                installation_id=install.id,
                name=name,
                owner_team="platform",
                source_path=f"reviewers/{name}",
                source_sha="a" * 40,
                errors=errors,
            )
        )
    await db.commit()
    return install


async def test_sync_creates_missing_teams_and_removes_only_its_own(db, org, monkeypatch):
    teams = FakeTeams(
        {
            "chakshu-default": f"Request this team to run Chakshu's default reviewer. {mentions.TEAM_MARKER}",
            "chakshu-old": f"Request this team to run Chakshu's old reviewer. {mentions.TEAM_MARKER}",
            "chakshu-ops": "A team people made by hand under chakshu.",
        }
    )
    monkeypatch.setattr(github, "installation_client", lambda creds, iid: FakeClient(teams))

    result = await orgs.sync_reviewer_teams(db, None, org)

    assert result.created == ["chakshu-security"]  # broken reviewers get no team
    assert result.kept == ["chakshu-default"]
    assert result.removed == ["chakshu-old"]  # chakshu-ops has no marker, so it stays
    assert teams.deleted == ["chakshu-old"]
    (body,) = teams.created
    assert body["parent_team_id"] == 7 and body["privacy"] == "closed"
    assert mentions.TEAM_MARKER in body["description"]


async def test_github_refusing_is_reported_not_raised(db, org, monkeypatch):
    class Refusing(FakeTeams):
        async def async_get_by_name(self, org, slug):
            request = httpx.Request("GET", "https://api.github.com/orgs/acme/teams/chakshu")
            raise RequestFailed(Response(httpx.Response(403, request=request), object))

    monkeypatch.setattr(github, "installation_client", lambda creds, iid: FakeClient(Refusing({})))
    result = await orgs.sync_reviewer_teams(db, None, org)
    assert result.error == "failed (403)" and not result.created


async def test_requesting_a_reviewer_team_runs_just_that_reviewer(db, org, monkeypatch):
    seen = {}

    async def fake_resolve(ctx, payload):
        return org, SimpleNamespace(full_name="acme/api", id=uuid.uuid4())

    async def fake_request(session, creds, request):
        seen["request"] = request
        return triggers.Outcome(queued=request.reviewers or [])

    async def no_speed(ctx, payload):
        return None

    monkeypatch.setattr(pull_request, "resolve", fake_resolve)
    monkeypatch.setattr(pull_request, "record_speed", no_speed)
    monkeypatch.setattr(triggers, "request_review", fake_request)
    payload = {
        "action": "review_requested",
        "requested_team": {"slug": "chakshu-security"},
        "sender": {"login": "mona"},
        "pull_request": {"number": 7},
    }
    await pull_request.handle(Context(db, None, "d1"), payload)
    assert seen["request"].reviewers == ["security"]
    assert seen["request"].trigger == "review_requested" and seen["request"].requester == "mona"

    seen.clear()
    payload["requested_team"] = {"slug": "platform"}  # someone else's team: not for Chakshu
    await pull_request.handle(Context(db, None, "d2"), payload)
    assert "request" not in seen


async def test_clearing_requests_covers_each_team_and_survives_errors(monkeypatch):
    calls = []

    async def remove(owner, name, number, reviewers, team_reviewers):
        calls.append(team_reviewers[0])
        if team_reviewers[0] == "chakshu":
            request = httpx.Request("DELETE", "https://api.github.com/x")
            raise RequestFailed(Response(httpx.Response(422, request=request), object))

    client = SimpleNamespace(
        rest=SimpleNamespace(pulls=SimpleNamespace(async_remove_requested_reviewers=remove))
    )
    monkeypatch.setattr(github, "installation_client", lambda creds, iid: client)
    await triggers.clear_team_request(None, 1, "acme/api", 7, teams=["chakshu-security", "chakshu"])
    assert calls == ["chakshu", "chakshu-security"]
