import uuid
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, status
from githubkit.exception import RequestFailed
from pydantic import BaseModel, Field
from sqlalchemy import select

from chakshu.api.deps import AdminDep, CredentialsDep, UserDep, csrf_protect
from chakshu.db.models import Installation, Repo
from chakshu.db.session import SessionDep
from chakshu.services import github, installations, repo_setup, triggers

router = APIRouter(prefix="/api/repos", tags=["repos"], dependencies=[Depends(csrf_protect)])


class RepoUpdate(BaseModel):
    enabled: bool


class ReviewBody(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


async def _load(session: SessionDep, repo_id: uuid.UUID) -> tuple[Repo, Installation]:
    row = (
        await session.execute(
            select(Repo, Installation)
            .join(Installation, Repo.installation_id == Installation.id)
            .where(Repo.id == repo_id)
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such repository.")
    return row[0], row[1]


@router.get("")
async def list_repos(session: SessionDep, _: UserDep) -> list[dict]:
    repos = (await session.scalars(select(Repo).order_by(Repo.full_name))).all()
    return [
        {"id": str(r.id), "full_name": r.full_name, "private": r.private, "enabled": r.enabled} for r in repos
    ]


@router.post("/sync")
async def sync_repos(session: SessionDep, creds: CredentialsDep, _: AdminDep) -> dict:
    """Re-read installations and repo access from GitHub, e.g. after changing the app's access there."""
    count = await installations.sync_all(session, creds)
    await session.commit()
    return {"installations": count}


@router.put("/{repo_id}")
async def update_repo(repo_id: uuid.UUID, body: RepoUpdate, session: SessionDep, _: AdminDep) -> dict:
    repo, _installation = await _load(session, repo_id)
    repo.enabled = body.enabled
    await session.commit()
    return {"id": str(repo.id), "enabled": repo.enabled}


def _actions(status: repo_setup.ActionsStatus) -> dict:
    return asdict(status) | {"ready": status.ready}


@router.get("/{repo_id}/actions")
async def actions_status(repo_id: uuid.UUID, session: SessionDep, creds: CredentialsDep, _: UserDep) -> dict:
    """Is this repo ready to run reviews in GitHub Actions: workflow file and Claude secrets."""
    repo, installation = await _load(session, repo_id)
    client = github.installation_client(creds, installation.github_id)
    return _actions(await repo_setup.status(session, client, repo))


@router.post("/{repo_id}/actions")
async def set_up_actions(
    repo_id: uuid.UUID, session: SessionDep, creds: CredentialsDep, user: AdminDep
) -> dict:
    """Open a PR with the workflow (if it's missing or old) and write the Claude secrets."""
    repo, installation = await _load(session, repo_id)
    client = github.installation_client(creds, installation.github_id)
    try:
        result = await repo_setup.set_up(session, client, repo, user.login)
    except RequestFailed as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"GitHub refused ({exc.response.status_code}). The app may be missing the contents, "
            "workflows or secrets permission; Settings shows what's missing.",
        ) from exc
    return _actions(result)


@router.get("/{repo_id}/pulls")
async def list_pulls(
    repo_id: uuid.UUID, session: SessionDep, creds: CredentialsDep, _: UserDep
) -> list[dict]:
    repo, installation = await _load(session, repo_id)
    owner, name = repo.full_name.split("/", 1)
    client = github.installation_client(creds, installation.github_id)
    pulls = (await client.rest.pulls.async_list(owner, name, state="open", per_page=50)).parsed_data
    return [
        {
            "number": p.number,
            "title": p.title,
            "author": p.user.login if p.user else None,
            "draft": bool(p.draft),
            "head_sha": p.head.sha,
            "updated_at": p.updated_at.isoformat(),
            "url": p.html_url,
        }
        for p in pulls
    ]


@router.post("/{repo_id}/pulls/{number}/review")
async def request_review(
    repo_id: uuid.UUID,
    number: int,
    body: ReviewBody,
    session: SessionDep,
    creds: CredentialsDep,
    user: UserDep,
) -> dict:
    repo, installation = await _load(session, repo_id)
    if not repo.enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Reviews are turned off for this repository.")
    outcome = await triggers.request_review(
        session,
        creds,
        triggers.ReviewRequest(
            installation=installation,
            repo=repo,
            pr_number=number,
            trigger="portal",
            source_id=f"portal:{user.login}",
            requester=user.login,
            note=body.note,
        ),
    )
    await session.commit()
    return {"queued": outcome.queued, "already": outcome.already, "refused": outcome.refused}
