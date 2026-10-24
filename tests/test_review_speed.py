"""Review speed: recording PR milestones from webhooks and comparing reviewed with not reviewed."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from chakshu.db.models import Installation, JobStatus, PrEvent, Repo, Reviewer, Run
from chakshu.services import review_speed
from chakshu.services.analytics import Filters

PERSON = {"login": "mona", "type": "User"}


def _iso(at: datetime) -> str:
    return at.isoformat().replace("+00:00", "Z")


@pytest.fixture
async def repo(db):
    installation = Installation(
        id=uuid.uuid4(), github_id=31, account_github_id=32, account_login="acme", account_type="Organization"
    )
    repo = Repo(id=uuid.uuid4(), github_id=33, installation_id=installation.id, full_name="acme/api")
    db.add_all([installation, repo])
    await db.commit()
    return repo


async def _kinds(db, number):
    rows = await db.scalars(select(PrEvent).where(PrEvent.pr_number == number).order_by(PrEvent.kind))
    return {e.kind: e.at for e in rows.all()}


async def test_webhooks_record_the_earliest_milestones(db, repo):
    opened = datetime.now(UTC) - timedelta(hours=10)
    pr = {"number": 1, "user": PERSON, "created_at": _iso(opened), "updated_at": _iso(opened)}
    await review_speed.from_pull_request(db, repo, "opened", pr)

    def review(login, kind, hours, state="approved"):
        return {"user": {"login": login, "type": kind}, "state": state, "submitted_at": _iso(opened + hours)}

    await review_speed.from_review(db, repo, review("mona", "User", timedelta(hours=1)), pr)  # the author
    await review_speed.from_review(db, repo, review("chakshu[bot]", "Bot", timedelta(hours=1)), pr)
    await review_speed.from_review(db, repo, review("hubot", "User", timedelta(hours=2), "pending"), pr)
    await review_speed.from_review(db, repo, review("hubot", "User", timedelta(hours=4)), pr)
    await review_speed.from_review(db, repo, review("octo", "User", timedelta(hours=3), "COMMENTED"), pr)
    merged = pr | {"merged_at": _iso(opened + timedelta(hours=6))}
    await review_speed.from_pull_request(db, repo, "closed", merged)
    await db.commit()

    kinds = await _kinds(db, 1)
    assert set(kinds) == {"opened", "first_review", "merged"}
    assert kinds["first_review"] == opened + timedelta(hours=3)  # the earliest, whatever the arrival order


async def test_bot_authored_prs_are_left_out(db, repo):
    pr = {
        "number": 2,
        "user": {"login": "dependabot[bot]", "type": "Bot"},
        "created_at": _iso(datetime.now(UTC)),
    }
    await review_speed.from_pull_request(db, repo, "opened", pr)
    await db.commit()
    assert await _kinds(db, 2) == {}


async def test_cohorts_compare_reviewed_and_not_reviewed(db, repo):
    reviewer = Reviewer(
        id=uuid.uuid4(),
        installation_id=repo.installation_id,
        name="default",
        owner_team="core",
        source_path="reviewers/default",
        source_sha="a" * 40,
    )
    db.add(reviewer)
    start = datetime.now(UTC) - timedelta(days=3)
    for number, review_hours, merge_hours in [(10, 1, 4), (11, 3, 8), (20, 10, 24), (21, None, None)]:
        await review_speed.record(db, repo.id, number, "opened", start, "mona")
        if review_hours is not None:
            await review_speed.record(
                db, repo.id, number, "first_review", start + timedelta(hours=review_hours), "hubot"
            )
            await review_speed.record(
                db, repo.id, number, "merged", start + timedelta(hours=merge_hours), None
            )
    for number in (10, 11):  # Chakshu reviewed 10 and 11
        db.add(
            Run(
                id=uuid.uuid4(),
                work_key=uuid.uuid4(),
                repo_id=repo.id,
                reviewer_id=reviewer.id,
                pr_number=number,
                head_sha="b" * 40,
                reviewer_sha="a" * 40,
                trigger="auto",
                cost_usd=Decimal("0.1"),
                status=JobStatus.SUCCEEDED,
            )
        )
    await db.commit()

    (row,) = await review_speed.speed(db, Filters.last(30))
    assert row["repo"] == "acme/api"
    yes, no = row["reviewed"], row["not_reviewed"]
    assert yes["prs"] == 2 and yes["first_review"]["median_hours"] == 2.0 and yes["merge"]["n"] == 2
    assert no["prs"] == 2 and no["first_review"]["n"] == 1 and no["first_review"]["median_hours"] == 10.0
    assert yes["first_review"]["small_sample"] is True
