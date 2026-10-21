from dataclasses import asdict

from fastapi import APIRouter, Depends
from sqlalchemy import select

from chakshu.api.deps import AdminDep, CredentialsDep, UserDep, csrf_protect
from chakshu.core.config import get_settings
from chakshu.db.models import Installation, Reviewer
from chakshu.db.session import SessionDep
from chakshu.services import catalog

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


@router.post("/sync")
async def sync_reviewers(session: SessionDep, creds: CredentialsDep, _: AdminDep) -> list[dict]:
    results = await catalog.sync_all(session, creds)
    await session.commit()
    return [asdict(r) for r in results]
