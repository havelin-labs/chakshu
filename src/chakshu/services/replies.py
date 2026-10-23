"""Answer people who reply to Chakshu's review comments.

reply webhook -> is it a Chakshu thread, and may this person get an answer? ->
queue a reply run for the reviewer that posted the finding -> the runner
answers in a short Actions job -> post the answer in the thread, and when the
answer says the finding is fixed or dismissed, resolve the thread and record that.

Reply runs use the review workflow and runner protocol, with `Job.kind = "reply"`.
They get no check run and don't count as reviews of the pull request.
"""

import logging
import uuid
from dataclasses import dataclass

from githubkit import GitHub
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.db.models import Installation, PostedFinding, Repo, Reviewer
from chakshu.helpers import findings, messages, replies
from chakshu.helpers.prompt import PullRequest, ThreadComment, build_reply_prompt
from chakshu.runner.protocol import Job, Result
from chakshu.services import bundle, catalog, finding_stats, github, orgs, runs, spend, threads
from chakshu.services.github import AppCredentials
from chakshu.services.jobs import RunContext, review_settings

log = logging.getLogger(__name__)

TRIGGER = "reply"


@dataclass(frozen=True)
class Reply:
    """A new reply in a review thread, from the webhook payload."""

    installation: Installation
    repo: Repo
    pr_number: int
    pr_title: str
    pr_author: str | None
    head_sha: str
    comment_id: int
    root_id: int  # the thread's first comment
    author: str


async def _reviewer_for(session: AsyncSession, finding_id: str) -> Reviewer | None:
    posted = await session.get(PostedFinding, uuid.UUID(finding_id))
    reviewer = await session.get(Reviewer, posted.reviewer_id) if posted else None
    return reviewer if reviewer and not reviewer.errors else None


async def request(session: AsyncSession, creds: AppCredentials, reply: Reply) -> bool:
    """Queue an answer if this reply is to a Chakshu finding and its author may get one."""
    owner, name = reply.repo.full_name.split("/", 1)
    client = github.installation_client(creds, reply.installation.github_id)
    root = (await client.rest.pulls.async_get_review_comment(owner, name, reply.root_id)).parsed_data
    finding_id = replies.finding_id(root.body, root.user.login if root.user else None, creds.slug)
    if finding_id is None:
        return False
    reviewer = await _reviewer_for(session, finding_id)
    if reviewer is None:
        log.info("No working reviewer for finding %s on %s; not answering", finding_id, reply.repo.full_name)
        return False

    permission = await orgs.repo_permission(
        creds, reply.installation.github_id, reply.repo.full_name, reply.author
    )
    if not replies.may_answer(reply.author, reply.pr_author, writer=orgs.can_write(permission)):
        return False
    if await runs.answers_in_thread(session, reply.repo, reply.root_id) >= replies.MAX_ANSWERS_PER_THREAD:
        log.info("Thread %s on %s has had enough answers", reply.root_id, reply.repo.full_name)
        return False
    budget = await spend.current(session)
    if budget.over_cap:
        body = messages.over_budget(reply.author, float(budget.month_to_date), float(budget.cap))
        await client.rest.pulls.async_create_reply_for_review_comment(
            owner, name, reply.pr_number, reply.root_id, body=body
        )
        return False

    added = await runs.enqueue(
        session,
        creds,
        repo=reply.repo,
        reviewer=reviewer,
        pr_number=reply.pr_number,
        pr_title=reply.pr_title,
        head_sha=reply.head_sha,
        trigger=TRIGGER,
        source_id=str(reply.comment_id),
        requested_by=reply.author,
        note=None,
        reply_to=reply.root_id,
    )
    if added:
        await client.rest.reactions.async_create_for_pull_request_review_comment(
            owner, name, reply.comment_id, content="eyes"
        )
    return added


async def _thread(client: GitHub, owner: str, name: str, number: int, root_id: int) -> list[ThreadComment]:
    comments = [
        replies.Comment(
            id=c.id,
            in_reply_to=c.in_reply_to_id or None,
            author=c.user.login if c.user else "ghost",
            body=c.body,
        )
        async for c in client.rest.paginate(
            client.rest.pulls.async_list_review_comments, owner=owner, repo=name, pull_number=number
        )
    ]
    return replies.conversation(comments, root_id)


async def build_job(session: AsyncSession, ctx: RunContext) -> Job:
    """The job for a dispatched reply run: the thread, the code at the PR's head and the reviewer's files."""
    run, repo, reviewer = ctx.run, ctx.repo, ctx.reviewer
    client = ctx.client
    owner, name = ctx.owner_and_name
    pr = (await client.rest.pulls.async_get(owner, name, run.pr_number)).parsed_data
    root = (await client.rest.pulls.async_get_review_comment(owner, name, run.reply_to)).parsed_data
    thread = await _thread(client, owner, name, run.pr_number, run.reply_to)
    reviewers_repo = await catalog.reviewers_repo(session, ctx.installation)
    if reviewers_repo is None:
        raise RuntimeError("The reviewers repo is no longer visible to the app.")
    model, max_usd = await review_settings(session, reviewer)
    token = await github.installation_token(ctx.creds, ctx.installation.github_id)
    reviewer_files = await bundle.build(
        token=token, reviewers_repo=reviewers_repo.full_name, reviewer=reviewer
    )
    prompt = build_reply_prompt(
        PullRequest(
            repo=repo.full_name,
            number=run.pr_number,
            title=pr.title,
            author=pr.user.login if pr.user else "unknown",
            base=pr.base.ref,
            head=pr.head.ref,
            description="",
        ),
        root.path,
        root.line or root.original_line,
        root.diff_hunk,
        thread,
    )
    run.model = model
    return Job(
        run_id=run.id,
        repo=repo.full_name,
        pr_number=run.pr_number,
        head_sha=run.head_sha,
        reviewer=reviewer.name,
        model=model,
        max_usd=max_usd,
        prompt=prompt,
        files=reviewer_files.files,
        kind="reply",
    )


async def post(ctx: RunContext, result: Result) -> str:
    """Post the runner's answer in the thread. Returns the answer's URL."""
    owner, name = ctx.owner_and_name
    client = ctx.client
    answer = result.summary.strip() or "I don't have anything to add."
    body = messages.reply(answer, ctx.reviewer.name, result.outcome)
    resp = await client.rest.pulls.async_create_reply_for_review_comment(
        owner, name, ctx.run.pr_number, ctx.run.reply_to, body=body
    )
    return resp.parsed_data.html_url


async def settle(session: AsyncSession, ctx: RunContext, outcome: str | None) -> bool:
    """For a fixed or dismissed finding, record the outcome and resolve its thread. True if resolved.

    Runs after the answer is posted, so GitHub errors are logged, never raised: a retry would post twice.
    """
    if outcome not in ("fixed", "dismissed"):
        return False
    owner, name = ctx.owner_and_name
    client = ctx.client
    run = ctx.run
    try:
        root = (await client.rest.pulls.async_get_review_comment(owner, name, run.reply_to)).parsed_data
        marker = findings.MARKER_RE.search(root.body or "")
        if marker:
            ids = {marker.group(1)}
            fixed, dismissed = (ids, set()) if outcome == "fixed" else (set(), ids)
            await finding_stats.record_outcomes(session, fixed, dismissed)
        return await threads.resolve_started_by(client, ctx.repo.full_name, run.pr_number, run.reply_to)
    except Exception:  # noqa: BLE001
        log.warning("Couldn't settle thread %s on %s", run.reply_to, ctx.repo.full_name, exc_info=True)
        return False
