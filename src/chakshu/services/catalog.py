"""Mirror each org's reviewers repo into the `reviewers` table."""

import asyncio
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.core import ids
from chakshu.core.config import get_settings
from chakshu.db.models import Installation, Repo, Reviewer
from chakshu.db.upsert import upsert
from chakshu.helpers import git
from chakshu.helpers.catalog import ParsedReviewer, load_catalog
from chakshu.services import github
from chakshu.services import settings_store as store
from chakshu.services.github import AppCredentials
from chakshu.services.settings_store import Key

log = logging.getLogger(__name__)


@dataclass
class SyncResult:
    account: str
    repo: str
    found: bool
    sha: str | None = None
    reviewers: int = 0
    broken: int = 0


def clone_url(full_name: str) -> str:
    return f"{get_settings().github_url}/{full_name}.git"


async def reviewers_repo(session: AsyncSession, installation: Installation) -> Repo | None:
    name = await store.get(session, Key.REVIEWERS_REPO)
    full_name = f"{installation.account_login}/{name}".lower()
    return await session.scalar(
        select(Repo).where(Repo.installation_id == installation.id, func.lower(Repo.full_name) == full_name)
    )


def _row(creds: AppCredentials, installation: Installation, sha: str, parsed: ParsedReviewer) -> dict:
    spec = parsed.spec
    return {
        "id": ids.eid(creds.namespace, "reviewer", installation.account_github_id, parsed.name),
        "installation_id": installation.id,
        "name": parsed.name,
        "product": spec.product if spec else None,
        "description": spec.description if spec else None,
        "owner_team": spec.owner_team if spec else "",
        "model": spec.model if spec else None,
        "repos": spec.repos if spec else [],
        "paths": spec.paths if spec else [],
        "auto": list(spec.auto) if spec else [],
        "skills": spec.skills if spec else [],
        "limits": spec.limits.model_dump() if spec else {},
        "rules": spec.rules if spec else None,
        "fail_check_on": spec.fail_check_on if spec else None,
        "connectors": spec.connectors if spec else [],
        "source_path": parsed.source_path,
        "source_sha": sha,
        "errors": parsed.errors,
    }


async def sync_installation(
    session: AsyncSession, creds: AppCredentials, installation: Installation
) -> SyncResult:
    repo = await reviewers_repo(session, installation)
    result = SyncResult(
        account=installation.account_login,
        repo=repo.full_name
        if repo
        else f"{installation.account_login}/{await store.get(session, Key.REVIEWERS_REPO)}",
        found=repo is not None,
    )
    if repo is None:
        await session.execute(delete(Reviewer).where(Reviewer.installation_id == installation.id))
        return result

    owner, name = repo.full_name.split("/", 1)
    client = github.installation_client(creds, installation.github_id)
    branch = (await client.rest.repos.async_get_branch(owner, name, repo.default_branch)).parsed_data
    sha = branch.commit.sha
    token = await github.installation_token(creds, installation.github_id)

    with tempfile.TemporaryDirectory(prefix="chakshu-catalog-") as tmp:
        root = await git.checkout(clone_url(repo.full_name), sha, Path(tmp) / "repo", token)
        parsed = await asyncio.to_thread(load_catalog, root)

    rows = [_row(creds, installation, sha, p) for p in parsed]
    await upsert(session, Reviewer, rows)
    await session.execute(
        delete(Reviewer).where(
            Reviewer.installation_id == installation.id,
            Reviewer.name.not_in([r["name"] for r in rows] or [""]),
        )
    )
    result.sha = sha
    result.reviewers = len(rows)
    result.broken = sum(1 for p in parsed if p.errors)
    log.info(
        "Synced %s at %s: %s reviewers, %s with errors", repo.full_name, sha[:7], len(rows), result.broken
    )
    return result


async def sync_all(session: AsyncSession, creds: AppCredentials) -> list[SyncResult]:
    installs = (await session.scalars(select(Installation).where(Installation.suspended.is_(False)))).all()
    return [await sync_installation(session, creds, install) for install in installs]
