"""POST /webhooks/github: verify, drop redeliveries, answer fast, handle in the background."""

import json

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from githubkit.webhooks import verify

from chakshu import handlers
from chakshu.db.session import SessionDep
from chakshu.services import deliveries, github

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/github")
async def receive(request: Request, session: SessionDep, background: BackgroundTasks) -> dict:
    creds = await github.load_credentials(session)
    if creds is None or not creds.webhook_secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Webhooks aren't configured.")

    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not signature or not verify(creds.webhook_secret, body, signature):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bad signature.")

    event = request.headers.get("X-GitHub-Event", "")
    delivery_id = request.headers.get("X-GitHub-Delivery", "")
    if not delivery_id or not await deliveries.first_time(session, delivery_id, event):
        return {"status": "duplicate"}
    await session.commit()

    # GitHub gives up after 10 seconds, so the real work happens after we reply.
    background.add_task(handlers.dispatch, event, delivery_id, json.loads(body))
    return {"status": "accepted"}
