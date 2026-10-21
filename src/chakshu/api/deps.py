"""Dependencies shared by API routes."""

import secrets
import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from chakshu.db.models import User
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


async def optional_user(request: Request, session: SessionDep) -> User | None:
    raw = request.session.get("user_id")
    if not raw:
        return None
    try:
        return await session.get(User, uuid.UUID(raw))
    except ValueError:
        return None


async def current_user(user: Annotated[User | None, Depends(optional_user)]) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in first.")
    return user


async def admin_user(user: Annotated[User, Depends(current_user)]) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only Chakshu admins can do that.")
    return user


OptionalUserDep = Annotated[User | None, Depends(optional_user)]
UserDep = Annotated[User, Depends(current_user)]
AdminDep = Annotated[User, Depends(admin_user)]


async def require_setup_or_admin(request: Request, user: OptionalUserDep) -> None:
    """Setup steps need the claimed setup code in this browser session, or an admin."""
    if not (request.session.get("setup") or (user and user.is_admin)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Enter the setup code first.")
