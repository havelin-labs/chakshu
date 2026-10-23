"""The People directory, person pages, the member list sync and their privacy rules."""

import re
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from githubkit.exception import RequestError
from sqlalchemy import select

from chakshu.api import deps
from chakshu.db.models import AnalyticsAudit, Installation, JobStatus, OrgMember, Repo, Reviewer, Run, User
from chakshu.handlers import organization
from chakshu.handlers.context import Context
from chakshu.helpers import analytics as calc
from chakshu.services import analytics, members
from chakshu.services import settings_store as store
from chakshu.services.analytics import Filters
from chakshu.services.github import AppCredentials
from chakshu.services.settings_store import Key

CREDS = AppCredentials(1, "chakshu", "cid", "secret", "key", None)


@pytest.fixture
async def org(db):
    """An installed org with a repo and a reviewer. `org.run(...)` adds a run, `org.member(...)` a member."""

    class Org:
        def __init__(self):
            self.installation = Installation(
                id=uuid.uuid4(),
                github_id=11,
                account_github_id=12,
                account_login="acme",
                account_type="Organization",
            )
            self.repo = Repo(
                id=uuid.uuid4(), github_id=13, installation_id=self.installation.id, full_name="acme/api"
            )
            self.reviewer = Reviewer(
                id=uuid.uuid4(),
                installation_id=self.installation.id,
                name="default",
                owner_team="core",
                source_path="reviewers/default",
                source_sha="a" * 40,
            )

        async def setup(self):
            db.add_all([self.installation, self.repo, self.reviewer])
            await db.commit()

        async def run(self, trigger, asked, author, cost="0.10", pr=1, ago=timedelta(hours=1), repo=None):
            run = Run(
                id=uuid.uuid4(),
                work_key=uuid.uuid4(),
                repo_id=(repo or self.repo).id,
                reviewer_id=self.reviewer.id,
                pr_number=pr,
                head_sha="b" * 40,
                reviewer_sha="a" * 40,
                trigger=trigger,
                requested_by=asked,
                pr_author=author,
                cost_usd=Decimal(cost),
                status=JobStatus.SUCCEEDED,
                created_at=datetime.now(UTC) - ago,
            )
            db.add(run)
            await db.commit()
            return run

        async def member(self, login, role="member", name=None, in_org=True):
            db.add(
                OrgMember(
                    login=login,
                    login_lower=login.lower(),
                    name=name,
                    org_role=role,
                    in_org=in_org,
                    synced_at=datetime.now(UTC),
                )
            )
            await db.commit()

    result = Org()
    await result.setup()
    return result


@pytest.fixture
async def as_user(client):
    app = client._transport.app

    def sign_in(login: str, admin: bool) -> httpx.AsyncClient:
        user = User(id=uuid.uuid4(), github_id=1, login=login, is_admin=admin)
        app.dependency_overrides[deps.optional_user] = lambda: user
        return client

    yield sign_in
    app.dependency_overrides.clear()


async def _csrf(client: httpx.AsyncClient) -> dict:
    return {"X-CSRF-Token": (await client.get("/api/session")).json()["csrf_token"]}


async def _k(db, value: int) -> None:
    await store.put(db, Key.ANALYTICS_MIN_GROUP, str(value))
    await db.commit()


async def _usage(org):
    """alice and bob ask for reviews of carol's PRs, dave's PR gets an automatic one, erin does nothing."""
    for login, role in [("alice", "owner"), ("bob", "member"), ("carol", "member"), ("dave", "member")]:
        await org.member(login, role)
    await org.member("Erin", name="Erin Example")
    await org.run("mention", "alice", "carol", "0.40", pr=1)
    await org.run("portal", "bob", "carol", "0.20", pr=2)
    await org.run("auto", None, "dave", "0.10", pr=3)
    await org.run("mention", "outsider", "carol", "0.05", pr=4)  # left the org, or never in it


async def test_directory_lists_every_member_and_keeps_outsiders_apart(db, org, as_user):
    await _usage(org)
    await _k(db, 1)
    admin = as_user("alice", admin=True)

    result = (await admin.get("/api/analytics/people")).json()
    assert result["hidden"] is False and result["min_group"] == 1
    assert [r["login"] for r in result["rows"]] == ["alice", "bob", "carol", "dave", "Erin"]
    erin = result["rows"][-1]
    assert erin["activity_state"] == "none" and erin["last_activity_at"] is None and erin["requested"] == 0
    assert result["counts"] == {"all": 5, "engaged": 2, "auto_only": 2, "none": 1, "not_in_org": 1}
    assert result["rows"][0]["org_role"] == "owner" and result["rows"][3]["activity_state"] == "auto_only"

    outsiders = (await admin.get("/api/analytics/people?activity=not_in_org")).json()["rows"]
    assert [(r["login"], r["in_org"], r["org_role"]) for r in outsiders] == [("outsider", False, None)]

    owners = (await admin.get("/api/analytics/people?role=owner")).json()
    assert [r["login"] for r in owners["rows"]] == ["alice"]
    found = (await admin.get("/api/analytics/people?q=example")).json()
    assert [r["login"] for r in found["rows"]] == ["Erin"]


async def test_directory_numbers_match_the_ledger(db, org, as_user):
    await _usage(org)
    await _k(db, 1)
    before = {r["login"]: r for r in await analytics.people(db, Filters.last(30))}
    rows = (await as_user("alice", admin=True).get("/api/analytics/people")).json()["rows"]
    for row in rows:
        if row["login"] in before:
            old = before[row["login"]]
            for field in ("requested", "prs_reviewed", "auto_reviews", "engaged", "cost_triggered"):
                assert row[field] == old[field], (row["login"], field)
    carol = next(r for r in rows if r["login"] == "carol")
    assert carol["prs_reviewed"] == 3 and carol["requested"] == 0


async def test_sorting_ties_and_paging(db, org, as_user):
    for login in ["zed", "Amy", "bea", "amy2"]:
        await org.member(login, name="Same Name" if login != "zed" else None)
    await org.run("mention", "bea", "zed", pr=1)
    await org.run("mention", "bea", "zed", pr=2)
    await org.run("mention", "zed", "zed", pr=3)
    await _k(db, 1)
    admin = as_user("bea", admin=True)

    by_name = (await admin.get("/api/analytics/people")).json()["rows"]
    assert [r["login"] for r in by_name] == ["Amy", "amy2", "bea", "zed"]  # same name: login breaks the tie
    by_requests = (await admin.get("/api/analytics/people?sort=requested")).json()["rows"]
    assert [r["login"] for r in by_requests] == ["bea", "zed", "Amy", "amy2"]  # desc by default
    by_last = (await admin.get("/api/analytics/people?sort=last_activity&order=asc")).json()["rows"]
    assert [r["login"] for r in by_last][2:] == ["Amy", "amy2"]  # never active: last, either way

    paged = (await admin.get("/api/analytics/people?page=2&page_size=24")).json()
    assert paged["total"] == 4 and paged["rows"] == [] and paged["page"] == 2
    assert (await admin.get("/api/analytics/people?page_size=10")).status_code == 422


async def test_small_groups_are_hidden_unless_turned_off(db, org, as_user):
    await _usage(org)  # alice, bob, carol, dave and outsider are active: 5
    await org.run("mention", "outsider", "outsider", pr=9, ago=timedelta(days=60))
    admin = as_user("alice", admin=True)
    await _k(db, 5)
    assert (await admin.get("/api/analytics/people")).json()["hidden"] is False
    await _k(db, 100)
    hidden = (await admin.get("/api/analytics/people")).json()
    assert hidden["hidden_reason"] == "small_group" and hidden["rows"] == [] and hidden["counts"] is None
    page = (await admin.get("/api/analytics/people/carol")).json()
    assert (
        page["hidden_reason"] == "small_group" and "totals" not in page and page["person"]["login"] == "carol"
    )
    await _k(db, 1)
    assert (await admin.get("/api/analytics/people?days=7&trigger=auto")).json()["hidden"] is False


async def test_four_active_people_are_hidden_at_five(db, org, as_user):
    await _usage(org)
    await _k(db, 5)
    result = (await as_user("alice", admin=True).get("/api/analytics/people?trigger=mention")).json()
    assert result["hidden_reason"] == "small_group"  # alice, carol and outsider


@pytest.mark.parametrize(
    ("value", "status"), [(0, 422), (2, 422), (101, 422), (1, 200), (3, 200), (100, 200)]
)
async def test_group_size_setting_is_one_or_three_to_a_hundred(db, as_user, value, status):
    admin = as_user("alice", admin=True)
    response = await admin.patch(
        "/api/settings/analytics", json={"min_group": value}, headers=await _csrf(admin)
    )
    assert response.status_code == status
    if status == 422:
        assert "from 3 to 100" in response.text


async def test_settings_changes_are_audited(db, client, as_user):
    admin = as_user("alice", admin=True)
    response = await admin.patch(
        "/api/settings/analytics", json={"show_names": False}, headers=await _csrf(admin)
    )
    assert response.json() == {"show_names": False, "min_group": 5}
    row = (await db.scalars(select(AnalyticsAudit))).one()
    assert row.action == "settings.analytics.update"
    assert row.filters == {
        "old": {"show_names": True, "min_group": 5},
        "new": {"show_names": False, "min_group": 5},
    }
    member = as_user("bob", admin=False)
    assert (
        await member.patch("/api/settings/analytics", json={}, headers=await _csrf(member))
    ).status_code == 403


async def test_names_off_hides_others_but_not_yourself(db, org, as_user):
    await _usage(org)
    await _k(db, 1)
    await store.put(db, Key.ANALYTICS_SHOW_NAMES, "false")
    await db.commit()
    admin = as_user("alice", admin=True)
    assert (await admin.get("/api/analytics/people")).json()["hidden_reason"] == "names_off"
    other = (await admin.get("/api/analytics/people/carol")).json()
    assert other["hidden"] is True and "person" not in other
    activity = (await admin.get("/api/analytics/people/carol/activity")).json()
    assert activity["hidden_reason"] == "names_off" and activity["items"] == []
    own = await admin.get("/api/analytics/people/alice")
    assert own.status_code == 200 and own.json()["is_self"] is True and own.json()["totals"]["requested"] == 1


async def test_members_see_only_themselves(db, org, as_user):
    await _usage(org)
    member = as_user("carol", admin=False)
    assert (await member.get("/api/analytics/people")).status_code == 403
    assert (await member.get("/api/analytics/people.csv")).status_code == 403
    assert (await member.get("/api/analytics/people/alice")).status_code == 403
    assert (await member.get("/api/analytics/people/alice/activity")).status_code == 403
    own = (await member.get("/api/analytics/people/Carol")).json()
    assert own["is_self"] is True and own["canonical_login"] == "carol"
    assert own["totals"]["prs_reviewed"] == 3
    assert (await member.get("/api/analytics/me")).json()["row"]["prs_reviewed"] == 3


async def test_person_page_totals_breakdowns_and_daily(db, org, as_user):
    await org.member("MonaLisa", "owner", name="Mona Lisa")
    await org.run("mention", "monalisa", "monalisa", "1.00", pr=1)
    await org.run("reply", "MonaLisa", "carol", "0.50", pr=2)
    await org.run("auto", None, "monalisa", "0.25", pr=3)
    await org.run("mention", "monalisa", "carol", "0.75", pr=4, ago=timedelta(days=40))  # previous period
    await _k(db, 1)
    admin = as_user("alice", admin=True)

    page = (await admin.get("/api/analytics/people/monalisa?days=30")).json()
    assert page["canonical_login"] == "MonaLisa" and page["is_self"] is False
    assert page["person"]["name"] == "Mona Lisa" and page["person"]["github_url"].endswith("/MonaLisa")
    assert page["person"]["activity_state"] == "engaged"
    assert page["person"]["first_activity_at"] < page["person"]["last_activity_at"]
    assert page["totals"] == {
        "requested": 2,
        "prs_reviewed": 2,
        "auto_reviews": 1,
        "replies": 1,
        "self_requested_on_own_prs": 1,
        "cost_triggered": 1.5,
        "cost_on_own_prs": 1.25,
    }
    assert page["previous_totals"]["requested"] == 1 and page["previous_totals"]["cost_triggered"] == 0.75
    assert {r["trigger"]: r["runs"] for r in page["by_trigger"]} == {"mention": 1, "reply": 1, "auto": 1}
    assert page["by_repo"] == [
        {"repo_id": str(org.repo.id), "repo": "acme/api", "prs": 3, "runs": 3, "cost_usd": 1.75}
    ]
    assert page["by_reviewer"][0]["reviewer"] == "default"
    assert len(page["daily"]) == 30 and page["daily"][-1]["day"] == datetime.now(UTC).date().isoformat()
    assert sum(d["requested"] for d in page["daily"]) == 2
    assert sum(d["own_prs_reviewed"] for d in page["daily"]) == 2
    assert len((await admin.get("/api/analytics/people/monalisa?days=7")).json()["daily"]) == 7


async def test_by_repo_keeps_nine_and_adds_up_the_rest(db, org, as_user):
    await org.member("mona")
    for n in range(12):
        repo = Repo(
            id=uuid.uuid4(), github_id=100 + n, installation_id=org.installation.id, full_name=f"acme/r{n:02}"
        )
        db.add(repo)
        await db.commit()
        for _ in range(12 - n):  # r00 has the most runs
            await org.run("mention", "mona", "x", pr=n, repo=repo)
    await _k(db, 1)
    page = (await as_user("alice", admin=True).get("/api/analytics/people/mona")).json()
    assert len(page["by_repo"]) == 10
    assert [r["repo"] for r in page["by_repo"][:2]] == ["acme/r00", "acme/r01"]
    assert page["by_repo"][-1] == {"repo": "Other", "repo_id": None, "runs": 6, "prs": 3, "cost_usd": 0.6}


async def test_activity_pages_without_duplicates(db, org, as_user):
    await org.member("mona")
    made = [await org.run("mention", "mona", "carol", pr=n, ago=timedelta(minutes=n % 3)) for n in range(7)]
    await org.run("auto", None, "mona", pr=50)
    await _k(db, 1)
    admin = as_user("alice", admin=True)
    seen, cursor = [], None
    while True:
        query = "limit=3" + (f"&cursor={cursor}" if cursor else "")
        page = (await admin.get(f"/api/analytics/people/mona/activity?{query}")).json()
        seen += page["items"]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert len(seen) == 8 and len({i["run_id"] for i in seen}) == 8
    assert {i["run_id"] for i in seen} >= {str(r.id) for r in made}
    assert [i["created_at"] for i in seen] == sorted((i["created_at"] for i in seen), reverse=True)
    assert {i["role"] for i in seen} == {"requested", "author"}
    assert (await admin.get("/api/analytics/people/mona/activity?cursor=nope")).status_code == 422


async def test_unknown_people_are_not_found(db, org, as_user):
    response = await as_user("alice", admin=True).get("/api/analytics/people/octocat")
    assert response.status_code == 404
    assert "No one with the login octocat" in response.json()["detail"]


async def test_every_view_of_someone_else_is_audited_and_self_views_are_not(db, org, as_user):
    await _usage(org)
    await _k(db, 1)
    admin = as_user("alice", admin=True)
    await admin.get("/api/analytics/people")
    await admin.get("/api/analytics/people/carol")
    await admin.get("/api/analytics/people/carol/activity")
    await admin.get("/api/analytics/people.csv?role=member")
    await admin.get("/api/analytics/people/alice")
    await admin.get("/api/analytics/people/alice/activity")
    rows = (await db.scalars(select(AnalyticsAudit).order_by(AnalyticsAudit.created_at))).all()
    assert [(r.user_login, r.action, r.target_login) for r in rows] == [
        ("alice", "people.directory.view", None),
        ("alice", "people.detail.view", "carol"),
        ("alice", "people.activity.view", "carol"),
        ("alice", "people.export", None),
    ]
    assert rows[-1].filters["role"] == "member"


async def test_export_has_the_new_columns(db, org, as_user):
    await _usage(org)
    await _k(db, 1)
    export = await as_user("alice", admin=True).get("/api/analytics/people.csv")
    lines = export.text.splitlines()
    assert lines[0].startswith("# Chakshu usage per person")
    assert lines[1] == (
        "login,name,org_role,in_org,activity_state,requested,prs_reviewed,auto_reviews,engaged,"
        "cost_triggered,last_activity_at"
    )
    assert len(lines) == 2 + 5


FORBIDDEN = re.compile("finding|accept|severity|rank|score")


def _keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _keys(v)}
    return set()


async def test_person_responses_carry_no_quality_metrics(db, org, as_user):
    await _usage(org)
    await _k(db, 1)
    admin = as_user("alice", admin=True)
    for path in (
        "/api/analytics/people",
        "/api/analytics/people/carol",
        "/api/analytics/people/carol/activity",
    ):
        keys = _keys((await admin.get(path)).json())
        assert keys and not {k for k in keys if FORBIDDEN.search(k)}, path


async def test_sync_replaces_the_list_and_keeps_it_when_github_fails(db, org, monkeypatch):
    await org.member("gone")
    db.add(User(id=uuid.uuid4(), github_id=5, login="Bob", name="Bob Builder"))
    await db.commit()
    asked: list[str] = []

    async def fetch_org(creds, installation_id, name):
        assert (installation_id, name) == (11, "acme")
        return [members.Member("Alice", "https://a", "owner"), members.Member("bob", None, "member")]

    async def fetch_name(creds, installation_id, login):
        asked.append(login)
        return "Alice A."

    monkeypatch.setattr(members, "fetch_org", fetch_org)
    monkeypatch.setattr(members, "fetch_name", fetch_name)
    source = await members.sync(db, CREDS)
    assert source["stale"] is False and source["synced_at"]
    rows = {
        m.login: m for m in (await db.scalars(select(OrgMember).execution_options(populate_existing=True)))
    }
    assert set(rows) == {"Alice", "bob", "gone"}
    assert (
        rows["Alice"].org_role == "owner"
        and rows["Alice"].name == "Alice A."
        and rows["gone"].in_org is False
    )
    assert asked == ["Alice"]  # bob already has a name from signing in

    source = await members.sync(db, CREDS)
    assert asked == ["Alice"]  # names are looked up at most daily

    async def broken(creds, installation_id, name):
        raise RequestError(Exception("network down"))

    monkeypatch.setattr(members, "fetch_org", broken)
    failed = await members.sync(db, CREDS)
    assert failed == {"synced_at": source["synced_at"], "stale": True}
    db.expire_all()
    assert len((await db.scalars(select(OrgMember).where(OrgMember.in_org.is_(True)))).all()) == 2


async def test_refresh_button_reports_the_members_source(db, org, as_user, monkeypatch):
    async def fake_sync(session, creds):
        return {"synced_at": "2026-10-23T09:15:00+00:00", "stale": False}

    monkeypatch.setattr(members, "sync", fake_sync)

    async def creds(session):
        return CREDS

    from chakshu.services import github

    monkeypatch.setattr(github, "load_credentials", creds)
    admin = as_user("alice", admin=True)
    response = await admin.post("/api/analytics/people/refresh", headers=await _csrf(admin))
    assert response.json()["members_source"]["stale"] is False


async def test_member_webhooks_add_and_remove_people(db, org):
    ctx = Context(db, CREDS, "delivery")
    user = {"login": "NewPerson", "avatar_url": "https://avatar"}
    await organization.handle(ctx, {"action": "member_added", "membership": {"role": "admin", "user": user}})
    await db.commit()
    member = await db.get(OrgMember, "NewPerson")
    assert member.in_org and member.org_role == "owner"

    await organization.handle(
        ctx, {"action": "member_removed", "membership": {"role": "admin", "user": user}}
    )
    await db.commit()
    assert (await db.get(OrgMember, "NewPerson", populate_existing=True)).in_org is False
    await organization.handle(ctx, {"action": "member_invited", "invitation": {"login": "someone"}})
    assert (await db.scalars(select(OrgMember))).all() == [member]


def test_helpers_for_the_directory():
    assert calc.activity_state(1, 0) == "engaged"
    assert calc.activity_state(0, 2) == "auto_only"
    assert calc.activity_state(0, 0) == "none"
    assert [calc.valid_min_group(n) for n in (0, 1, 2, 3, 100, 101)] == [
        False,
        True,
        False,
        True,
        True,
        False,
    ]
    when, run_id = datetime(2026, 10, 23, 9, tzinfo=UTC), uuid.uuid4()
    assert calc.decode_cursor(calc.encode_cursor(when, run_id)) == (when, run_id)
    with pytest.raises(ValueError):
        calc.decode_cursor("not-a-cursor")
    days = calc.last_days(datetime(2026, 10, 23, 1, tzinfo=UTC), 3)
    assert [d.isoformat() for d in days] == ["2026-10-21", "2026-10-22", "2026-10-23"]
