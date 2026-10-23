"""Tell admins about spend before the cap surprises them, and send a weekly digest.

The worker calls `run` on every maintenance pass. It only posts when something
is due: a spend threshold crossed for the first time this month, or the weekly
digest on Monday (UTC). What was sent is stored, so a restart never repeats it.
Delivery is a Slack incoming webhook.
"""

import json
import logging
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.core.config import get_settings
from chakshu.db.models import FindingOutcome, PostedFinding
from chakshu.helpers import alerts as text
from chakshu.helpers import analytics as calc
from chakshu.services import analytics, spend
from chakshu.services import settings_store as store
from chakshu.services.analytics import Filters
from chakshu.services.settings_store import Key

log = logging.getLogger(__name__)

TIMEOUT = 10.0
DIGEST_WEEKDAY = 0  # Monday
NOISY_MIN_VERDICTS = 5  # a skill needs this many fixed + dismissed findings to be called noisy


class AlertError(Exception):
    pass


async def post(webhook: str, message: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(webhook, json={"text": message})
    except httpx.HTTPError as exc:
        raise AlertError(f"Couldn't reach the webhook: {exc}") from exc
    if resp.status_code >= 400:
        raise AlertError(f"The webhook answered {resp.status_code}: {resp.text[:200]}")


def _link(path: str) -> str:
    return f"{get_settings().base_url}{path}"


async def _spend_alerts(
    session: AsyncSession, webhook: str, thresholds: list[int], sent_raw: str | None
) -> None:
    today = datetime.now(UTC).date()
    month = text.month_key(today)
    sent = json.loads(sent_raw or "{}")
    already = sent.get("thresholds", []) if sent.get("month") == month else []
    budget = await spend.current(session)
    cap = float(budget.cap) if budget.cap is not None else None
    spent = float(budget.month_to_date)
    crossed = text.due(spent, cap, thresholds, already)
    if not crossed:
        return
    projection = calc.forecast(spent, cap, today)
    highest = crossed[-1]  # one message for the highest threshold crossed, not one per threshold
    await post(
        webhook,
        text.spend_message(
            highest,
            spent,
            cap,
            projection.projected,
            projection.cap_hit_on and projection.cap_hit_on.isoformat(),
            _link("/analytics?tab=cost"),
        ),
    )
    await store.put(session, Key.ALERTS_SENT, json.dumps({"month": month, "thresholds": already + crossed}))
    await session.commit()


async def digest_data(session: AsyncSession) -> dict:
    week = Filters.last(7)
    totals = await analytics.totals(session, week)
    fixed_rows = (
        await session.execute(
            select(PostedFinding.severity, func.count())
            .where(
                PostedFinding.outcome == FindingOutcome.FIXED.value,
                PostedFinding.closed_at >= week.start,
                PostedFinding.closed_at < week.end,
            )
            .group_by(PostedFinding.severity)
        )
    ).all()
    order = {s: i for i, s in enumerate(("critical", "high", "medium", "low", "info"))}
    fixed_by_severity = dict(sorted(((s, n) for s, n in fixed_rows), key=lambda kv: order.get(kv[0], 9)))
    skills = [
        r
        for r in await analytics.breakdown(session, week, "skill")
        if r["fixed"] + r["dismissed"] >= NOISY_MIN_VERDICTS and r["dismissed_rate"]
    ]
    noisiest = max(skills, key=lambda r: r["dismissed_rate"], default=None)
    repos = [r for r in await analytics.breakdown(session, week, "repo") if r["spend"] > 0][:3]
    budget = await spend.current(session)
    return {
        "totals": totals,
        "fixed_by_severity": fixed_by_severity,
        "noisiest_skill": noisiest,
        "top_repos": repos,
        "month_spend": float(budget.month_to_date),
        "cap": float(budget.cap) if budget.cap is not None else None,
    }


async def _digest(session: AsyncSession, webhook: str, last_week: str | None) -> None:
    today = datetime.now(UTC).date()
    week = text.week_key(today - timedelta(days=7))  # the digest covers the week that just ended
    if today.weekday() != DIGEST_WEEKDAY or last_week == week:
        return
    await post(webhook, text.digest_message(week, await digest_data(session), _link("/analytics")))
    await store.put(session, Key.DIGEST_SENT_WEEK, week)
    await session.commit()


async def run(session: AsyncSession) -> None:
    values = await store.get_many(
        session,
        Key.ALERTS_WEBHOOK,
        Key.ALERTS_THRESHOLDS,
        Key.ALERTS_SENT,
        Key.ALERTS_DIGEST,
        Key.DIGEST_SENT_WEEK,
    )
    webhook = values[Key.ALERTS_WEBHOOK]
    if not webhook:
        return
    try:
        await _spend_alerts(
            session, webhook, text.parse_thresholds(values[Key.ALERTS_THRESHOLDS]), values[Key.ALERTS_SENT]
        )
        if values[Key.ALERTS_DIGEST] == "true":
            await _digest(session, webhook, values[Key.DIGEST_SENT_WEEK])
    except AlertError as exc:
        log.warning("Couldn't send a Chakshu alert: %s", exc)


async def send_test(session: AsyncSession) -> None:
    webhook = await store.get(session, Key.ALERTS_WEBHOOK)
    if not webhook:
        raise AlertError("Save a Slack webhook URL first.")
    await post(
        webhook, ":wave: Chakshu alerts are connected. Spend alerts and the weekly digest will arrive here."
    )
