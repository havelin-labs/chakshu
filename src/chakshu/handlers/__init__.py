"""GitHub webhook handlers, one module per event."""

import logging
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.db.models import WebhookEvent
from chakshu.handlers import (
    installation,
    issue_comment,
    organization,
    pull_request,
    pull_request_review_comment,
    push,
    team,
    workflow_run,
)
from chakshu.handlers.context import Context, Payload
from chakshu.services import github

log = logging.getLogger(__name__)

Handler = Callable[[Context, Payload], Awaitable[None]]

HANDLERS: dict[str, Handler] = {
    "installation": installation.handle,
    "installation_repositories": installation.handle,
    "issue_comment": issue_comment.handle,
    "organization": organization.handle,
    "pull_request": pull_request.handle,
    "pull_request_review_comment": pull_request_review_comment.handle,
    "push": push.handle,
    "team": team.handle_team,
    "membership": team.handle_membership,
    "workflow_run": workflow_run.handle,
}


async def handle(session: AsyncSession, event: WebhookEvent) -> None:
    """Run the handler for a stored event. Raises on failure so the caller can retry."""
    handler = HANDLERS.get(event.event)
    creds = await github.load_credentials(session)
    if handler is None or creds is None:
        return
    await handler(Context(session, creds, event.id), event.payload)
