"""POST /webhooks/github: verify, store, reply. The worker does the handling."""

import json

from fastapi import APIRouter, HTTPException, Request, status
from githubkit.webhooks import verify

from chakshu.db.session import SessionDep
from chakshu.services import events, github

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/github")
async def receive(request: Request, session: SessionDep) -> dict:
    creds = await github.load_credentials(session)
    if creds is None or not creds.webhook_secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Webhooks aren't configured.")

    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not signature or not verify(creds.webhook_secret, body, signature):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bad signature.")

    delivery_id = request.headers.get("X-GitHub-Delivery", "")
    event = request.headers.get("X-GitHub-Event", "")
    if not delivery_id or not await events.store(session, delivery_id, event, json.loads(body)):
        return {"status": "duplicate"}
    await session.commit()
    return {"status": "accepted"}
