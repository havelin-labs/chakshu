"""Postgres tables as job queues: runs and webhook events.

Workers claim the oldest queued row with SELECT ... FOR UPDATE SKIP LOCKED, so
any number of worker processes can share a table and never pick the same row.
A worker stamps the rows it holds and refreshes `heartbeat_at` while it works;
rows whose heartbeat stops are put back in the queue.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.db.models import JobStatus, Run, WebhookEvent

Job = Run | WebhookEvent
MODELS: tuple[type[Job], ...] = (Run, WebhookEvent)

HEARTBEAT_EVERY = timedelta(seconds=20)
# No heartbeat for this long means the worker holding the job is gone.
STALE_AFTER = timedelta(minutes=2)
MAX_ATTEMPTS = 3


def _now() -> datetime:
    return datetime.now(UTC)


async def claim[J: Job](session: AsyncSession, model: type[J], worker_id: str) -> J | None:
    """Mark the oldest queued row running for this worker and commit. None when empty."""
    row = await session.scalar(
        select(model)
        .where(model.status == JobStatus.QUEUED.value)
        .order_by(model.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if row is None:
        return None
    row.status = JobStatus.RUNNING
    row.attempts += 1
    row.started_at = row.heartbeat_at = _now()
    row.worker_id = worker_id
    if isinstance(row, Run):
        row.progress = "Starting"
    await session.commit()
    return row


async def finish(session: AsyncSession, row: Job, exc: Exception | None = None) -> None:
    """Record the outcome: succeeded, back in the queue for another attempt, or failed."""
    if exc is None:
        row.status, row.error = JobStatus.SUCCEEDED, None
    elif row.attempts < MAX_ATTEMPTS:
        row.status, row.error = JobStatus.QUEUED, str(exc)[:2000]
    else:
        row.status, row.error = JobStatus.FAILED, str(exc)[:2000]
    if row.status != JobStatus.QUEUED:
        row.finished_at = _now()
    await session.commit()


async def _update_running(session: AsyncSession, condition, **values) -> int:
    count = 0
    for model in MODELS:
        result = await session.execute(
            update(model).where(model.status == JobStatus.RUNNING.value, condition(model)).values(**values)
        )
        count += result.rowcount or 0
    await session.commit()
    return count


async def heartbeat(session: AsyncSession, worker_id: str) -> int:
    """Tell everyone this worker is still on the jobs it holds."""
    return await _update_running(session, lambda m: m.worker_id == worker_id, heartbeat_at=_now())


async def requeue_stale(session: AsyncSession) -> int:
    """Put back jobs whose worker stopped sending heartbeats."""
    cutoff = _now() - STALE_AFTER
    return await _update_running(
        session,
        lambda m: func.coalesce(m.heartbeat_at, m.started_at) < cutoff,
        status=JobStatus.QUEUED.value,
        worker_id=None,
    )


async def release(session: AsyncSession, worker_id: str) -> int:
    """On shutdown, hand unfinished jobs back. The interrupted attempt doesn't count."""
    count = 0
    for model in MODELS:
        result = await session.execute(
            update(model)
            .where(model.status == JobStatus.RUNNING.value, model.worker_id == worker_id)
            .values(status=JobStatus.QUEUED.value, worker_id=None, attempts=model.attempts - 1)
        )
        count += result.rowcount or 0
    await session.commit()
    return count


async def set_progress(session: AsyncSession, run: Run, text: str) -> None:
    run.progress = text
    await session.commit()
