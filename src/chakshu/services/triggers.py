"""Turn "someone (or something) wants a review" into queued runs.

Every trigger ends up here: a comment mention, a review request for the
chakshu team, an automatic PR event, or the portal's Review button.
"""

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.db.models import Installation, Repo, Reviewer
from chakshu.helpers import mentions, messages, selection
from chakshu.services import github, orgs, runs, spend
from chakshu.services.github import AppCredentials

log = logging.getLogger(__name__)


@dataclass
class ReviewRequest:
    installation: Installation
    repo: Repo
    pr_number: int
    trigger: str  # mention | review_requested | auto | portal
    source_id: str  # what caused it (comment id, delivery id), part of the run id
    requester: str | None = None  # GitHub login; None for automatic runs
    note: str | None = None  # for mentions, may start with reviewer names
    event: str | None = None  # PR action for automatic runs
    reviewers: list[str] | None = None  # names picked in the portal


@dataclass
class Outcome:
    queued: list[str] = field(default_factory=list)
    already: list[str] = field(default_factory=list)
    refused: str | None = None  # message for the requester when nothing was queued on purpose

    @property
    def ok(self) -> bool:
        return self.refused is None


async def request_review(session: AsyncSession, creds: AppCredentials, req: ReviewRequest) -> Outcome:
    budget = await spend.current(session)
    if budget.over_cap:
        return Outcome(
            refused=messages.over_budget(req.requester, float(budget.month_to_date), float(budget.cap))
        )

    owner, name = req.repo.full_name.split("/", 1)
    client = github.installation_client(creds, req.installation.github_id)
    pr = (await client.rest.pulls.async_get(owner, name, req.pr_number)).parsed_data
    if pr.state != "open":
        return Outcome(refused="This pull request is closed.")

    if req.requester:
        permission = await orgs.repo_permission(
            creds, req.installation.github_id, req.repo.full_name, req.requester
        )
        if not orgs.can_write(permission):
            return Outcome(refused=messages.needs_write_access(req.requester))

    query = select(Reviewer).where(Reviewer.installation_id == req.installation.id).order_by(Reviewer.name)
    reviewers = list((await session.scalars(query)).all())
    available = [r.name for r in reviewers if not r.errors]
    note = req.note
    if req.reviewers:
        chosen, unknown = selection.by_names(reviewers, req.reviewers)
        if unknown:
            return Outcome(refused=messages.unknown_reviewers(req.requester, unknown, available))
    else:
        # Named reviewers run whatever their repos and paths say; the rest of the note goes to them.
        chosen, note = selection.pick_named(reviewers, note) if req.requester and note else ([], note)

    if not chosen:
        files = [
            f.filename
            async for f in client.rest.paginate(
                client.rest.pulls.async_list_files, owner=owner, repo=name, pull_number=req.pr_number
            )
        ]
        chosen = selection.applicable(reviewers, req.repo.full_name, files, event=req.event)
        if req.requester and not chosen:
            chosen = selection.fallback(reviewers, req.repo.full_name)
            if not chosen:
                handle = mentions.handle(req.installation.account_login)
                return Outcome(refused=messages.nothing_matched(req.requester, handle, available))

    outcome = Outcome()
    for reviewer in chosen:
        added = await runs.enqueue(
            session,
            creds,
            repo=req.repo,
            reviewer=reviewer,
            pr_number=req.pr_number,
            pr_title=pr.title,
            head_sha=pr.head.sha,
            trigger=req.trigger,
            source_id=req.source_id,
            requested_by=req.requester,
            note=note or None,
            pr_author=pr.user.login if pr.user else None,
        )
        (outcome.queued if added else outcome.already).append(reviewer.name)
    log.info(
        "%s#%s %s by %s: queued %s, already %s",
        req.repo.full_name,
        req.pr_number,
        req.trigger,
        req.requester or "-",
        outcome.queued,
        outcome.already,
    )
    return outcome


async def reply(creds: AppCredentials, req: ReviewRequest, body: str) -> None:
    owner, name = req.repo.full_name.split("/", 1)
    client = github.installation_client(creds, req.installation.github_id)
    await client.rest.issues.async_create_comment(owner, name, req.pr_number, body=body)


async def clear_team_request(
    creds: AppCredentials, installation_id: int, full_name: str, number: int
) -> None:
    """Remove the pending chakshu team request so the PR doesn't wait on it."""
    owner, name = full_name.split("/", 1)
    client = github.installation_client(creds, installation_id)
    await client.rest.pulls.async_remove_requested_reviewers(
        owner, name, number, reviewers=[], team_reviewers=[mentions.HANDLE_TEAM]
    )
