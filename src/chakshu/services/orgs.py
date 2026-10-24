"""Who belongs to which org, asked as the app installation, and the org's chakshu team.

Uses the app's "members" permission, so answers don't depend on what a
user's own token can see.
"""

import logging
from dataclasses import dataclass, field
from typing import Literal

from githubkit.exception import RequestFailed
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.db.models import Installation, Repo, Reviewer
from chakshu.helpers import mentions
from chakshu.services import github
from chakshu.services.github import AppCredentials

log = logging.getLogger(__name__)

TeamState = Literal["created", "exists"]


@dataclass
class ReviewerTeams:
    """What syncing one org's reviewer teams did."""

    created: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)
    error: str | None = None


async def org_role(creds: AppCredentials, installation_id: int, org: str, login: str) -> str | None:
    """'admin' or 'member' for active members of `org`, otherwise None."""
    client = github.installation_client(creds, installation_id)
    try:
        membership = (await client.rest.orgs.async_get_membership_for_user(org, login)).parsed_data
    except RequestFailed as exc:
        if exc.response.status_code in (403, 404):
            return None
        raise
    return membership.role if membership.state == "active" else None


async def repo_permission(creds: AppCredentials, installation_id: int, full_name: str, login: str) -> str:
    """The user's permission on a repo: admin, maintain, write, triage, read or none."""
    owner, repo = full_name.split("/", 1)
    client = github.installation_client(creds, installation_id)
    try:
        resp = await client.rest.repos.async_get_collaborator_permission_level(owner, repo, login)
    except RequestFailed as exc:
        if exc.response.status_code in (403, 404):
            return "none"
        raise
    return resp.parsed_data.role_name or resp.parsed_data.permission


def can_write(permission: str) -> bool:
    return permission in {"admin", "maintain", "write"}


async def ensure_review_team(
    creds: AppCredentials, installation_id: int, org: str, repo_names: list[str]
) -> TeamState:
    """Create the empty team people mention (@org/chakshu), with read access to these repos.

    An existing team is left as it is: changing its repos would need the
    administration permission, which Chakshu doesn't ask for.
    """
    client = github.installation_client(creds, installation_id)
    try:
        await client.rest.teams.async_get_by_name(org, mentions.HANDLE_TEAM)
        return "exists"
    except RequestFailed as exc:
        if exc.response.status_code != 404:
            raise
    await client.rest.teams.async_create(
        org,
        name=mentions.HANDLE_TEAM,
        description="Mention or request this team to ask Chakshu for a review. Keep it empty.",
        repo_names=repo_names,
        privacy="closed",  # visible to the whole org, so anyone can mention it
        notification_setting="notifications_disabled",
    )
    return "created"


async def _org_installs(session: AsyncSession) -> list[Installation]:
    return list(
        (
            await session.scalars(
                select(Installation).where(
                    Installation.account_type == "Organization", Installation.suspended.is_(False)
                )
            )
        ).all()
    )


async def sync_reviewer_teams(
    session: AsyncSession, creds: AppCredentials, install: Installation
) -> ReviewerTeams:
    """Give each healthy reviewer a child team of chakshu, and remove the teams of reviewers that are gone.

    Child teams inherit the parent's repository access, so each one appears in a pull
    request's Reviewers box without Chakshu needing the administration permission.
    Only teams carrying Chakshu's marker are ever removed.
    """
    result = ReviewerTeams()
    if install.account_type != "Organization" or install.suspended:
        return result
    org = install.account_login
    client = github.installation_client(creds, install.github_id)
    try:
        try:
            parent = (await client.rest.teams.async_get_by_name(org, mentions.HANDLE_TEAM)).parsed_data
        except RequestFailed as exc:
            if exc.response.status_code != 404:
                raise
            repos = await session.scalars(select(Repo.full_name).where(Repo.installation_id == install.id))
            await ensure_review_team(creds, install.github_id, org, sorted(repos.all()))
            parent = (await client.rest.teams.async_get_by_name(org, mentions.HANDLE_TEAM)).parsed_data
        children = {
            team.slug: team
            async for team in client.rest.paginate(
                client.rest.teams.async_list_child_in_org,
                org=org,
                team_slug=mentions.HANDLE_TEAM,
                per_page=100,
            )
        }
        names = (
            await session.scalars(
                select(Reviewer.name).where(Reviewer.installation_id == install.id, Reviewer.errors == [])
            )
        ).all()
        wanted = {mentions.reviewer_team(name): name for name in names}
        for slug, name in sorted(wanted.items()):
            if slug in children:
                result.kept.append(slug)
                continue
            await client.rest.teams.async_create(
                org,
                name=slug,
                description=(
                    f"Request this team to run Chakshu's {name} reviewer. Keep it empty. "
                    + mentions.TEAM_MARKER
                ),
                parent_team_id=parent.id,
                privacy="closed",  # child teams must be closed
                notification_setting="notifications_disabled",
            )
            result.created.append(slug)
        for slug, team in sorted(children.items()):
            ours = slug.startswith(mentions.REVIEWER_TEAM_PREFIX) and mentions.TEAM_MARKER in (
                team.description or ""
            )
            if ours and slug not in wanted:
                await client.rest.teams.async_delete_in_org(org, slug)
                result.removed.append(slug)
    except RequestFailed as exc:
        # 403 usually means the app or the installation lacks members: write.
        result.error = f"failed ({exc.response.status_code})"
        log.warning("Couldn't sync reviewer teams in %s: %s", org, result.error)
    return result


async def sync_all_reviewer_teams(session: AsyncSession, creds: AppCredentials) -> dict[str, ReviewerTeams]:
    return {
        install.account_login: await sync_reviewer_teams(session, creds, install)
        for install in await _org_installs(session)
    }


async def ensure_review_teams(session: AsyncSession, creds: AppCredentials) -> dict[str, str]:
    """Run ensure_review_team for each installed organization: login -> created, exists or failed (status)."""
    installs = (
        await session.scalars(
            select(Installation).where(
                Installation.account_type == "Organization", Installation.suspended.is_(False)
            )
        )
    ).all()
    results: dict[str, str] = {}
    for install in installs:
        repos = await session.scalars(select(Repo.full_name).where(Repo.installation_id == install.id))
        try:
            results[install.account_login] = await ensure_review_team(
                creds, install.github_id, install.account_login, sorted(repos.all())
            )
        except RequestFailed as exc:
            # 403 usually means the app or the installation lacks members: write.
            results[install.account_login] = f"failed ({exc.response.status_code})"
    return results
