"""Store connectors and build the tools a review gets from them."""

from collections.abc import Iterable

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.connectors import KINDS, ConnectorConfig, Toolset
from chakshu.core import crypto, ids
from chakshu.db.models import Connector
from chakshu.db.upsert import upsert
from chakshu.services.github import AppCredentials

NAME_PATTERN = r"^[a-z][a-z0-9-]{0,49}$"


def config(row: Connector) -> ConnectorConfig:
    return ConnectorConfig(
        name=row.name,
        kind=row.kind,
        base_url=row.base_url,
        username=row.username,
        secret=crypto.decrypt(row.secret_enc),
    )


async def list_all(session: AsyncSession) -> list[Connector]:
    return list((await session.scalars(select(Connector).order_by(Connector.name))).all())


async def get(session: AsyncSession, name: str) -> Connector | None:
    return await session.scalar(select(Connector).where(Connector.name == name))


async def save(
    session: AsyncSession,
    creds: AppCredentials,
    *,
    name: str,
    kind: str,
    base_url: str,
    username: str | None,
    secret: str | None,
    enabled: bool,
) -> None:
    """Create or update a connector. secret=None keeps the stored one."""
    values = {
        "id": ids.eid(creds.namespace, "connector", name),
        "name": name,
        "kind": kind,
        "base_url": base_url.rstrip("/"),
        "username": username,
        "enabled": enabled,
    }
    if secret is not None:
        values["secret_enc"] = crypto.encrypt(secret) if secret else None
    await upsert(session, Connector, values)


async def remove(session: AsyncSession, name: str) -> None:
    await session.execute(delete(Connector).where(Connector.name == name))


async def toolsets_for(session: AsyncSession, names: Iterable[str], pr_text: str) -> list[Toolset]:
    """Tools for the connectors a reviewer lists. Unknown, disabled or unsupported names are skipped."""
    wanted = set(names)
    if not wanted:
        return []
    rows = (
        await session.scalars(
            select(Connector).where(Connector.name.in_(wanted), Connector.enabled.is_(True))
        )
    ).all()
    return [KINDS[row.kind].build(config(row), pr_text) for row in rows if row.kind in KINDS]
