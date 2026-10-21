"""Insert-or-update for any table.

Deterministic IDs mean the same GitHub object always maps to the same primary
key, so syncing is just "upsert everything we saw". Columns not passed in are
left alone on update (for example a repo's `enabled` flag set in the portal).
"""

from typing import Any

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.db.base import Base


async def upsert(
    session: AsyncSession, model: type[Base], rows: dict[str, Any] | list[dict[str, Any]], *, key: str = "id"
) -> None:
    rows = [rows] if isinstance(rows, dict) else rows
    if not rows:
        return
    stmt = insert(model).values(rows)
    updates = {column: stmt.excluded[column] for column in rows[0] if column != key}
    if "updated_at" in model.__table__.c:
        updates["updated_at"] = func.now()
    stmt = (
        stmt.on_conflict_do_update(index_elements=[key], set_=updates)
        if updates
        else stmt.on_conflict_do_nothing(index_elements=[key])
    )
    await session.execute(stmt)
