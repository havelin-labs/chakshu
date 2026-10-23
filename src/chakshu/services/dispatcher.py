"""Hand a queued run to GitHub Actions in the pull request's repository.

check run in progress -> PR still at this commit? -> workflow_dispatch -> link the
check to the Actions run. The run then waits as `dispatched` until the runner
reports back through the runner API.
"""

import logging
import uuid

import httpx
from githubkit.exception import RequestFailed
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.core.config import get_settings
from chakshu.db.models import Run, RunStatus
from chakshu.helpers import workflow
from chakshu.helpers.urls import is_public_url
from chakshu.services import checks, jobs, queue, review_results
from chakshu.services.jobs import RunContext

log = logging.getLogger(__name__)


class DispatchError(Exception):
    """Why a run couldn't be handed to Actions, in words for the check run."""


def _transient(exc: Exception) -> bool:
    if isinstance(exc, RequestFailed):
        return exc.response.status_code >= 500 or exc.response.status_code == 429
    return isinstance(exc, httpx.TransportError)


def _explain(exc: RequestFailed, ctx: RunContext) -> DispatchError:
    portal = f"{get_settings().base_url}/repos/{ctx.repo.id}"
    if exc.response.status_code == 404:
        return DispatchError(
            f"{ctx.repo.full_name} doesn't have the Chakshu workflow ({workflow.WORKFLOW_PATH}) on "
            f"{ctx.repo.default_branch} yet. An admin can add it from {portal}."
        )
    if exc.response.status_code == 403:
        return DispatchError(
            "The Chakshu GitHub App isn't allowed to start workflows here. An admin needs to grant "
            "it the Actions permission; Chakshu's status page lists what's missing."
        )
    return DispatchError(f"GitHub refused to start the workflow ({exc.response.status_code}).")


async def _dispatch(ctx: RunContext) -> None:
    run, repo = ctx.run, ctx.repo
    client = ctx.client
    owner, name = ctx.owner_and_name
    server = get_settings().public_runner_url
    if not is_public_url(server):
        raise DispatchError(
            f"GitHub Actions can't reach Chakshu at {server}. Set CHAKSHU_RUNNER_URL to a public URL "
            "(a tunnel works for a laptop install)."
        )

    pr = (await client.rest.pulls.async_get(owner, name, run.pr_number)).parsed_data
    if pr.head.sha != run.head_sha:
        raise jobs.Superseded(pr.head.sha)

    try:
        resp = await client.rest.actions.async_create_workflow_dispatch(
            owner,
            name,
            workflow.WORKFLOW_FILE,
            data={
                "ref": repo.default_branch,
                "inputs": workflow.dispatch_inputs(
                    run_id=str(run.id),
                    pr=run.pr_number,
                    head_sha=run.head_sha,
                    reviewer=ctx.reviewer.name,
                    server=server,
                ),
            },
        )
    except RequestFailed as exc:
        if _transient(exc):
            raise
        raise _explain(exc, ctx) from exc

    dispatched = resp.parsed_data
    run.actions_run_id = dispatched.workflow_run_id
    run.actions_run_url = dispatched.html_url
    run.status, run.progress = RunStatus.DISPATCHED, "Waiting for a GitHub Actions runner"
    if run.check_run_id is not None:
        await checks.link_actions_run(client, repo.full_name, run.check_run_id, dispatched.html_url)
    log.info("Run %s dispatched to %s", run.id, dispatched.html_url)


async def dispatch(session: AsyncSession, run_id: uuid.UUID) -> None:
    """Dispatch one claimed run. Every outcome is recorded on the run; nothing is raised."""
    run = await session.get(Run, run_id)
    if run is None:
        return
    ctx = await jobs.load(session, run)
    if ctx is None:
        run.status, run.error = RunStatus.FAILED, "Repo, reviewer or GitHub app is gone."
        await session.commit()
        return

    try:
        if run.check_run_id is None:
            run.check_run_id = await checks.start(
                ctx.client, ctx.repo.full_name, run.head_sha, ctx.reviewer.name, str(run.id)
            )
            await session.commit()
        await _dispatch(ctx)
    except jobs.Superseded as exc:
        await review_results.fail(
            ctx,
            f"The pull request moved to {exc.new_sha[:7]} before the review started.",
            status=RunStatus.CANCELLED,
            conclusion="cancelled",
            title="Superseded by a newer commit",
        )
    except DispatchError as exc:
        await review_results.fail(ctx, str(exc), title="Couldn't start the review")
    except Exception as exc:  # noqa: BLE001 - every failure is recorded on the run
        if _transient(exc) and run.attempts < queue.MAX_ATTEMPTS:
            log.warning("Run %s hit a transient error, requeueing: %s", run_id, exc)
            run.status, run.progress = RunStatus.QUEUED, f"Retrying after: {exc}"[:500]
        else:
            log.exception("Couldn't dispatch run %s", run_id)
            await review_results.fail(ctx, str(exc), title="Couldn't start the review")
    await session.commit()
