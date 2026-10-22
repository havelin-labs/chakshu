import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from chakshu.db.models import Installation, Repo, Reviewer, Run, RunStatus
from chakshu.db.session import get_sessionmaker
from chakshu.services import queue


async def _seed(db, count: int) -> list[uuid.UUID]:
    installation = Installation(
        id=uuid.uuid4(), github_id=1, account_github_id=2, account_login="acme", account_type="Organization"
    )
    repo = Repo(id=uuid.uuid4(), github_id=3, installation_id=installation.id, full_name="acme/api")
    reviewer = Reviewer(
        id=uuid.uuid4(),
        installation_id=installation.id,
        name="default",
        owner_team="core",
        source_path="reviewers/default",
        source_sha="a" * 40,
    )
    db.add_all([installation, repo, reviewer])
    await db.flush()
    ids = []
    for n in range(count):
        run = Run(
            id=uuid.uuid4(),
            work_key=uuid.uuid4(),
            repo_id=repo.id,
            reviewer_id=reviewer.id,
            pr_number=n + 1,
            head_sha="b" * 40,
            reviewer_sha="a" * 40,
            trigger="mention",
            status=RunStatus.QUEUED,
        )
        db.add(run)
        ids.append(run.id)
    await db.commit()
    return ids


async def _claim():
    async with get_sessionmaker()() as session:
        run = await queue.claim(session, Run)
        return run.id if run else None


async def test_concurrent_workers_never_claim_the_same_run(db):
    seeded = await _seed(db, 3)

    claimed = await asyncio.gather(*(_claim() for _ in range(5)))

    got = [c for c in claimed if c is not None]
    assert sorted(got) == sorted(seeded)
    assert claimed.count(None) == 2


async def test_stale_running_runs_are_requeued(db):
    [run_id] = await _seed(db, 1)
    await queue.claim(db, Run)
    run = await db.get(Run, run_id)
    run.started_at = datetime.now(UTC) - timedelta(hours=1)
    await db.commit()

    assert await queue.requeue_stale(db) == 1
    await db.refresh(run)
    assert run.status == RunStatus.QUEUED
    assert run.attempts == 1
