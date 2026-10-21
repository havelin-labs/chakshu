"""GitHub webhook handlers, one module per event."""

import logging
from collections.abc import Awaitable, Callable

from chakshu.db.session import get_sessionmaker
from chakshu.handlers import installation, issue_comment, pull_request, push
from chakshu.handlers.context import Context, Payload
from chakshu.services import github

log = logging.getLogger(__name__)

Handler = Callable[[Context, Payload], Awaitable[None]]

HANDLERS: dict[str, Handler] = {
    "installation": installation.handle,
    "installation_repositories": installation.handle,
    "issue_comment": issue_comment.handle,
    "pull_request": pull_request.handle,
    "push": push.handle,
}


async def dispatch(event: str, delivery_id: str, payload: Payload) -> None:
    """Run the handler for an event in its own DB session. Errors are logged, never raised."""
    handler = HANDLERS.get(event)
    if handler is None:
        return
    async with get_sessionmaker()() as session:
        creds = await github.load_credentials(session)
        if creds is None:
            return
        try:
            await handler(Context(session, creds, delivery_id), payload)
            await session.commit()
        except Exception:
            await session.rollback()
            log.exception("Webhook %s (%s) failed", event, delivery_id)
