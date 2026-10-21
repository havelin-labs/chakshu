import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from chakshu.api.deps import UserDep
from chakshu.core.config import get_settings
from chakshu.db.models import Repo, Reviewer, Run
from chakshu.db.session import SessionDep

router = APIRouter(prefix="/api/runs", tags=["runs"])


def serialize(run: Run, repo: Repo, reviewer: Reviewer, *, detail: bool = False) -> dict:
    data = {
        "id": str(run.id),
        "repo": repo.full_name,
        "repo_id": str(repo.id),
        "reviewer": reviewer.name,
        "pr_number": run.pr_number,
        "pr_title": run.pr_title,
        "pr_url": f"{get_settings().github_url}/{repo.full_name}/pull/{run.pr_number}",
        "head_sha": run.head_sha,
        "trigger": run.trigger,
        "requested_by": run.requested_by,
        "status": run.status,
        "progress": run.progress,
        "model": run.model,
        "cost_usd": float(run.cost_usd) if run.cost_usd is not None else None,
        "duration_ms": run.duration_ms,
        "review_url": run.review_url,
        "created_at": run.created_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }
    if detail:
        data |= {"note": run.note, "error": run.error, "attempts": run.attempts, "result": run.result}
    return data


def _query():
    return (
        select(Run, Repo, Reviewer)
        .join(Repo, Run.repo_id == Repo.id)
        .join(Reviewer, Run.reviewer_id == Reviewer.id)
    )


@router.get("")
async def list_runs(
    session: SessionDep,
    _: UserDep,
    limit: int = Query(50, ge=1, le=200),
    repo_id: uuid.UUID | None = None,
) -> list[dict]:
    stmt = _query().order_by(Run.created_at.desc()).limit(limit)
    if repo_id:
        stmt = stmt.where(Run.repo_id == repo_id)
    return [serialize(*row) for row in (await session.execute(stmt)).all()]


@router.get("/{run_id}")
async def get_run(run_id: uuid.UUID, session: SessionDep, _: UserDep) -> dict:
    row = (await session.execute(_query().where(Run.id == run_id))).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such run.")
    return serialize(*row, detail=True)
