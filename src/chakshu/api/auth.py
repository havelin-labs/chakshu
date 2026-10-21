"""Sign in with GitHub (OAuth through the GitHub App) and sign out."""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from chakshu.api.deps import CredentialsDep, csrf_protect
from chakshu.db.session import SessionDep
from chakshu.services import users

router = APIRouter(tags=["auth"])
api = APIRouter(prefix="/api/auth", tags=["auth"], dependencies=[Depends(csrf_protect)])


@router.get("/auth/login")
async def login(request: Request, creds: CredentialsDep) -> RedirectResponse:
    state = secrets.token_urlsafe(24)
    request.session["oauth_state"] = state
    return RedirectResponse(users.authorize_url(creds, state))


@router.get("/auth/callback")
async def callback(
    request: Request, creds: CredentialsDep, session: SessionDep, code: str = "", state: str = ""
) -> RedirectResponse:
    expected = request.session.pop("oauth_state", None)
    if not (code and expected and secrets.compare_digest(state, expected)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sign-in link expired. Try again.")
    try:
        user = await users.sign_in(session, creds, code)
    except users.SignInRefused:
        return RedirectResponse("/login?error=not-a-member", status.HTTP_303_SEE_OTHER)
    # New session on sign-in, so nothing from before it carries over.
    request.session.clear()
    request.session["user_id"] = str(user.id)
    return RedirectResponse("/", status.HTTP_303_SEE_OTHER)


@api.post("/logout")
async def logout(request: Request) -> dict:
    request.session.clear()
    return {"ok": True}
