import uuid
from dataclasses import asdict
from typing import get_args

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from chakshu.api.deps import AdminDep, CredentialsDep, UserDep, csrf_protect
from chakshu.core.config import get_settings
from chakshu.db.models import Installation, Reviewer
from chakshu.db.session import SessionDep
from chakshu.helpers import mentions
from chakshu.helpers.catalog import AutoEvent
from chakshu.helpers.reviewer_drafts import ReviewerDraft
from chakshu.services import catalog, connectors, reviewer_editor
from chakshu.services import settings_store as store
from chakshu.services.reviewer_editor import DraftError
from chakshu.services.settings_store import Key

router = APIRouter(prefix="/api/reviewers", tags=["reviewers"], dependencies=[Depends(csrf_protect)])


def _serialize(reviewer: Reviewer, installation: Installation, repo_name: str | None) -> dict:
    source_url = (
        f"{get_settings().github_url}/{repo_name}/tree/{reviewer.source_sha}/{reviewer.source_path}"
        if repo_name
        else None
    )
    return {
        "id": str(reviewer.id),
        "account": installation.account_login,
        "name": reviewer.name,
        "product": reviewer.product,
        "description": reviewer.description,
        "owner_team": reviewer.owner_team,
        # Request this team in a pull request's Reviewers box to run just this reviewer.
        "team": f"{installation.account_login}/{mentions.reviewer_team(reviewer.name)}",
        "model": reviewer.model,
        "repos": reviewer.repos,
        "paths": reviewer.paths,
        "auto": reviewer.auto,
        "skills": reviewer.skills,
        "limits": reviewer.limits,
        "fail_check_on": reviewer.fail_check_on,
        "source_sha": reviewer.source_sha,
        "source_url": source_url,
        "errors": reviewer.errors,
    }


@router.get("")
async def list_reviewers(session: SessionDep, _: UserDep) -> list[dict]:
    rows = (
        await session.execute(
            select(Reviewer, Installation)
            .join(Installation, Reviewer.installation_id == Installation.id)
            .order_by(Installation.account_login, Reviewer.name)
        )
    ).all()
    repos: dict = {}
    for _reviewer, installation in rows:
        if installation.id not in repos:
            repo = await catalog.reviewers_repo(session, installation)
            repos[installation.id] = repo.full_name if repo else None
    return [_serialize(r, i, repos[i.id]) for r, i in rows]


class ProposalBody(BaseModel):
    draft: ReviewerDraft
    reviewer_id: uuid.UUID | None = None  # None proposes a new reviewer


def _draft_error(exc: DraftError) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "; ".join(exc.errors))


async def _load(session: SessionDep, reviewer_id: uuid.UUID) -> tuple[Reviewer, Installation]:
    row = (
        await session.execute(
            select(Reviewer, Installation)
            .join(Installation, Reviewer.installation_id == Installation.id)
            .where(Reviewer.id == reviewer_id)
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such reviewer.")
    return row[0], row[1]


@router.get("/options")
async def editor_options(session: SessionDep, _: UserDep) -> dict:
    """Choices for the reviewer editor. Models are suggestions; any model name is accepted."""
    installs = (await session.scalars(select(Installation).where(Installation.suspended.is_(False)))).all()
    used = (await session.scalars(select(Reviewer.model).where(Reviewer.model.is_not(None)))).all()
    default_model = await store.get(session, Key.DEFAULT_MODEL)
    return {
        "accounts": sorted(i.account_login for i in installs),
        "models": sorted({m for m in [default_model, *used] if m}),
        "default_model": default_model,
        "connectors": [c.name for c in await connectors.list_all(session)],
        "auto_events": list(get_args(AutoEvent)),
    }


@router.get("/{reviewer_id}/draft")
async def get_draft(reviewer_id: uuid.UUID, session: SessionDep, creds: CredentialsDep, _: UserDep) -> dict:
    """The reviewer's files on the reviewers repo's default branch, in editable form."""
    reviewer, installation = await _load(session, reviewer_id)
    try:
        draft = await reviewer_editor.load_draft(session, creds, installation, reviewer)
    except DraftError as exc:
        raise _draft_error(exc) from exc
    return draft.model_dump()


@router.post("/proposals")
async def propose(body: ProposalBody, session: SessionDep, creds: CredentialsDep, user: UserDep) -> dict:
    """Open a pull request in the reviewers repo with the new or changed reviewer.

    Anyone signed in may propose: the pull request is where the change gets reviewed.
    """
    reviewer = None
    if body.reviewer_id:
        reviewer, installation = await _load(session, body.reviewer_id)
    else:
        installation = await reviewer_editor.installation_for(session, body.draft.account)
        if installation is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"Chakshu isn't installed on {body.draft.account}."
            )
    try:
        proposal = await reviewer_editor.propose(
            session, creds, installation, body.draft, reviewer, user.login
        )
    except DraftError as exc:
        raise _draft_error(exc) from exc
    return asdict(proposal)


@router.post("/sync")
async def sync_reviewers(session: SessionDep, creds: CredentialsDep, _: AdminDep) -> list[dict]:
    results = await catalog.sync_all(session, creds)
    await session.commit()
    return [asdict(r) for r in results]
