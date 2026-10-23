"""Keep each repository's Actions secrets in step with Chakshu's Claude credential.

Repository secrets rather than organization ones: on GitHub Free, organization
secrets don't reach private repositories. GitHub only accepts secrets sealed
with the repository's public key (libsodium sealed box).
"""

import asyncio
import logging
from base64 import b64encode
from dataclasses import dataclass, field

from githubkit import GitHub
from githubkit.exception import RequestFailed
from nacl import encoding, public
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.db.models import Installation, Repo
from chakshu.helpers import workflow
from chakshu.services import github, model_access
from chakshu.services.github import AppCredentials

log = logging.getLogger(__name__)

CONCURRENCY = 8
# Credential (environment variable the runner reads) -> repository secret the workflow passes it from.
SECRET_FOR = {
    model_access.API_KEY_ENV: workflow.API_KEY_SECRET,
    model_access.TOKEN_ENV: workflow.TOKEN_SECRET,
}


@dataclass
class SyncReport:
    synced: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)


def seal(public_key: str, value: str) -> str:
    """Encrypt a secret for GitHub with the repository's base64 public key."""
    box = public.SealedBox(public.PublicKey(public_key.encode(), encoding.Base64Encoder()))
    return b64encode(box.encrypt(value.encode())).decode()


async def wanted(session: AsyncSession) -> dict[str, str | None]:
    """Secret name -> value it should hold (None: it shouldn't exist)."""
    creds = await model_access.credentials(session)
    return {secret: creds[env] for env, secret in SECRET_FOR.items()}


async def sync_repo(client: GitHub, full_name: str, values: dict[str, str | None]) -> None:
    owner, name = full_name.split("/", 1)
    key = (await client.rest.actions.async_get_repo_public_key(owner, name)).parsed_data
    for secret, value in values.items():
        if value:
            await client.rest.actions.async_create_or_update_repo_secret(
                owner, name, secret, encrypted_value=seal(key.key, value), key_id=key.key_id
            )
            continue
        try:
            await client.rest.actions.async_delete_repo_secret(owner, name, secret)
        except RequestFailed as exc:
            if exc.response.status_code != 404:
                raise


async def present(client: GitHub, full_name: str) -> dict[str, bool]:
    """Which Chakshu secrets the repository has. GitHub never shows their values."""
    owner, name = full_name.split("/", 1)
    found = {}
    for secret in SECRET_FOR.values():
        try:
            await client.rest.actions.async_get_repo_secret(owner, name, secret)
            found[secret] = True
        except RequestFailed as exc:
            if exc.response.status_code != 404:
                raise
            found[secret] = False
    return found


async def sync_all(session: AsyncSession, creds: AppCredentials) -> SyncReport:
    """Update the secrets in every enabled repository. One repo failing doesn't stop the others."""
    values = await wanted(session)
    rows = (
        await session.execute(
            select(Repo, Installation)
            .join(Installation, Repo.installation_id == Installation.id)
            .where(Repo.enabled.is_(True), Installation.suspended.is_(False))
        )
    ).all()
    clients = {i.github_id: github.installation_client(creds, i.github_id) for _, i in rows}
    report = SyncReport()
    limit = asyncio.Semaphore(CONCURRENCY)

    async def one(repo: Repo, installation: Installation) -> None:
        async with limit:
            try:
                await sync_repo(clients[installation.github_id], repo.full_name, values)
                report.synced.append(repo.full_name)
            except RequestFailed as exc:
                log.warning("Couldn't update Actions secrets in %s: %s", repo.full_name, exc)
                report.failed[repo.full_name] = f"GitHub said {exc.response.status_code}"

    await asyncio.gather(*(one(repo, installation) for repo, installation in rows))
    report.synced.sort()
    return report
