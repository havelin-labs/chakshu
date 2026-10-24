"""Read and write portal settings.

Callers name settings through the `Key` enum, so a typo is an error at import
time rather than a silently missing value. Secret keys are encrypted on write
and decrypted on read; nothing outside this module touches ciphertext.
"""

from enum import StrEnum

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.core import crypto
from chakshu.db.models import Setting
from chakshu.db.upsert import upsert


class Key(StrEnum):
    SETUP_CODE = "setup.code"
    APP_ID = "github.app_id"
    APP_SLUG = "github.app_slug"
    APP_CLIENT_ID = "github.client_id"
    APP_CLIENT_SECRET = "github.client_secret"
    APP_PRIVATE_KEY = "github.private_key"
    APP_WEBHOOK_SECRET = "github.webhook_secret"
    APP_OWNER = "github.owner"
    REVIEWERS_REPO = "reviewers.repo"
    ANTHROPIC_API_KEY = "anthropic.api_key"
    CLAUDE_OAUTH_TOKEN = "anthropic.oauth_token"
    DEFAULT_MODEL = "review.default_model"
    MAX_USD_PER_REVIEW = "review.max_usd"
    MONTHLY_CAP_USD = "review.monthly_cap_usd"
    ACTIONS_ACTION = "actions.action"  # owner/repo@ref of the action the workflow runs
    ACTIONS_RUNS_ON = "actions.runs_on"  # default runner labels for the workflow, e.g. "self-hosted, linux"
    ANALYTICS_SHOW_NAMES = "analytics.show_names"  # "true" or "false": name people in analytics
    ANALYTICS_MIN_GROUP = (
        "analytics.min_group"  # hide grouped numbers covering fewer people than this; 1 is off
    )
    ANALYTICS_RETENTION_DAYS = "analytics.retention_days"  # clear who asked and who authored on older runs
    ANALYTICS_EXPORT_PEOPLE = "analytics.export_people"  # "false" refuses CSV export of named people
    ANALYTICS_ROI = "analytics.roi"  # JSON: minutes saved per fixed finding by severity, and an hourly rate
    MEMBERS_SYNCED_AT = "members.synced_at"  # when the org member list last came from GitHub (ISO 8601)
    ALERTS_WEBHOOK = "alerts.webhook"  # Slack incoming webhook for spend alerts and the digest
    ALERTS_THRESHOLDS = "alerts.thresholds"  # percentages of the monthly cap, e.g. "50,80,100"
    ALERTS_DIGEST = "alerts.digest"  # "true" sends a weekly digest on Mondays
    ALERTS_SENT = "alerts.sent"  # JSON: the month and the thresholds already announced in it
    DIGEST_SENT_WEEK = "alerts.digest_week"  # ISO week of the last digest sent
    MEMBERS_STALE = "members.stale"  # "true" when the last attempt failed and the list is older than it looks
    TEAMS_SYNCED_AT = "teams.synced_at"  # when teams and memberships last came from GitHub (ISO 8601)
    TEAMS_STALE = "teams.stale"  # "true" when the last team sync failed


SECRET_KEYS = frozenset(
    {
        Key.SETUP_CODE,
        Key.APP_CLIENT_SECRET,
        Key.APP_PRIVATE_KEY,
        Key.APP_WEBHOOK_SECRET,
        Key.ANTHROPIC_API_KEY,
        Key.CLAUDE_OAUTH_TOKEN,
        Key.ALERTS_WEBHOOK,
    }
)

DEFAULTS: dict[Key, str] = {
    Key.REVIEWERS_REPO: "chakshu-reviewers",
    Key.DEFAULT_MODEL: "sonnet",
    Key.MAX_USD_PER_REVIEW: "2",
    Key.ANALYTICS_SHOW_NAMES: "true",
    Key.ANALYTICS_MIN_GROUP: "5",
    Key.ALERTS_THRESHOLDS: "50,80,100",
    Key.ALERTS_DIGEST: "true",
    Key.ANALYTICS_EXPORT_PEOPLE: "true",
}


def _decode(row: Setting) -> str | None:
    return crypto.decrypt(row.value) if row.is_secret else row.value


async def get(session: AsyncSession, key: Key) -> str | None:
    row = await session.get(Setting, key.value)
    return DEFAULTS.get(key) if row is None else _decode(row)


async def get_many(session: AsyncSession, *keys: Key) -> dict[Key, str | None]:
    rows = (await session.scalars(select(Setting).where(Setting.key.in_([k.value for k in keys])))).all()
    found = {Key(r.key): _decode(r) for r in rows}
    return {k: found.get(k, DEFAULTS.get(k)) for k in keys}


async def put(session: AsyncSession, key: Key, value: str) -> None:
    """Insert or update one setting. The caller commits."""
    is_secret = key in SECRET_KEYS
    stored = crypto.encrypt(value) if is_secret else value
    await upsert(session, Setting, {"key": key.value, "value": stored, "is_secret": is_secret}, key="key")


async def put_many(session: AsyncSession, values: dict[Key, str | None]) -> None:
    """Store several settings. A None value deletes that setting."""
    for key, value in values.items():
        if value is None:
            await delete(session, key)
        else:
            await put(session, key, value)


async def delete(session: AsyncSession, key: Key) -> None:
    await session.execute(sql_delete(Setting).where(Setting.key == key.value))
