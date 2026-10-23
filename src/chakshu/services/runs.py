"""Create runs. One run is one reviewer reviewing one PR at one commit, or answering one reply.

The work key identifies the work itself (PR, head commit, reviewer commit,
reviewer). A second request for the same work is dropped while the first is
queued, running (here or in Actions) or done; a new push or a reviewer edit makes a new key.
A reply run's work is the reply comment it answers.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.core import ids
from chakshu.db.models import Repo, Reviewer, Run, RunStatus
from chakshu.services.github import AppCredentials

LIVE_OR_DONE = (RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.DISPATCHED, RunStatus.SUCCEEDED)


def pr_key(ns: uuid.UUID, repo: Repo, pr_number: int) -> uuid.UUID:
    return ids.eid(ns, "pr", repo.github_id, pr_number)


def work_key(ns: uuid.UUID, repo: Repo, pr_number: int, head_sha: str, reviewer: Reviewer) -> uuid.UUID:
    return ids.eid(ns, "work", pr_key(ns, repo, pr_number), head_sha, reviewer.source_sha, reviewer.id)


def reply_key(ns: uuid.UUID, repo: Repo, comment_id: int) -> uuid.UUID:
    return ids.eid(ns, "reply", repo.github_id, comment_id)


async def last_reviewed_head(session: AsyncSession, run: Run) -> str | None:
    """Head commit of this reviewer's latest successful review of the same PR at another commit."""
    return await session.scalar(
        select(Run.head_sha)
        .where(
            Run.repo_id == run.repo_id,
            Run.pr_number == run.pr_number,
            Run.reviewer_id == run.reviewer_id,
            Run.status == RunStatus.SUCCEEDED.value,
            Run.head_sha != run.head_sha,
            Run.reply_to.is_(None),
        )
        .order_by(Run.finished_at.desc())
        .limit(1)
    )


async def enqueue(
    session: AsyncSession,
    creds: AppCredentials,
    *,
    repo: Repo,
    reviewer: Reviewer,
    pr_number: int,
    pr_title: str,
    head_sha: str,
    trigger: str,
    source_id: str,
    requested_by: str | None,
    note: str | None,
    reply_to: int | None = None,
) -> bool:
    """Queue a run. False if the same work is already queued, running or done.

    For a reply run, `source_id` is the reply's comment ID and `reply_to` the thread's first comment.
    """
    ns = creds.namespace
    if reply_to:
        key = reply_key(ns, repo, int(source_id))
    else:
        key = work_key(ns, repo, pr_number, head_sha, reviewer)
    existing = await session.scalar(
        select(Run.id).where(Run.work_key == key, Run.status.in_([s.value for s in LIVE_OR_DONE])).limit(1)
    )
    if existing:
        return False
    stmt = (
        insert(Run)
        .values(
            id=ids.eid(ns, "run", key, trigger, source_id),
            work_key=key,
            repo_id=repo.id,
            reviewer_id=reviewer.id,
            pr_number=pr_number,
            pr_title=pr_title[:500],
            head_sha=head_sha,
            reviewer_sha=reviewer.source_sha,
            trigger=trigger,
            requested_by=requested_by,
            note=(note or None) and note[:2000],
            status=RunStatus.QUEUED.value,
            reply_to=reply_to,
        )
        .on_conflict_do_nothing(index_elements=[Run.id])
        .returning(Run.id)
    )
    return (await session.scalar(stmt)) is not None


async def answers_in_thread(session: AsyncSession, repo: Repo, root_id: int) -> int:
    """Reply runs for one thread that are queued, running or done."""
    return await session.scalar(
        select(func.count())
        .select_from(Run)
        .where(
            Run.repo_id == repo.id,
            Run.reply_to == root_id,
            Run.status.in_([s.value for s in LIVE_OR_DONE]),
        )
    )
