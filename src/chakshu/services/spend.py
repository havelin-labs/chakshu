"""Month-to-date review spend and the optional monthly cap."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.db.models import Run
from chakshu.services import settings_store as store
from chakshu.services.settings_store import Key


@dataclass(frozen=True)
class Spend:
    month_to_date: Decimal
    cap: Decimal | None

    @property
    def over_cap(self) -> bool:
        return self.cap is not None and self.month_to_date >= self.cap


def month_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def current(session: AsyncSession) -> Spend:
    total = await session.scalar(
        select(func.coalesce(func.sum(Run.cost_usd), 0)).where(Run.created_at >= month_start())
    )
    cap = await store.get(session, Key.MONTHLY_CAP_USD)
    return Spend(month_to_date=Decimal(total), cap=Decimal(cap) if cap else None)
