import asyncio
from datetime import UTC, datetime, timedelta

from chakshu.db.models import JobStatus, Run
from chakshu.db.session import get_sessionmaker
from chakshu.services import queue


async def _claim(worker: str):
    async with get_sessionmaker()() as session:
        run = await queue.claim(session, Run, worker)
        return run.id if run else None


async def test_concurrent_workers_never_claim_the_same_run(seed_runs):
    seeded = await seed_runs(3)

    claimed = await asyncio.gather(*(_claim(f"w{n}") for n in range(5)))

    got = [c for c in claimed if c is not None]
    assert sorted(got) == sorted(seeded)
    assert claimed.count(None) == 2


async def test_runs_without_a_heartbeat_are_requeued(db, seed_runs):
    [run_id] = await seed_runs(1)
    await queue.claim(db, Run, "dead")
    run = await db.get(Run, run_id)
    run.heartbeat_at = datetime.now(UTC) - timedelta(minutes=5)
    await db.commit()

    assert await queue.heartbeat(db, "someone-else") == 0
    assert await queue.requeue_stale(db) == 1
    await db.refresh(run)
    assert run.status == JobStatus.QUEUED and run.worker_id is None and run.attempts == 1


async def test_live_heartbeats_keep_the_run(db, seed_runs):
    await seed_runs(1)
    await queue.claim(db, Run, "alive")
    assert await queue.heartbeat(db, "alive") == 1
    assert await queue.requeue_stale(db) == 0


async def test_release_hands_back_without_using_an_attempt(db, seed_runs):
    [run_id] = await seed_runs(1)
    await queue.claim(db, Run, "stopping")

    assert await queue.release(db, "stopping") == 1
    run = await db.get(Run, run_id, populate_existing=True)
    assert run.status == JobStatus.QUEUED and run.attempts == 0
