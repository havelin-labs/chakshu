"""Queries behind the analytics pages: usage, outcomes and cost, sliced by repo, reviewer and person.

A "review" is a finished run that wasn't a reply. Spend counts every run that
cost something, including failed ones, because the bill does. Findings are
dated by when they were posted. People appear only as a usage ledger (what they
asked for, whose PRs were reviewed, what that cost), never with findings per
author, and grouped numbers about fewer than `min_group` people are hidden.
See helpers/analytics.py for the definitions of each rate.
"""

import uuid
from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from sqlalchemy import Select, case, distinct, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.db.models import (
    AnalyticsAudit,
    FindingOutcome,
    PostedFinding,
    Repo,
    Reviewer,
    Run,
    RunStatus,
    User,
)
from chakshu.helpers import analytics as calc
from chakshu.services import settings_store as store
from chakshu.services import spend
from chakshu.services.settings_store import Key

Dimension = Literal["repo", "reviewer", "skill", "trigger", "model"]
DIMENSIONS: tuple[Dimension, ...] = ("repo", "reviewer", "skill", "trigger", "model")
REPLY = "reply"
NO_VALUE = "(none)"


@dataclass(frozen=True)
class Filters:
    start: datetime
    end: datetime
    repo_id: uuid.UUID | None = None
    reviewer: str | None = None
    trigger: str | None = None

    @classmethod
    def last(cls, days: int, **kwargs) -> "Filters":
        end = datetime.now(UTC)
        return cls(start=end - timedelta(days=days), end=end, **kwargs)

    def previous(self) -> "Filters":
        """The period of the same length just before this one."""
        length = self.end - self.start
        return replace(self, start=self.start - length, end=self.start)

    def describe(self) -> dict:
        return {k: str(v) for k, v in asdict(self).items() if v is not None}


@dataclass(frozen=True)
class Privacy:
    show_names: bool
    min_group: int


async def privacy(session: AsyncSession) -> Privacy:
    values = await store.get_many(session, Key.ANALYTICS_SHOW_NAMES, Key.ANALYTICS_MIN_GROUP)
    return Privacy(
        show_names=(values[Key.ANALYTICS_SHOW_NAMES] or "true") == "true",
        min_group=max(int(values[Key.ANALYTICS_MIN_GROUP] or 5), calc.MIN_GROUP_FLOOR),
    )


def _runs(stmt: Select, f: Filters) -> Select:
    stmt = stmt.where(Run.created_at >= f.start, Run.created_at < f.end)
    if f.repo_id:
        stmt = stmt.where(Run.repo_id == f.repo_id)
    if f.reviewer:
        stmt = stmt.where(Run.reviewer_id.in_(select(Reviewer.id).where(Reviewer.name == f.reviewer)))
    if f.trigger:
        stmt = stmt.where(Run.trigger == f.trigger)
    return stmt


def _findings(stmt: Select, f: Filters) -> Select:
    """Findings posted in the period by runs that match the filters."""
    stmt = (
        stmt.select_from(PostedFinding)
        .join(Run, PostedFinding.run_id == Run.id)
        .where(PostedFinding.created_at >= f.start, PostedFinding.created_at < f.end)
    )
    if f.repo_id:
        stmt = stmt.where(Run.repo_id == f.repo_id)
    if f.reviewer:
        stmt = stmt.where(
            PostedFinding.reviewer_id.in_(select(Reviewer.id).where(Reviewer.name == f.reviewer))
        )
    if f.trigger:
        stmt = stmt.where(Run.trigger == f.trigger)
    return stmt


_review = (Run.status == RunStatus.SUCCEEDED.value) & (Run.trigger != REPLY)


def _run_columns():
    return (
        func.count(case((_review, 1))).label("reviews"),
        func.count(distinct(case((_review, tuple_(Run.repo_id, Run.pr_number))))).label("prs"),
        func.count(case((_review & Run.trigger.in_(calc.ENGAGED_TRIGGERS), 1))).label("engaged"),
        func.count(case(((Run.status == RunStatus.SUCCEEDED.value) & (Run.trigger == REPLY), 1))).label(
            "replies"
        ),
        func.count(case((Run.status == RunStatus.FAILED.value, 1))).label("failed"),
        func.coalesce(func.sum(Run.cost_usd), 0).label("spend"),
        func.count(distinct(Run.requested_by)).label("requesters"),
    )


def _finding_columns():
    def outcome(value: FindingOutcome):
        return func.count(case((PostedFinding.outcome == value.value, 1)))

    return (
        func.count().label("posted"),
        outcome(FindingOutcome.FIXED).label("fixed"),
        outcome(FindingOutcome.DISMISSED).label("dismissed"),
        outcome(FindingOutcome.OPEN).label("open"),
    )


COUNTS = (
    "reviews",
    "prs",
    "engaged",
    "replies",
    "failed",
    "requesters",
    "posted",
    "fixed",
    "dismissed",
    "open",
)


def _derive(row: dict) -> dict:
    """Add the rates and unit costs to a row of raw counts. Counts a row lacks are zero."""
    row = dict.fromkeys(COUNTS, 0) | row
    fixed, dismissed = row.get("fixed", 0), row.get("dismissed", 0)
    spent = float(row.get("spend") or 0)
    return row | {
        "spend": round(spent, 4),
        "fix_rate": calc.fix_rate(fixed, dismissed),
        "dismissed_rate": calc.dismissed_rate(fixed, dismissed),
        "cost_per_review": calc.per_unit(spent, row.get("reviews", 0)),
        "cost_per_fixed": calc.per_unit(spent, fixed),
        "engaged_share": calc.ratio(row.get("engaged", 0), row.get("reviews", 0)),
    }


async def totals(session: AsyncSession, f: Filters) -> dict:
    runs = (await session.execute(_runs(select(*_run_columns()), f))).one()._asdict()
    found = (await session.execute(_findings(select(*_finding_columns()), f))).one()._asdict()
    return _derive(runs | found)


TILES = (
    "reviews",
    "prs",
    "spend",
    "posted",
    "fixed",
    "fix_rate",
    "cost_per_fixed",
    "engaged_share",
    "requesters",
)


async def overview(session: AsyncSession, f: Filters) -> dict:
    now, before = await totals(session, f), await totals(session, f.previous())
    day = func.date_trunc("day", Run.created_at)
    daily_runs = {
        r.day.date(): r
        for r in (
            await session.execute(
                _runs(select(day.label("day"), *_run_columns()), f).group_by(day).order_by(day)
            )
        ).all()
    }
    fday = func.date_trunc("day", PostedFinding.created_at)
    daily_found = {
        r.day.date(): r
        for r in (
            await session.execute(
                _findings(select(fday.label("day"), *_finding_columns()), f).group_by(fday).order_by(fday)
            )
        ).all()
    }
    series = []
    for d in calc.days(f.start, f.end):
        runs, found = daily_runs.get(d), daily_found.get(d)
        series.append(
            {
                "day": d.isoformat(),
                "reviews": runs.reviews if runs else 0,
                "spend": round(float(runs.spend), 4) if runs else 0.0,
                "posted": found.posted if found else 0,
                "fixed": found.fixed if found else 0,
            }
        )
    return {
        "tiles": {
            k: {"value": now[k], "previous": before[k], "change": calc.change(now[k], before[k])}
            for k in TILES
        },
        "totals": now,
        "daily": series,
    }


def _dimension(by: Dimension):
    """(label column, joins) for a run-level dimension."""
    if by == "repo":
        return Repo.full_name, [(Repo, Run.repo_id == Repo.id)]
    if by == "reviewer":
        return Reviewer.name, [(Reviewer, Run.reviewer_id == Reviewer.id)]
    if by == "trigger":
        return Run.trigger, []
    return Run.model, []


def _finding_dimension(by: Dimension):
    """(label column, joins) for a dimension of findings, applied after the join to runs."""
    if by == "skill":
        return PostedFinding.skill, []
    if by == "reviewer":
        return Reviewer.name, [(Reviewer, PostedFinding.reviewer_id == Reviewer.id)]
    return _dimension(by)


async def breakdown(session: AsyncSession, f: Filters, by: Dimension) -> list[dict]:
    rows: dict[str, dict] = {}
    if by != "skill":  # skills belong to findings, not runs
        label, joins = _dimension(by)
        stmt = select(label.label("key"), *_run_columns())
        for table, on in joins:
            stmt = stmt.join(table, on)
        for r in (await session.execute(_runs(stmt, f).group_by(label))).all():
            rows[r.key or NO_VALUE] = r._asdict()
    label, joins = _finding_dimension(by)
    stmt = _findings(select(label.label("key"), *_finding_columns()), f)
    for table, on in joins:
        stmt = stmt.join(table, on)
    for r in (await session.execute(stmt.group_by(label))).all():
        key = r.key or NO_VALUE
        rows[key] = rows.get(key, {}) | r._asdict()
    result = [_derive(counts | {"key": key}) for key, counts in rows.items()]
    return sorted(result, key=lambda r: (-r["spend"], -r.get("posted", 0), r["key"]))


async def _names(session: AsyncSession, logins: set[str]) -> dict[str, str | None]:
    if not logins:
        return {}
    users = (await session.execute(select(User.login, User.name).where(User.login.in_(logins)))).all()
    return {u.login: u.name for u in users}


async def people(session: AsyncSession, f: Filters, login: str | None = None) -> list[dict]:
    """Usage per person, sorted by login. No findings per author, no ranks.

    `login` limits it to one person (their own activity view).
    """
    asked = _runs(
        select(
            Run.requested_by.label("login"),
            func.count().label("requested"),
            func.coalesce(func.sum(Run.cost_usd), 0).label("cost"),
        ).where(Run.requested_by.is_not(None)),
        f,
    ).group_by(Run.requested_by)
    authored = _runs(
        select(
            Run.pr_author.label("login"),
            func.count(distinct(tuple_(Run.repo_id, Run.pr_number))).label("prs_reviewed"),
            func.count(case((Run.trigger == "auto", 1))).label("auto_reviews"),
        ).where(Run.pr_author.is_not(None), Run.pr_author != "", _review),
        f,
    ).group_by(Run.pr_author)
    if login:
        asked = asked.where(Run.requested_by == login)
        authored = authored.where(Run.pr_author == login)
    rows: dict[str, dict] = {}
    for r in (await session.execute(asked)).all():
        rows[r.login] = {"requested": r.requested, "cost_triggered": round(float(r.cost), 4)}
    for r in (await session.execute(authored)).all():
        rows.setdefault(r.login, {}).update({"prs_reviewed": r.prs_reviewed, "auto_reviews": r.auto_reviews})
    names = await _names(session, set(rows))
    result = []
    for person in sorted(rows, key=str.lower):
        row = {"requested": 0, "cost_triggered": 0.0, "prs_reviewed": 0, "auto_reviews": 0} | rows[person]
        result.append(row | {"login": person, "name": names.get(person), "engaged": row["requested"] > 0})
    return result


async def cost(session: AsyncSession, today: date | None = None) -> dict:
    today = today or datetime.now(UTC).date()
    budget = await spend.current(session)
    start = datetime(today.year, today.month, 1, tzinfo=UTC)
    month = Filters(start=start, end=datetime.now(UTC))
    capped = await session.scalar(
        _runs(select(func.count()).select_from(Run).where(Run.error.ilike("%max_budget%")), month)
    )
    projection = calc.forecast(float(budget.month_to_date), float(budget.cap) if budget.cap else None, today)
    return {
        "forecast": asdict(projection)
        | {"cap_hit_on": projection.cap_hit_on and projection.cap_hit_on.isoformat()},
        "stopped_by_review_cap": capped or 0,
        "by": {by: await breakdown(session, month, by) for by in ("repo", "reviewer", "model", "trigger")},
    }


async def findings(
    session: AsyncSession, f: Filters, *, skill: str | None, outcome: str | None, limit: int = 200
) -> list[dict]:
    stmt = _findings(
        select(PostedFinding, Run.pr_number, Run.pr_title, Run.review_url, Repo.full_name, Reviewer.name), f
    )
    stmt = stmt.join(Repo, Run.repo_id == Repo.id).join(Reviewer, PostedFinding.reviewer_id == Reviewer.id)
    if skill:
        stmt = stmt.where(PostedFinding.skill == skill)
    if outcome:
        stmt = stmt.where(PostedFinding.outcome == outcome)
    rows = (await session.execute(stmt.order_by(PostedFinding.created_at.desc()).limit(limit))).all()
    return [
        {
            "posted_at": found.created_at.isoformat(),
            "repo": repo,
            "pr_number": number,
            "pr_title": title,
            "review_url": url,
            "reviewer": reviewer,
            "skill": found.skill,
            "severity": found.severity,
            "category": found.category,
            "outcome": found.outcome,
            "outcome_source": found.outcome_source,
        }
        for found, number, title, url, repo, reviewer in rows
    ]


async def record_access(session: AsyncSession, login: str, action: str, view: str, f: Filters) -> None:
    session.add(
        AnalyticsAudit(
            id=uuid.uuid4(),
            user_login=login,
            action=action,
            view=view,
            filters=f.describe(),
            created_at=datetime.now(UTC),
        )
    )
    await session.commit()
