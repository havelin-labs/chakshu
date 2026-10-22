"""Remember posted findings, record their outcomes and summarise them per skill."""

import logging
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from githubkit import GitHub
from sqlalchemy import case, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.db.models import FindingOutcome, Installation, PostedFinding, Reviewer, Run
from chakshu.helpers.findings import Identified
from chakshu.services import threads

log = logging.getLogger(__name__)


async def record_posted(session: AsyncSession, run: Run, items: Iterable[Identified]) -> None:
    """Remember inline findings. A finding posted before keeps its first record."""
    rows = [
        {
            "id": item.id,
            "run_id": run.id,
            "reviewer_id": run.reviewer_id,
            "skill": item.finding.skill,
            "severity": item.finding.severity,
            "category": item.finding.category,
        }
        for item in items
    ]
    if rows:
        await session.execute(
            insert(PostedFinding).values(rows).on_conflict_do_nothing(index_elements=["id"])
        )


async def record_outcomes(session: AsyncSession, fixed: set[str], dismissed: set[str]) -> None:
    """Close open findings. An outcome, once recorded, isn't changed by later scans."""
    for outcome, ids in ((FindingOutcome.FIXED, fixed), (FindingOutcome.DISMISSED, dismissed)):
        if ids:
            await session.execute(
                update(PostedFinding)
                .where(
                    PostedFinding.id.in_([uuid.UUID(i) for i in ids]),
                    PostedFinding.outcome == FindingOutcome.OPEN.value,
                )
                .values(outcome=outcome.value, closed_at=datetime.now(UTC))
            )


async def sweep(
    session: AsyncSession, client: GitHub, full_name: str, number: int, still_found: set[str]
) -> int:
    """Resolve finished Chakshu threads on a PR and record outcomes. Returns how many it resolved.

    Tidy-up only: GitHub errors are logged, never raised.
    """
    try:
        scan = await threads.tidy(client, full_name, number, still_found)
    except Exception:  # noqa: BLE001
        log.warning("Couldn't check review threads on %s#%s", full_name, number, exc_info=True)
        return 0
    await record_outcomes(session, scan.fixed, scan.dismissed)
    return len(scan.resolve)


def _count(outcome: FindingOutcome):
    return func.count(case((PostedFinding.outcome == outcome.value, 1)))


async def per_skill(session: AsyncSession, days: int) -> list[dict]:
    since = datetime.now(UTC) - timedelta(days=days)
    rows = (
        await session.execute(
            select(
                Installation.account_login,
                Reviewer.name,
                PostedFinding.skill,
                func.count().label("posted"),
                _count(FindingOutcome.FIXED).label("fixed"),
                _count(FindingOutcome.DISMISSED).label("dismissed"),
                _count(FindingOutcome.OPEN).label("open"),
            )
            .join(Reviewer, PostedFinding.reviewer_id == Reviewer.id)
            .join(Installation, Reviewer.installation_id == Installation.id)
            .where(PostedFinding.created_at >= since)
            .group_by(Installation.account_login, Reviewer.name, PostedFinding.skill)
            .order_by(Installation.account_login, Reviewer.name, func.count().desc())
        )
    ).all()
    stats = []
    for account, reviewer, skill, posted, fixed, dismissed, still_open in rows:
        closed = fixed + dismissed
        stats.append(
            {
                "account": account,
                "reviewer": reviewer,
                "skill": skill or "(no skill named)",
                "posted": posted,
                "fixed": fixed,
                "dismissed": dismissed,
                "open": still_open,
                # Of the findings that got a verdict, how many were acted on.
                "fix_rate": round(fixed / closed, 2) if closed else None,
            }
        )
    return stats
