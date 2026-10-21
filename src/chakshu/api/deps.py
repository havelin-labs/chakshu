"""Dependencies shared by API routes."""

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from chakshu.db.session import SessionDep
from chakshu.services import github
from chakshu.services.github import AppCredentials

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
CSRF_HEADER = "X-CSRF-Token"


def csrf_token(request: Request) -> str:
    """The session's CSRF token, created on first use. The portal sends it back in a header."""
    token = request.session.get("csrf")
    if not token:
        token = request.session["csrf"] = secrets.token_urlsafe(32)
    return token


async def csrf_protect(request: Request) -> None:
    """Attach to API routers: every state-changing request must echo the session token."""
    if request.method in SAFE_METHODS:
        return
    sent = request.headers.get(CSRF_HEADER, "")
    expected = request.session.get("csrf", "")
    if not (expected and secrets.compare_digest(sent, expected)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing or invalid CSRF token. Reload the page.")


async def get_credentials(session: SessionDep) -> AppCredentials:
    creds = await github.load_credentials(session)
    if creds is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Connect Chakshu to GitHub first.")
    return creds


CredentialsDep = Annotated[AppCredentials, Depends(get_credentials)]


def require_setup_session(request: Request) -> None:
    """Setup steps need the claimed setup code in this browser session."""
    if not request.session.get("setup"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Enter the setup code first.")
