from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.db.models import WebhookDelivery


async def first_time(session: AsyncSession, delivery_id: str, event: str) -> bool:
    """Record a GitHub delivery ID. False if we've seen it before (a redelivery)."""
    stmt = (
        insert(WebhookDelivery)
        .values(id=delivery_id[:64], event=event[:50], received_at=datetime.now(UTC))
        .on_conflict_do_nothing(index_elements=[WebhookDelivery.id])
        .returning(WebhookDelivery.id)
    )
    return (await session.scalar(stmt)) is not None
