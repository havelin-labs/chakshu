"""Build the job a runner gets for one run: the prompt, the reviewer's files and its connector tools."""

from dataclasses import dataclass

from githubkit import GitHub
from githubkit.exception import RequestFailed
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.db.models import Installation, Repo, Reviewer, Run
from chakshu.helpers.prompt import FileDiff, PullRequest, build_prompt
from chakshu.runner.protocol import Job
from chakshu.services import bundle, catalog, connectors, github, runs
from chakshu.services import settings_store as store
from chakshu.services.github import AppCredentials
from chakshu.services.settings_store import Key


class Superseded(Exception):
    def __init__(self, new_sha: str):
        super().__init__(new_sha)
        self.new_sha = new_sha


@dataclass(frozen=True)
class RunContext:
    """Everything a run belongs to, loaded once."""

    creds: AppCredentials
    run: Run
    repo: Repo
    reviewer: Reviewer
    installation: Installation

    @property
    def client(self) -> GitHub:
        return github.installation_client(self.creds, self.installation.github_id)

    @property
    def owner_and_name(self) -> tuple[str, str]:
        owner, name = self.repo.full_name.split("/", 1)
        return owner, name


async def load(session: AsyncSession, run: Run) -> RunContext | None:
    repo = await session.get(Repo, run.repo_id)
    reviewer = await session.get(Reviewer, run.reviewer_id)
    installation = await session.get(Installation, repo.installation_id) if repo else None
    creds = await github.load_credentials(session)
    if not (repo and reviewer and installation and creds):
        return None
    return RunContext(creds=creds, run=run, repo=repo, reviewer=reviewer, installation=installation)


async def pr_files(client: GitHub, owner: str, name: str, number: int) -> list[FileDiff]:
    return [
        (f.filename, f.patch)
        async for f in client.rest.paginate(
            client.rest.pulls.async_list_files, owner=owner, repo=name, pull_number=number
        )
    ]


async def compare(
    client: GitHub, owner: str, name: str, base: str, head: str, *, ahead_only: bool
) -> list[FileDiff] | None:
    """Files changed from `base` to `head` (three-dot: from their merge base), or None if unavailable.

    `ahead_only`: also None when head isn't simply ahead of base, i.e. history was rewritten.
    """
    try:
        comparison = (
            await client.rest.repos.async_compare_commits(owner, name, f"{base}...{head}")
        ).parsed_data
    except RequestFailed:
        return None
    if (ahead_only and comparison.status != "ahead") or not comparison.files:
        return None
    return [(f.filename, f.patch) for f in comparison.files]


async def review_settings(session: AsyncSession, reviewer: Reviewer) -> tuple[str, float]:
    values = await store.get_many(session, Key.DEFAULT_MODEL, Key.MAX_USD_PER_REVIEW)
    model = reviewer.model or values[Key.DEFAULT_MODEL] or "sonnet"
    max_usd = float(reviewer.limits.get("max_usd") or values[Key.MAX_USD_PER_REVIEW] or 2)
    return model, max_usd


async def build(session: AsyncSession, ctx: RunContext) -> Job:
    """The job for a dispatched run. Raises Superseded if the PR moved on."""
    run, repo, reviewer = ctx.run, ctx.repo, ctx.reviewer
    client = ctx.client
    owner, name = ctx.owner_and_name
    pr = (await client.rest.pulls.async_get(owner, name, run.pr_number)).parsed_data
    if pr.head.sha != run.head_sha:
        raise Superseded(pr.head.sha)

    files = await pr_files(client, owner, name, run.pr_number)
    since = await runs.last_reviewed_head(session, run)
    # A force push since the last review means a full review again.
    new_files = await compare(client, owner, name, since, run.head_sha, ahead_only=True) if since else None
    if new_files is None:
        since = None
    reviewers_repo = await catalog.reviewers_repo(session, ctx.installation)
    if reviewers_repo is None:
        raise RuntimeError("The reviewers repo is no longer visible to the app.")
    model, max_usd = await review_settings(session, reviewer)
    tools = await connectors.tools_for(
        session, reviewer.connectors, "\n".join([pr.title, pr.head.ref, pr.body or ""])
    )
    token = await github.installation_token(ctx.creds, ctx.installation.github_id)
    reviewer_files = await bundle.build(
        token=token, reviewers_repo=reviewers_repo.full_name, reviewer=reviewer
    )

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
        reviewer_files.skills,
        run.note,
        since=since,
        new_files=new_files,
        hints=[t.hint for t in tools],
    )
    run.model = model
    # Kept for publishing: which commit this review built on, and the PR's base at the time.
    run.result = {"since": since, "base_sha": pr.base.sha}
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
        connectors=tools,
    )
