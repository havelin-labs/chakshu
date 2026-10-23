"""Admin settings for spend alerts and the weekly digest. The webhook URL is write-only."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from chakshu.api.deps import AdminDep, csrf_protect
from chakshu.core import crypto
from chakshu.db.session import SessionDep
from chakshu.helpers import alerts as text
from chakshu.services import alerts
from chakshu.services import settings_store as store
from chakshu.services.settings_store import Key

router = APIRouter(prefix="/api/settings/alerts", tags=["alerts"], dependencies=[Depends(csrf_protect)])


class AlertsUpdate(BaseModel):
    # None keeps the stored webhook; "" removes it.
    webhook: str | None = Field(default=None, max_length=500, pattern=r"^(https://\S+)?$")
    thresholds: list[int] = Field(min_length=1, max_length=10)
    digest: bool


async def _read(session: SessionDep) -> dict:
    values = await store.get_many(session, Key.ALERTS_WEBHOOK, Key.ALERTS_THRESHOLDS, Key.ALERTS_DIGEST)
    webhook = values[Key.ALERTS_WEBHOOK]
    return {
        "webhook": {"set": bool(webhook), "hint": crypto.mask(webhook)},
        "thresholds": text.parse_thresholds(values[Key.ALERTS_THRESHOLDS]),
        "digest": values[Key.ALERTS_DIGEST] == "true",
    }


@router.get("")
async def get_alerts(session: SessionDep, _: AdminDep) -> dict:
    return await _read(session)


@router.put("")
async def put_alerts(body: AlertsUpdate, session: SessionDep, _: AdminDep) -> dict:
    thresholds = text.parse_thresholds(",".join(str(t) for t in body.thresholds))
    if not thresholds:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Use percentages from 1 to 200.")
    values: dict[Key, str | None] = {
        Key.ALERTS_THRESHOLDS: ",".join(str(t) for t in thresholds),
        Key.ALERTS_DIGEST: "true" if body.digest else "false",
    }
    if body.webhook is not None:
        values[Key.ALERTS_WEBHOOK] = body.webhook.strip() or None
    await store.put_many(session, values)
    await session.commit()
    return await _read(session)


@router.post("/test")
async def test_alert(session: SessionDep, _: AdminDep) -> dict:
    try:
        await alerts.send_test(session)
    except alerts.AlertError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return {"ok": True}
