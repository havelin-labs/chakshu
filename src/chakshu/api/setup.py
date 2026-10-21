"""Setup endpoints: claim the instance, create the GitHub App, sync installations."""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from chakshu.api.deps import CredentialsDep, csrf_protect, require_setup_or_admin
from chakshu.db.session import SessionDep
from chakshu.services import github, installations, setup

router = APIRouter(prefix="/api/setup", tags=["setup"], dependencies=[Depends(csrf_protect)])


class ClaimRequest(BaseModel):
    code: str = Field(min_length=4, max_length=20)


class ManifestRequest(BaseModel):
    # GitHub App names are global across github.com, so the portal suggests one with the org in it.
    name: str = Field(min_length=3, max_length=34)
    org: str | None = Field(default=None, max_length=39)


async def _ensure_not_configured(session: SessionDep) -> None:
    if await github.load_credentials(session):
        raise HTTPException(status.HTTP_409_CONFLICT, "Chakshu is already connected to GitHub.")


@router.post("/claim", dependencies=[Depends(_ensure_not_configured)])
async def claim(body: ClaimRequest, request: Request, session: SessionDep) -> dict:
    if not await setup.check_setup_code(session, body.code):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "That setup code doesn't match. Check the web logs.")
    request.session["setup"] = True
    return {"ok": True}


@router.post("/manifest", dependencies=[Depends(require_setup_or_admin), Depends(_ensure_not_configured)])
async def manifest(body: ManifestRequest, request: Request) -> dict:
    state = secrets.token_urlsafe(24)
    request.session["manifest_state"] = state
    org = (body.org or "").strip() or None
    return {
        "action": setup.manifest_action_url(org, state),
        "manifest": setup.build_manifest(body.name.strip()),
        "webhooks": setup.webhooks_reachable(),
    }


@router.get("/callback", dependencies=[Depends(require_setup_or_admin)])
async def callback(code: str, state: str, request: Request, session: SessionDep) -> RedirectResponse:
    expected = request.session.pop("manifest_state", None)
    if not (expected and secrets.compare_digest(state, expected)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Setup link expired. Start again from the portal.")
    await _ensure_not_configured(session)
    creds = await setup.complete_manifest(session, code)
    return RedirectResponse(github.install_url(creds.slug), status.HTTP_303_SEE_OTHER)


@router.post("/sync", dependencies=[Depends(require_setup_or_admin)])
async def sync(creds: CredentialsDep, session: SessionDep) -> dict:
    count = await installations.sync_all(session, creds)
    await session.commit()
    return {"installations": count}
