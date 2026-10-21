from fastapi import APIRouter, Request

from chakshu.api.deps import OptionalUserDep, csrf_token
from chakshu.db.session import SessionDep
from chakshu.services import github, setup, users

router = APIRouter(prefix="/api", tags=["session"])


@router.get("/session")
async def get_session_info(request: Request, session: SessionDep, user: OptionalUserDep) -> dict:
    """Everything the portal needs on load: is the app set up, who is signed in, the CSRF token."""
    creds = await github.load_credentials(session)
    return {
        "configured": creds is not None,
        "setup_claimed": bool(request.session.get("setup")),
        "app": {"slug": creds.slug, "install_url": github.install_url(creds.slug)} if creds else None,
        "webhooks": bool(creds and creds.webhook_secret) if creds else setup.webhooks_reachable(),
        "user": users.public(user) if user else None,
        "csrf_token": csrf_token(request),
    }
