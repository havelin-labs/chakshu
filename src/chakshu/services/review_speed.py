"""Review speed: how long pull requests wait for a person's review and for merge.

The `pull_request` and `pull_request_review` webhooks record when each PR was
opened, left draft, got its first review from someone other than its author,
and merged. Bot-authored PRs and reviews by bots (Chakshu included) are left
out. PRs Chakshu reviewed are compared with the ones it didn't, per repository.
That's a cohort comparison: the two groups differ in more than Chakshu, so it
doesn't say Chakshu caused a difference.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import and_, case, exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from chakshu.db.models import PrEvent, Repo, Run, RunStatus
from chakshu.services.analytics import REPLY, Filters

REVIEW_STATES = frozenset({"approved", "changes_requested", "commented"})
SMALL_SAMPLE = 5  # fewer PRs than this in a cohort is too few to read much into


def _time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _is_bot(user: dict | None) -> bool:
    return not user or user.get("type") == "Bot"


async def record(
    session: AsyncSession, repo_id: uuid.UUID, number: int, kind: str, at: datetime, actor: str | None
) -> None:
    """Keep the earliest time seen for this PR and kind, whatever order the webhooks arrive in."""
    stmt = insert(PrEvent).values(
        id=uuid.uuid4(), repo_id=repo_id, pr_number=number, kind=kind, at=at, actor=actor
    )
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=["repo_id", "pr_number", "kind"],
            set_={"at": func.least(PrEvent.at, stmt.excluded.at)},
        )
    )


async def from_pull_request(session: AsyncSession, repo: Repo, action: str | None, pr: dict) -> None:
    """From any `pull_request` webhook. The caller commits."""
    author = pr.get("user")
    if _is_bot(author) or not pr.get("created_at"):
        return
    await record(session, repo.id, pr["number"], "opened", _time(pr["created_at"]), author["login"])
    if action == "ready_for_review":
        at = _time(pr.get("updated_at")) or datetime.now(UTC)
        await record(session, repo.id, pr["number"], "ready", at, author["login"])
    if action == "closed" and pr.get("merged_at"):
        await record(session, repo.id, pr["number"], "merged", _time(pr["merged_at"]), None)


async def from_review(session: AsyncSession, repo: Repo, review: dict, pr: dict) -> None:
    """From a submitted `pull_request_review`. The caller commits."""
    reviewer, author = review.get("user"), pr.get("user")
    if _is_bot(reviewer) or _is_bot(author) or review.get("state", "").lower() not in REVIEW_STATES:
        return
    if reviewer["login"].lower() == author["login"].lower() or not review.get("submitted_at"):
        return
    await from_pull_request(session, repo, None, pr)
    await record(
        session, repo.id, pr["number"], "first_review", _time(review["submitted_at"]), reviewer["login"]
    )


def _stats(hours, reviewed):
    """n, median and P90 of `hours` for one cohort."""

    def pick(fn):
        return fn.within_group(hours).filter(reviewed)

    return (
        func.count(hours).filter(reviewed),
        pick(func.percentile_cont(0.5)),
        pick(func.percentile_cont(0.9)),
    )


def _cohort(row, prefix: str) -> dict:
    def metric(name: str) -> dict:
        n = getattr(row, f"{prefix}_{name}_n")
        return {
            "n": n,
            "median_hours": _round(getattr(row, f"{prefix}_{name}_median")),
            "p90_hours": _round(getattr(row, f"{prefix}_{name}_p90")),
            "small_sample": n < SMALL_SAMPLE,
        }

    return {"prs": getattr(row, f"{prefix}_prs"), "first_review": metric("review"), "merge": metric("merge")}


def _round(value: float | None) -> float | None:
    return None if value is None else round(float(value), 2)


async def speed(session: AsyncSession, f: Filters) -> list[dict]:
    """Per repository, PRs opened in the period: time to first human review and to merge, by cohort."""
    opened, ready, review, merged = (aliased(PrEvent) for _ in range(4))

    def kind(alias, name: str):
        return and_(alias.repo_id == opened.repo_id, alias.pr_number == opened.pr_number, alias.kind == name)

    start = func.coalesce(ready.at, opened.at)
    by_chakshu = exists().where(
        Run.repo_id == opened.repo_id,
        Run.pr_number == opened.pr_number,
        Run.status == RunStatus.SUCCEEDED.value,
        Run.trigger != REPLY,
    )
    prs = (
        select(
            opened.repo_id.label("repo_id"),
            by_chakshu.label("reviewed"),
            (func.extract("epoch", review.at - start) / 3600).label("to_review"),
            (func.extract("epoch", merged.at - start) / 3600).label("to_merge"),
        )
        .select_from(opened)
        .outerjoin(ready, kind(ready, "ready"))
        .outerjoin(review, kind(review, "first_review"))
        .outerjoin(merged, kind(merged, "merged"))
        .where(opened.kind == "opened", opened.at >= f.start, opened.at < f.end)
    )
    if f.repo_id:
        prs = prs.where(opened.repo_id == f.repo_id)
    prs = prs.subquery()
    # A review or merge before the PR left draft counts as no wait. (greatest() would turn NULL into 0.)
    to_review, to_merge = (case((hours < 0, 0), else_=hours) for hours in (prs.c.to_review, prs.c.to_merge))
    columns = []
    for prefix, cohort in (("yes", prs.c.reviewed), ("no", ~prs.c.reviewed)):
        r_n, r_med, r_p90 = _stats(to_review, cohort)
        m_n, m_med, m_p90 = _stats(to_merge, cohort)
        columns += [
            func.count().filter(cohort).label(f"{prefix}_prs"),
            r_n.label(f"{prefix}_review_n"),
            r_med.label(f"{prefix}_review_median"),
            r_p90.label(f"{prefix}_review_p90"),
            m_n.label(f"{prefix}_merge_n"),
            m_med.label(f"{prefix}_merge_median"),
            m_p90.label(f"{prefix}_merge_p90"),
        ]
    stmt = (
        select(Repo.id, Repo.full_name, *columns)
        .select_from(prs)
        .join(Repo, Repo.id == prs.c.repo_id)
        .group_by(Repo.id, Repo.full_name)
        .order_by(Repo.full_name)
    )
    return [
        {
            "repo_id": str(row.id),
            "repo": row.full_name,
            "reviewed": _cohort(row, "yes"),
            "not_reviewed": _cohort(row, "no"),
        }
        for row in (await session.execute(stmt)).all()
    ]
