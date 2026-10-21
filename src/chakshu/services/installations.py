"""Keep the installations and repos tables in step with GitHub."""

import logging
import uuid

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.core import ids
from chakshu.db.models import Installation, Repo
from chakshu.db.upsert import upsert
from chakshu.services import github
from chakshu.services.github import AppCredentials

log = logging.getLogger(__name__)


async def sync_all(session: AsyncSession, creds: AppCredentials) -> int:
    """Sync every installation of the app. Returns how many there are."""
    app = github.app_client(creds)
    seen: list[int] = []
    async for installation in app.rest.paginate(app.rest.apps.async_list_installations):
        await sync_installation(session, creds, installation.id)
        seen.append(installation.id)
    await session.execute(delete(Installation).where(Installation.github_id.not_in(seen or [0])))
    return len(seen)


async def sync_installation(session: AsyncSession, creds: AppCredentials, installation_id: int) -> uuid.UUID:
    ns = creds.namespace
    app = github.app_client(creds)
    installation = (await app.rest.apps.async_get_installation(installation_id)).parsed_data
    account = installation.account
    row_id = ids.eid(ns, "installation", installation.id)
    suspended = installation.suspended_at is not None
    await upsert(
        session,
        Installation,
        {
            "id": row_id,
            "github_id": installation.id,
            "account_github_id": account.id,
            "account_login": getattr(account, "login", None) or account.slug,
            "account_type": getattr(account, "type", None) or "Organization",
            "suspended": suspended,
        },
    )
    if suspended:
        return row_id

    client = github.installation_client(creds, installation.id)
    repos = [
        {
            "id": ids.eid(ns, "repo", repo.id),
            "github_id": repo.id,
            "installation_id": row_id,
            "full_name": repo.full_name,
            "default_branch": repo.default_branch,
            "private": repo.private,
        }
        async for repo in client.rest.paginate(
            client.rest.apps.async_list_repos_accessible_to_installation,
            map_func=lambda r: r.parsed_data.repositories,
        )
    ]
    await upsert(session, Repo, repos)
    await session.execute(
        delete(Repo).where(
            Repo.installation_id == row_id, Repo.github_id.not_in([r["github_id"] for r in repos] or [0])
        )
    )
    log.info("Synced installation %s (%s repos)", installation.id, len(repos))
    return row_id


async def remove_installation(session: AsyncSession, installation_id: int) -> None:
    await session.execute(delete(Installation).where(Installation.github_id == installation_id))
