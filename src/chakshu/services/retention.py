"""Forget who asked for and who authored older reviews, once a retention period is set.

Runs keep everything else (repo, reviewer, cost, outcomes), so organization,
repository and skill analytics stay whole; only the person fields are cleared.
The same cutoff clears who opened and first reviewed a PR in `pr_events`, and
deletes team memberships that ended before it, since runs that old no longer
name anyone a team could be matched on. The worker calls `apply` once a day.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.db.models import PrEvent, Run, TeamMembership
from chakshu.services import analytics, pr_authors

log = logging.getLogger(__name__)

MIN_DAYS = 30
MAX_DAYS = 3650


async def apply(session: AsyncSession, now: datetime | None = None) -> int:
    """Clear person fields on runs older than the retention period. Returns how many runs changed."""
    days = (await analytics.privacy(session)).retention_days
    if not days:
        return 0
    cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
    result = await session.execute(
        update(Run)
        .where(
            Run.created_at < cutoff, or_(Run.requested_by.is_not(None), Run.pr_author != pr_authors.UNKNOWN)
        )
        # The empty author is the backfill's "looked up, unknown" marker, so it won't refill these.
        .values(requested_by=None, pr_author=pr_authors.UNKNOWN)
    )
    await session.execute(
        update(PrEvent).where(PrEvent.at < cutoff, PrEvent.actor.is_not(None)).values(actor=None)
    )
    await session.execute(delete(TeamMembership).where(TeamMembership.valid_to < cutoff))
    await session.commit()
    if result.rowcount:
        log.info("Cleared who asked and who authored on %s run(s) older than %s days", result.rowcount, days)
    return result.rowcount or 0
