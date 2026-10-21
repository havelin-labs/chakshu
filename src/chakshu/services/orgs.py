"""Who belongs to which org and team, asked as the app installation.

Uses the app's "members: read" permission, so answers don't depend on what a
user's own token can see.
"""

from githubkit.exception import RequestFailed

from chakshu.services import github
from chakshu.services.github import AppCredentials


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


async def is_team_member(
    creds: AppCredentials, installation_id: int, org: str, team: str, login: str
) -> bool:
    client = github.installation_client(creds, installation_id)
    try:
        membership = (
            await client.rest.teams.async_get_membership_for_user_in_org(org, team, login)
        ).parsed_data
    except RequestFailed as exc:
        if exc.response.status_code in (403, 404):
            return False
        raise
    return membership.state == "active"


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
