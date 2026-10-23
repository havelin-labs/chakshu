"""Endpoints for GitHub Actions runners doing a review. No session or CSRF: the OIDC token is the auth.

Only the Actions run Chakshu dispatched for a review may fetch its job, call
its connector tools and report its result, and only while the run is waiting
for that result.
"""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from chakshu.connectors import ToolError
from chakshu.db.models import Run, RunStatus
from chakshu.db.session import SessionDep
from chakshu.helpers import workflow
from chakshu.runner.protocol import API_PREFIX, Failure, Job, Result, ToolCall, ToolReply
from chakshu.services import connectors, jobs, oidc, replies, review_results
from chakshu.services.jobs import RunContext

log = logging.getLogger(__name__)

router = APIRouter(prefix=API_PREFIX, tags=["runner"])


def _bearer(request: Request) -> str:
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Send the Actions OIDC token as a bearer token.")
    return token


def authorize(identity: oidc.RunnerIdentity, ctx: RunContext) -> None:
    """Raise unless this identity is the Actions run dispatched for this review, still waiting."""
    if identity.repository_id != ctx.repo.github_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such run.")
    if identity.event_name != "workflow_dispatch" or not workflow.is_chakshu_workflow(
        identity.workflow_ref, ctx.repo.full_name
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Only {workflow.WORKFLOW_PATH} can run reviews.")
    if ctx.run.actions_run_id != identity.run_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Chakshu didn't start this Actions run for that review."
        )
    if ctx.run.status != RunStatus.DISPATCHED:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"This review is {ctx.run.status}, not waiting for a runner."
        )


async def runner_context(run_id: uuid.UUID, request: Request, session: SessionDep) -> RunContext:
    try:
        identity = await oidc.verify(_bearer(request))
    except oidc.InvalidToken as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid OIDC token: {exc}") from exc
    run = await session.get(Run, run_id)
    ctx = await jobs.load(session, run) if run else None
    if ctx is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such run.")
    authorize(identity, ctx)
    return ctx


RunnerDep = Annotated[RunContext, Depends(runner_context)]


@router.post("/{run_id}/job")
async def get_job(ctx: RunnerDep, session: SessionDep) -> Job:
    try:
        job = await (replies.build_job if ctx.run.reply_to else jobs.build)(session, ctx)
    except jobs.Superseded as exc:
        await review_results.fail(
            ctx,
            f"The pull request moved to {exc.new_sha[:7]} before the review started.",
            status=RunStatus.CANCELLED,
            conclusion="cancelled",
            title="Superseded by a newer commit",
        )
        await session.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, ctx.run.error) from exc
    except Exception as exc:
        log.exception("Couldn't build the job for run %s", ctx.run.id)
        await review_results.fail(ctx, f"Couldn't prepare the review: {exc}")
        await session.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, ctx.run.error) from exc
    ctx.run.progress = f"{'Answering' if job.kind == 'reply' else 'Reviewing'} with {job.model}"
    await session.commit()
    return job


@router.post("/{run_id}/tools/{connector}/{tool}")
async def call_tool(
    connector: str, tool: str, body: ToolCall, ctx: RunnerDep, session: SessionDep
) -> ToolReply:
    try:
        text = await connectors.call(session, ctx.reviewer.connectors, connector, tool, body.args)
    except ToolError as exc:
        return ToolReply(text=str(exc), is_error=True)
    return ToolReply(text=text)


@router.post("/{run_id}/result")
async def report_result(body: Result, ctx: RunnerDep, session: SessionDep) -> dict:
    try:
        await review_results.complete(session, ctx, body)
    except Exception as exc:
        # Leave the run waiting: the runner retries, and posting is idempotent (findings carry markers).
        log.exception("Couldn't publish run %s", ctx.run.id)
        await session.rollback()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Couldn't publish the review: {exc}") from exc
    await session.commit()
    return {"review_url": ctx.run.review_url}


@router.post("/{run_id}/failure")
async def report_failure(body: Failure, ctx: RunnerDep, session: SessionDep) -> dict:
    await review_results.fail(ctx, body.error, cost_usd=body.cost_usd)
    await session.commit()
    return {"ok": True}
