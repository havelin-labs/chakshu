from fastapi import APIRouter, Depends, HTTPException, status

from chakshu.api.deps import AdminDep, UserDep, csrf_protect
from chakshu.db.session import SessionDep
from chakshu.services import events

router = APIRouter(prefix="/api/webhook-events", tags=["webhooks"], dependencies=[Depends(csrf_protect)])


@router.get("/failed")
async def failed_events(session: SessionDep, _: UserDep) -> list[dict]:
    return [
        {
            "id": e.id,
            "event": e.event,
            "action": e.payload.get("action"),
            "repo": (e.payload.get("repository") or {}).get("full_name"),
            "attempts": e.attempts,
            "error": e.error,
            "received_at": e.created_at.isoformat(),
        }
        for e in await events.recent_failures(session)
    ]


@router.post("/{delivery_id}/retry")
async def retry_event(delivery_id: str, session: SessionDep, _: AdminDep) -> dict:
    if not await events.retry(session, delivery_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No failed event with that delivery ID.")
    return {"ok": True}
