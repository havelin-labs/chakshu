"""Postgres tables as job queues: runs and webhook events.

Workers claim the oldest queued row with SELECT ... FOR UPDATE SKIP LOCKED, so
any number of worker processes can share a table and never pick the same row.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.db.models import JobStatus, Run, WebhookEvent

Job = Run | WebhookEvent

# A row still "running" after this long belongs to a worker that died.
STALE_AFTER = timedelta(minutes=30)
MAX_ATTEMPTS = 3


async def claim[J: Job](session: AsyncSession, model: type[J]) -> J | None:
    """Mark the oldest queued row running and commit. None when the queue is empty."""
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
    row.started_at = datetime.now(UTC)
    if isinstance(row, Run):
        row.progress = "Starting"
    await session.commit()
    return row


async def finish(
    session: AsyncSession, row: Job, exc: Exception | None = None, *, retry: bool = True
) -> None:
    """Record the outcome: succeeded, back in the queue for another attempt, or failed."""
    if exc is None:
        row.status, row.error = JobStatus.SUCCEEDED, None
    elif retry and row.attempts < MAX_ATTEMPTS:
        row.status, row.error = JobStatus.QUEUED, str(exc)[:2000]
    else:
        row.status, row.error = JobStatus.FAILED, str(exc)[:2000]
    if row.status != JobStatus.QUEUED:
        row.finished_at = datetime.now(UTC)
    await session.commit()


async def requeue_stale(session: AsyncSession) -> int:
    cutoff = datetime.now(UTC) - STALE_AFTER
    count = 0
    for model in (Run, WebhookEvent):
        result = await session.execute(
            update(model)
            .where(model.status == JobStatus.RUNNING.value, model.started_at < cutoff)
            .values(status=JobStatus.QUEUED.value)
        )
        count += result.rowcount or 0
    await session.commit()
    return count


async def set_progress(session: AsyncSession, run: Run, text: str) -> None:
    run.progress = text
    await session.commit()
