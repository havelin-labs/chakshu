"""Read and write portal settings.

Callers name settings through the `Key` enum, so a typo is an error at import
time rather than a silently missing value. Secret keys are encrypted on write
and decrypted on read; nothing outside this module touches ciphertext.
"""

from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.core import crypto
from chakshu.db.models import Setting


class Key(StrEnum):
    SETUP_CODE = "setup.code"
    SETUP_CLAIMED = "setup.claimed"
    APP_ID = "github.app_id"
    APP_SLUG = "github.app_slug"
    APP_CLIENT_ID = "github.client_id"
    APP_CLIENT_SECRET = "github.client_secret"
    APP_PRIVATE_KEY = "github.private_key"
    APP_WEBHOOK_SECRET = "github.webhook_secret"
    APP_OWNER = "github.owner"
    REVIEWERS_REPO = "reviewers.repo"
    ANTHROPIC_API_KEY = "anthropic.api_key"
    DEFAULT_MODEL = "review.default_model"
    MAX_USD_PER_REVIEW = "review.max_usd"


SECRET_KEYS = frozenset(
    {
        Key.SETUP_CODE,
        Key.APP_CLIENT_SECRET,
        Key.APP_PRIVATE_KEY,
        Key.APP_WEBHOOK_SECRET,
        Key.ANTHROPIC_API_KEY,
    }
)

DEFAULTS: dict[Key, str] = {
    Key.REVIEWERS_REPO: "chakshu-reviewers",
    Key.DEFAULT_MODEL: "sonnet",
    Key.MAX_USD_PER_REVIEW: "2",
}


async def get(session: AsyncSession, key: Key) -> str | None:
    row = await session.get(Setting, key.value)
    if row is None:
        return DEFAULTS.get(key)
    return crypto.decrypt(row.value) if row.is_secret else row.value


async def get_many(session: AsyncSession, *keys: Key) -> dict[Key, str | None]:
    rows = (await session.scalars(select(Setting).where(Setting.key.in_([k.value for k in keys])))).all()
    found = {Key(r.key): (crypto.decrypt(r.value) if r.is_secret else r.value) for r in rows}
    return {k: found.get(k, DEFAULTS.get(k)) for k in keys}


async def put(session: AsyncSession, key: Key, value: str) -> None:
    """Insert or update one setting. The caller commits."""
    is_secret = key in SECRET_KEYS
    stored = crypto.encrypt(value) if is_secret else value
    stmt = insert(Setting).values(key=key.value, value=stored, is_secret=is_secret)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Setting.key], set_={"value": stored, "is_secret": is_secret}
    )
    await session.execute(stmt)


async def put_many(session: AsyncSession, values: dict[Key, str]) -> None:
    for key, value in values.items():
        await put(session, key, value)
