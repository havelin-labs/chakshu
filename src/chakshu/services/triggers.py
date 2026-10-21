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
from chakshu.services import github, orgs, runs
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
    note: str | None = None
    event: str | None = None  # PR action for automatic runs


@dataclass
class Outcome:
    queued: list[str] = field(default_factory=list)
    already: list[str] = field(default_factory=list)
    refused: str | None = None  # message for the requester when nothing was queued on purpose

    @property
    def ok(self) -> bool:
        return self.refused is None


async def _caller_teams(
    creds: AppCredentials, installation: Installation, login: str, candidates: list[Reviewer]
) -> set[str] | None:
    """Teams of the caller among the candidates' owners. None means "may run any"."""
    if installation.account_type == "User":
        return None
    org = installation.account_login
    if await orgs.org_role(creds, installation.github_id, org, login) == "admin":
        return None
    teams = {r.owner_team for r in candidates}
    return {
        team for team in teams if await orgs.is_team_member(creds, installation.github_id, org, team, login)
    }


async def request_review(session: AsyncSession, creds: AppCredentials, req: ReviewRequest) -> Outcome:
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

    files = [
        f.filename
        async for f in client.rest.paginate(client.rest.pulls.async_list_files, owner, name, req.pr_number)
    ]
    reviewers = list(
        (await session.scalars(select(Reviewer).where(Reviewer.installation_id == req.installation.id))).all()
    )
    candidates = selection.applicable(reviewers, req.repo.full_name, files, event=req.event)
    if req.requester:
        teams = await _caller_teams(creds, req.installation, req.requester, candidates)
        chosen = selection.for_caller(candidates, teams) or selection.fallback(reviewers, req.repo.full_name)
        if not chosen:
            owners = [(r.name, f"{req.installation.account_login}/{r.owner_team}") for r in candidates]
            return Outcome(refused=messages.nothing_matched(req.requester, owners))
    else:
        chosen = candidates

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
            note=req.note,
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


async def clear_team_request(creds: AppCredentials, req: ReviewRequest) -> None:
    """Remove the pending chakshu team request so the PR doesn't wait on it."""
    owner, name = req.repo.full_name.split("/", 1)
    client = github.installation_client(creds, req.installation.github_id)
    await client.rest.pulls.async_remove_requested_reviewers(
        owner, name, req.pr_number, reviewers=[], team_reviewers=[mentions.HANDLE_TEAM]
    )
