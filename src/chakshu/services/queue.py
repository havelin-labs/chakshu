"""The runs table as a job queue.

Workers claim the oldest queued run with SELECT ... FOR UPDATE SKIP LOCKED, so
any number of worker processes can share it and never pick the same run.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.db.models import Run, RunStatus

# A run still "running" after this long belongs to a worker that died.
STALE_AFTER = timedelta(minutes=30)
MAX_ATTEMPTS = 3


async def claim_next(session: AsyncSession) -> uuid.UUID | None:
    run = await session.scalar(
        select(Run)
        .where(Run.status == RunStatus.QUEUED.value)
        .order_by(Run.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if run is None:
        return None
    run.status = RunStatus.RUNNING
    run.attempts += 1
    run.started_at = datetime.now(UTC)
    run.progress = "Starting"
    await session.commit()
    return run.id


async def requeue_stale(session: AsyncSession) -> int:
    result = await session.execute(
        update(Run)
        .where(Run.status == RunStatus.RUNNING.value, Run.started_at < datetime.now(UTC) - STALE_AFTER)
        .values(status=RunStatus.QUEUED.value, progress="Requeued after the worker stopped")
    )
    await session.commit()
    return result.rowcount or 0


async def set_progress(session: AsyncSession, run: Run, text: str) -> None:
    run.progress = text
    await session.commit()
