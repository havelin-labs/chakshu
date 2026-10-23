"""Fill in who opened the pull request for runs queued before Chakshu recorded it.

The worker calls `backfill` on each maintenance pass, so it only ever does a
few GitHub lookups at a time. A PR GitHub no longer shows gets an empty author,
so it isn't asked about again.
"""

import logging

from githubkit.exception import RequestFailed
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.db.models import Installation, Repo, Run
from chakshu.services import github
from chakshu.services.github import AppCredentials

log = logging.getLogger(__name__)

BATCH = 20
UNKNOWN = ""


async def backfill(session: AsyncSession, creds: AppCredentials, batch: int = BATCH) -> int:
    """Look up the author of up to `batch` pull requests. Returns how many PRs were filled."""
    rows = (
        await session.execute(
            select(Run.repo_id, Run.pr_number, Repo.full_name, Installation.github_id)
            .join(Repo, Run.repo_id == Repo.id)
            .join(Installation, Repo.installation_id == Installation.id)
            .where(Run.pr_author.is_(None))
            .group_by(Run.repo_id, Run.pr_number, Repo.full_name, Installation.github_id)
            .limit(batch)
        )
    ).all()
    for repo_id, number, full_name, installation_id in rows:
        owner, name = full_name.split("/", 1)
        client = github.installation_client(creds, installation_id)
        try:
            pr = (await client.rest.pulls.async_get(owner, name, number)).parsed_data
            author = pr.user.login if pr.user else UNKNOWN
        except RequestFailed as exc:
            if exc.response.status_code != 404:
                raise
            author = UNKNOWN
        await session.execute(
            update(Run)
            .where(Run.repo_id == repo_id, Run.pr_number == number, Run.pr_author.is_(None))
            .values(pr_author=author)
        )
    await session.commit()
    if rows:
        log.info("Filled in pull request authors for %s PR(s)", len(rows))
    return len(rows)
