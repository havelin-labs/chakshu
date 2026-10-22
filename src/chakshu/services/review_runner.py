"""Process one queued run from start to finish.

check run in progress -> still the PR's head? -> workspace -> agent -> publish
-> check run completed. Failures land on the run row and the check run, never
as an unhandled exception in the worker.
"""

import logging
import tempfile
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
from githubkit import GitHub
from githubkit.exception import RequestFailed
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.db.models import Installation, Repo, Reviewer, Run, RunStatus
from chakshu.db.session import get_sessionmaker
from chakshu.helpers import findings
from chakshu.helpers.git import GitError
from chakshu.helpers.prompt import PullRequest, build_prompt
from chakshu.services import catalog, checks, engine, github, publisher, queue, runs, triggers, workspace
from chakshu.services import settings_store as store
from chakshu.services.github import AppCredentials
from chakshu.services.settings_store import Key

log = logging.getLogger(__name__)


class Superseded(Exception):
    def __init__(self, new_sha: str):
        super().__init__(new_sha)
        self.new_sha = new_sha


def _transient(exc: Exception) -> bool:
    if isinstance(exc, RequestFailed):
        return exc.response.status_code >= 500 or exc.response.status_code == 429
    return isinstance(exc, httpx.TransportError | GitError)


async def _review_settings(session: AsyncSession, reviewer: Reviewer) -> tuple[str, float, str | None]:
    values = await store.get_many(session, Key.DEFAULT_MODEL, Key.MAX_USD_PER_REVIEW, Key.ANTHROPIC_API_KEY)
    model = reviewer.model or values[Key.DEFAULT_MODEL] or "sonnet"
    max_usd = float(reviewer.limits.get("max_usd") or values[Key.MAX_USD_PER_REVIEW] or 2)
    return model, max_usd, values[Key.ANTHROPIC_API_KEY]


async def _changes_since(
    client: GitHub, owner: str, name: str, since: str, head: str
) -> list[tuple[str, str | None]] | None:
    """Files changed between the last reviewed commit and now, or None for a full review.

    Falls back to a full review when history was rewritten (force push) or the
    comparison isn't available.
    """
    try:
        comparison = (
            await client.rest.repos.async_compare_commits(owner, name, f"{since}...{head}")
        ).parsed_data
    except RequestFailed:
        return None
    if comparison.status != "ahead" or not comparison.files:
        return None
    return [(f.filename, f.patch) for f in comparison.files]


async def _execute(
    session: AsyncSession,
    creds: AppCredentials,
    client: GitHub,
    run: Run,
    repo: Repo,
    reviewer: Reviewer,
    installation: Installation,
) -> None:
    owner, name = repo.full_name.split("/", 1)
    pr = (await client.rest.pulls.async_get(owner, name, run.pr_number)).parsed_data
    if pr.head.sha != run.head_sha:
        raise Superseded(pr.head.sha)

    files = [
        (f.filename, f.patch)
        async for f in client.rest.paginate(client.rest.pulls.async_list_files, owner, name, run.pr_number)
    ]
    since = await runs.last_reviewed_head(session, run)
    new_files = await _changes_since(client, owner, name, since, run.head_sha) if since else None
    if new_files is None:
        since = None
    reviewers_repo = await catalog.reviewers_repo(session, installation)
    if reviewers_repo is None:
        raise RuntimeError("The reviewers repo is no longer visible to the app.")
    model, max_usd, api_key = await _review_settings(session, reviewer)
    run.model = model

    await queue.set_progress(session, run, "Preparing workspace")
    token = await github.installation_token(creds, installation.github_id)
    with tempfile.TemporaryDirectory(prefix="chakshu-run-") as tmp:
        ws = await workspace.build(
            Path(tmp),
            token=token,
            reviewers_repo=reviewers_repo.full_name,
            reviewer=reviewer,
            pr_repo=repo.full_name,
            head_sha=run.head_sha,
        )
        await queue.set_progress(session, run, f"Reviewing with {model}")
        prompt = build_prompt(
            PullRequest(
                repo=repo.full_name,
                number=run.pr_number,
                title=pr.title,
                author=pr.user.login if pr.user else "unknown",
                base=pr.base.ref,
                head=pr.head.ref,
                description=pr.body or "",
            ),
            files,
            ws.skills,
            run.note,
            since=since,
            new_files=new_files,
        )
        result = await engine.review(ws.root, prompt, model=model, max_usd=max_usd, api_key=api_key)

    run.cost_usd = Decimal(str(result.cost_usd)) if result.cost_usd is not None else None
    run.duration_ms = result.duration_ms
    await queue.set_progress(session, run, "Publishing")

    published = await publisher.publish(
        client,
        full_name=repo.full_name,
        number=run.pr_number,
        head_sha=run.head_sha,
        reviewer=reviewer.name,
        summary=result.summary,
        raw_findings=result.findings,
        patches=dict(files),
        limits=reviewer.limits,
        ns=creds.namespace,
        pr_key=runs.pr_key(creds.namespace, repo, run.pr_number),
        reviewer_id=reviewer.id,
    )
    conclusion = findings.conclusion(published.chosen, reviewer.fail_check_on)
    summary = findings.render_review_body(reviewer.name, result.summary, published.plan)
    if published.review_url:
        summary += f"\n\n[Open the review]({published.review_url})"
    await checks.finish(
        client,
        repo.full_name,
        run.check_run_id,
        conclusion=conclusion,
        title=findings.counts(published.chosen),
        summary=summary,
    )
    if run.trigger == "review_requested":
        await triggers.clear_team_request(creds, installation.github_id, repo.full_name, run.pr_number)

    run.result = {
        "summary": result.summary,
        "findings": result.findings,
        "posted": len(published.plan.inline),
        "summary_only": len(published.plan.summary_only),
        "repeats": published.plan.repeats,
        "turns": result.turns,
        "since": since,
    }
    run.review_url = published.review_url
    run.status = RunStatus.SUCCEEDED


async def process(run_id: uuid.UUID) -> None:
    async with get_sessionmaker()() as session:
        run = await session.get(Run, run_id)
        if run is None:
            return
        repo = await session.get(Repo, run.repo_id)
        reviewer = await session.get(Reviewer, run.reviewer_id)
        installation = await session.get(Installation, repo.installation_id) if repo else None
        creds = await github.load_credentials(session)
        if not (repo and reviewer and installation and creds):
            run.status, run.error = RunStatus.FAILED, "Repo, reviewer or GitHub app is gone."
            run.finished_at = datetime.now(UTC)
            await session.commit()
            return

        client = github.installation_client(creds, installation.github_id)
        try:
            if run.check_run_id is None:
                run.check_run_id = await checks.start(
                    client, repo.full_name, run.head_sha, reviewer.name, str(run.id)
                )
                await session.commit()
            await _execute(session, creds, client, run, repo, reviewer, installation)
        except Superseded as exc:
            run.status = RunStatus.CANCELLED
            run.error = f"The pull request moved to {exc.new_sha[:7]} before the review started."
            await _close_check(client, repo, run, "cancelled", "Superseded by a newer commit", run.error)
        except Exception as exc:  # noqa: BLE001 - every failure is recorded on the run
            await session.rollback()
            run = await session.get(Run, run_id, populate_existing=True)
            if _transient(exc) and run.attempts < queue.MAX_ATTEMPTS:
                log.warning("Run %s hit a transient error, requeueing: %s", run_id, exc)
                run.status, run.progress = RunStatus.QUEUED, f"Retrying after: {exc}"[:500]
                await session.commit()
                return
            log.exception("Run %s failed", run_id)
            run.status, run.error = RunStatus.FAILED, str(exc)[:2000]
            if isinstance(exc, engine.EngineError) and exc.cost_usd is not None:
                run.cost_usd = Decimal(str(exc.cost_usd))
            await _close_check(client, repo, run, "neutral", "Review didn't finish", run.error)

        run.finished_at = datetime.now(UTC)
        run.progress = None
        await session.commit()


async def _close_check(
    client: GitHub, repo: Repo, run: Run, conclusion: str, title: str, summary: str
) -> None:
    if run.check_run_id is None:
        return
    try:
        await checks.finish(
            client, repo.full_name, run.check_run_id, conclusion=conclusion, title=title, summary=summary
        )
    except RequestFailed:
        log.warning("Couldn't update check run for %s", run.id, exc_info=True)
