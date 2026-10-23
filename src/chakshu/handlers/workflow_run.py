"""A Chakshu Actions run that ended without reporting back (cancelled, timed out) fails its review."""

from sqlalchemy import select

from chakshu.db.models import Run, RunStatus
from chakshu.handlers.context import Context, Payload
from chakshu.services import jobs, review_results


async def handle(ctx: Context, payload: Payload) -> None:
    workflow_run = payload.get("workflow_run") or {}
    if payload.get("action") != "completed" or not workflow_run.get("id"):
        return
    run = await ctx.session.scalar(select(Run).where(Run.actions_run_id == workflow_run["id"]))
    if run is None or run.status != RunStatus.DISPATCHED:
        return
    loaded = await jobs.load(ctx.session, run)
    message = (
        f"The GitHub Actions run ended ({workflow_run.get('conclusion') or 'unknown'}) without sending "
        "a result. Its logs say why."
    )
    if loaded is None:
        run.status, run.error = RunStatus.FAILED, message
        return
    await review_results.fail(loaded, message)
