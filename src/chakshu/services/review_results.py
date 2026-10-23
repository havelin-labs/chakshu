"""Finish a run: publish what the runner found, or record why the review didn't finish.

Callers commit.
"""

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from githubkit.exception import RequestFailed
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.db.models import Run, RunStatus
from chakshu.helpers import findings
from chakshu.runner.protocol import Result
from chakshu.services import checks, finding_stats, jobs, publisher, runs, triggers
from chakshu.services.jobs import RunContext

log = logging.getLogger(__name__)

# A dispatched run with no result after this long is given up on (the workflow times out at 30).
DISPATCH_TIMEOUT = timedelta(minutes=45)


def _cost(value: float | None) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


async def _patches(ctx: RunContext) -> dict[str, str | None]:
    """The PR's diff at the reviewed commit, which decides where inline comments can go."""
    client = ctx.client
    owner, name = ctx.owner_and_name
    pr = (await client.rest.pulls.async_get(owner, name, ctx.run.pr_number)).parsed_data
    if pr.head.sha == ctx.run.head_sha:
        return dict(await jobs.pr_files(client, owner, name, ctx.run.pr_number))
    # Someone pushed while the review ran: diff the reviewed commit against the base it was built on.
    base = (ctx.run.result or {}).get("base_sha")
    changed = (
        await jobs.compare(client, owner, name, base, ctx.run.head_sha, ahead_only=False) if base else None
    )
    return dict(changed or [])


async def complete(session: AsyncSession, ctx: RunContext, result: Result) -> None:
    run, repo, reviewer = ctx.run, ctx.repo, ctx.reviewer
    client = ctx.client
    since = (run.result or {}).get("since")
    run.cost_usd = _cost(result.cost_usd)
    run.duration_ms = result.duration_ms

    published = await publisher.publish(
        client,
        full_name=repo.full_name,
        number=run.pr_number,
        head_sha=run.head_sha,
        reviewer=reviewer.name,
        summary=result.summary,
        raw_findings=result.findings,
        patches=await _patches(ctx),
        limits=reviewer.limits,
        ns=ctx.creds.namespace,
        pr_key=runs.pr_key(ctx.creds.namespace, repo, run.pr_number),
        reviewer_id=reviewer.id,
    )
    await finding_stats.record_posted(session, run, published.plan.inline)
    resolved = await finding_stats.sweep(session, client, repo.full_name, run.pr_number, published.found_ids)
    summary = findings.render_review_body(reviewer.name, result.summary, published.plan)
    if published.review_url:
        summary += f"\n\n[Open the review]({published.review_url})"
    if run.check_run_id is not None:
        await checks.finish(
            client,
            repo.full_name,
            run.check_run_id,
            conclusion=findings.conclusion(published.chosen, reviewer.fail_check_on),
            title=findings.counts(published.chosen),
            summary=summary,
        )
    if run.trigger == "review_requested":
        await triggers.clear_team_request(
            ctx.creds, ctx.installation.github_id, repo.full_name, run.pr_number
        )

    run.result = {
        "summary": result.summary,
        "findings": result.findings,
        "posted": len(published.plan.inline),
        "summary_only": len(published.plan.summary_only),
        "repeats": published.plan.repeats,
        "turns": result.turns,
        "since": since,
        "resolved": resolved,
    }
    run.review_url = published.review_url
    run.status, run.error = RunStatus.SUCCEEDED, None
    run.finished_at, run.progress = datetime.now(UTC), None


async def fail(
    ctx: RunContext,
    error: str,
    *,
    cost_usd: float | None = None,
    status: RunStatus = RunStatus.FAILED,
    conclusion: str = "neutral",
    title: str = "Review didn't finish",
) -> None:
    run = ctx.run
    run.status, run.error = status, error[:2000]
    if cost_usd is not None:
        run.cost_usd = _cost(cost_usd)
    run.finished_at, run.progress = datetime.now(UTC), None
    if run.check_run_id is None:
        return
    summary = run.error + (
        f"\n\n[Open the Actions run]({run.actions_run_url})" if run.actions_run_url else ""
    )
    try:
        await checks.finish(
            ctx.client,
            ctx.repo.full_name,
            run.check_run_id,
            conclusion=conclusion,
            title=title,
            summary=summary,
        )
    except RequestFailed:
        log.warning("Couldn't update check run for %s", run.id, exc_info=True)


async def expire_dispatched(session: AsyncSession) -> int:
    """Give up on dispatched runs that never reported back. Returns how many."""
    cutoff = datetime.now(UTC) - DISPATCH_TIMEOUT
    stale = (
        await session.scalars(
            select(Run).where(Run.status == RunStatus.DISPATCHED.value, Run.started_at < cutoff)
        )
    ).all()
    for run in stale:
        ctx = await jobs.load(session, run)
        message = "GitHub Actions didn't send a result within 45 minutes."
        if ctx is None:
            run.status, run.error, run.finished_at = RunStatus.FAILED, message, datetime.now(UTC)
        else:
            await fail(ctx, message)
    await session.commit()
    return len(stale)
