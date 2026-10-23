"""Who belongs to which org, asked as the app installation, and the org's chakshu team.

Uses the app's "members" permission, so answers don't depend on what a
user's own token can see.
"""

from typing import Literal

from githubkit.exception import RequestFailed
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.db.models import Installation, Repo
from chakshu.helpers import mentions
from chakshu.services import github
from chakshu.services.github import AppCredentials

TeamState = Literal["created", "exists"]


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
