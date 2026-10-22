from datetime import UTC, datetime, timedelta

from chakshu.db.models import JobStatus, Run
from chakshu.services import runs


async def test_last_reviewed_head_is_the_latest_success_at_another_commit(db, seed_runs):
    old, newer, failed, current = [await db.get(Run, i) for i in await seed_runs(4)]
    now = datetime.now(UTC)
    for run, sha, status, finished in [
        (old, "1" * 40, JobStatus.SUCCEEDED, now - timedelta(hours=2)),
        (newer, "2" * 40, JobStatus.SUCCEEDED, now - timedelta(hours=1)),
        (failed, "3" * 40, JobStatus.FAILED, now),
        (current, "4" * 40, JobStatus.RUNNING, None),
    ]:
        run.pr_number, run.head_sha, run.status, run.finished_at = 1, sha, status, finished
    await db.commit()

    assert await runs.last_reviewed_head(db, current) == "2" * 40


async def test_no_earlier_review_means_full_review(db, seed_runs):
    [run_id] = await seed_runs(1)
    assert await runs.last_reviewed_head(db, await db.get(Run, run_id)) is None
