"""Webhook events: stored by `web`, handled by the worker."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.db.models import JobStatus, WebhookEvent

KEEP_FOR = timedelta(days=30)


async def store(session: AsyncSession, delivery_id: str, event: str, payload: dict[str, Any]) -> bool:
    """Queue a delivery. False if GitHub already delivered it (a redelivery)."""
    stmt = (
        insert(WebhookEvent)
        .values(id=delivery_id[:64], event=event[:50], payload=payload, status=JobStatus.QUEUED.value)
        .on_conflict_do_nothing(index_elements=[WebhookEvent.id])
        .returning(WebhookEvent.id)
    )
    return (await session.scalar(stmt)) is not None


async def recent_failures(session: AsyncSession, limit: int = 20) -> list[WebhookEvent]:
    return list(
        (
            await session.scalars(
                select(WebhookEvent)
                .where(WebhookEvent.status == JobStatus.FAILED.value)
                .order_by(WebhookEvent.created_at.desc())
                .limit(limit)
            )
        ).all()
    )


async def retry(session: AsyncSession, delivery_id: str) -> bool:
    event = await session.get(WebhookEvent, delivery_id)
    if event is None or event.status != JobStatus.FAILED:
        return False
    event.status, event.attempts, event.error, event.finished_at = JobStatus.QUEUED, 0, None, None
    await session.commit()
    return True


async def prune(session: AsyncSession) -> None:
    """Drop handled events after a while; the table is a queue, not an archive."""
    await session.execute(
        delete(WebhookEvent).where(
            WebhookEvent.status == JobStatus.SUCCEEDED.value,
            WebhookEvent.created_at < datetime.now(UTC) - KEEP_FOR,
        )
    )
    await session.commit()
