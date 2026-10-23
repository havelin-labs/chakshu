"""Queries behind the analytics pages: usage, outcomes and cost, sliced by repo, reviewer and person.

A "review" is a finished run that wasn't a reply. Spend counts every run that
cost something, including failed ones, because the bill does. Findings are
dated by when they were posted. People appear only as a usage ledger (what they
asked for, whose PRs were reviewed, what that cost), never with findings per
author, and grouped numbers about fewer than `min_group` people are hidden.
Logins are matched case-insensitively and shown as GitHub spells them.
See helpers/analytics.py for the definitions of each rate.
"""

import uuid
from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from sqlalchemy import Select, case, distinct, func, select, tuple_, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from chakshu.core.config import get_settings
from chakshu.db.models import (
    AnalyticsAudit,
    FindingOutcome,
    OrgMember,
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
    retention_days: int | None = None  # None keeps who asked and who authored indefinitely
    export_people: bool = True


async def privacy(session: AsyncSession) -> Privacy:
    values = await store.get_many(
        session,
        Key.ANALYTICS_SHOW_NAMES,
        Key.ANALYTICS_MIN_GROUP,
        Key.ANALYTICS_RETENTION_DAYS,
        Key.ANALYTICS_EXPORT_PEOPLE,
    )
    min_group = int(values[Key.ANALYTICS_MIN_GROUP] or 5)
    if not calc.valid_min_group(min_group):  # stored before the rules changed
        min_group = min(max(min_group, calc.MIN_GROUP_FLOOR), calc.MIN_GROUP_MAX)
    retention = values[Key.ANALYTICS_RETENTION_DAYS]
    return Privacy(
        show_names=(values[Key.ANALYTICS_SHOW_NAMES] or "true") == "true",
        min_group=min_group,
        retention_days=int(retention) if retention else None,
        export_people=(values[Key.ANALYTICS_EXPORT_PEOPLE] or "true") == "true",
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


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _asked(key: str):
    return func.lower(Run.requested_by) == key


def _owns(key: str):
    return func.lower(Run.pr_author) == key


async def ledger(session: AsyncSession, f: Filters, key: str | None = None) -> dict[str, dict]:
    """Usage per person in the slice, keyed by lowercase login. No findings per author, no ranks.

    `key` (a lowercase login) limits it to one person.
    """
    requester = func.lower(Run.requested_by)
    asked = _runs(
        select(
            requester.label("key"),
            func.min(Run.requested_by).label("login"),
            func.count().label("requested"),
            func.count(case((Run.trigger == REPLY, 1))).label("replies"),
            func.coalesce(func.sum(Run.cost_usd), 0).label("cost"),
        ).where(Run.requested_by.is_not(None)),
        f,
    ).group_by(requester)
    author = func.lower(Run.pr_author)
    authored = _runs(
        select(
            author.label("key"),
            func.min(Run.pr_author).label("login"),
            func.count(distinct(tuple_(Run.repo_id, Run.pr_number))).label("prs_reviewed"),
            func.count(case((Run.trigger == "auto", 1))).label("auto_reviews"),
        ).where(Run.pr_author.is_not(None), Run.pr_author != "", _review),
        f,
    ).group_by(author)
    if key:
        asked, authored = asked.where(requester == key), authored.where(author == key)
    rows: dict[str, dict] = {}
    for r in (await session.execute(asked)).all():
        rows[r.key] = {
            "login": r.login,
            "requested": r.requested,
            "replies": r.replies,
            "cost_triggered": round(float(r.cost), 4),
        }
    for r in (await session.execute(authored)).all():
        rows.setdefault(r.key, {"login": r.login}).update(
            {"prs_reviewed": r.prs_reviewed, "auto_reviews": r.auto_reviews}
        )
    for row in rows.values():
        for name in ("requested", "replies", "prs_reviewed", "auto_reviews"):
            row.setdefault(name, 0)
        row.setdefault("cost_triggered", 0.0)
        row["engaged"] = row["requested"] > 0
        row["activity_state"] = calc.activity_state(row["requested"], row["prs_reviewed"])
    return rows


NO_USAGE = {
    "requested": 0,
    "replies": 0,
    "prs_reviewed": 0,
    "auto_reviews": 0,
    "cost_triggered": 0.0,
    "engaged": False,
    "activity_state": "none",
}


async def people(session: AsyncSession, f: Filters, login: str | None = None) -> list[dict]:
    """The ledger as rows sorted by login, with names. `login` limits it to one person (/api/analytics/me)."""
    rows = await ledger(session, f, login.lower() if login else None)
    users = {u.login.lower(): u.name for u in (await session.execute(select(User.login, User.name))).all()}
    result = []
    for key in sorted(rows):
        row = rows[key]
        result.append(
            {k: row[k] for k in ("requested", "prs_reviewed", "auto_reviews", "cost_triggered", "engaged")}
            | {"login": row["login"], "name": users.get(key)}
        )
    return result


async def activity_dates(session: AsyncSession, keys: set[str]) -> dict[str, tuple[datetime, datetime]]:
    """(first, last) time each person asked for a review or had a PR reviewed. All time, no filters."""
    if not keys:
        return {}
    requester, author = func.lower(Run.requested_by), func.lower(Run.pr_author)
    both = union_all(
        select(requester.label("key"), Run.created_at).where(requester.in_(keys)),
        select(author.label("key"), Run.created_at).where(author.in_(keys)),
    ).subquery()
    rows = await session.execute(
        select(both.c.key, func.min(both.c.created_at), func.max(both.c.created_at)).group_by(both.c.key)
    )
    return {key: (first, last) for key, first, last in rows.all()}


async def _profiles(session: AsyncSession, f: Filters, keys: set[str] | None) -> tuple[list[dict], bool]:
    """Directory rows: the roster joined to the slice's usage and to portal sign-ins.

    `keys` limits it to those people; None means every org member plus anyone active in the slice.
    Returns the rows and whether a member list has been synced at all.
    """
    members = {m.login_lower: m for m in (await session.scalars(select(OrgMember))).all()}
    users = {u.login.lower(): u for u in (await session.scalars(select(User))).all()}
    usage = await ledger(session, f, next(iter(keys)) if keys and len(keys) == 1 else None)
    if keys is None:
        keys = {k for k, m in members.items() if m.in_org} | set(usage)
    dates = await activity_dates(session, keys)
    rows = []
    for key in keys:
        member, user, use = members.get(key), users.get(key), usage.get(key, {})
        in_org = bool(member and member.in_org)
        first, last = dates.get(key, (None, None))
        login = member.login if member else user.login if user else use.get("login", key)
        rows.append(
            {
                "login": login,
                "name": (member and member.name) or (user and user.name) or None,
                "avatar_url": (member and member.avatar_url) or (user and user.avatar_url) or None,
                "org_role": member.org_role if member and in_org else None,
                "in_org": in_org,
                "is_portal_admin": bool(user and user.is_admin),
                "last_login_at": _iso(user.last_login_at) if user else None,
                **NO_USAGE,
                **{k: v for k, v in use.items() if k != "login"},
                "first_activity_at": _iso(first),
                "last_activity_at": _iso(last),
            }
        )
    return rows, bool(members)


@dataclass(frozen=True)
class DirectoryQuery:
    q: str | None = None
    role: Literal["owner", "member", "all"] = "all"
    activity: Literal["all", "engaged", "auto_only", "none", "not_in_org"] = "all"
    sort: calc.PeopleSort = "name"
    order: Literal["asc", "desc"] | None = None


DIRECTORY_FIELDS = (
    "login",
    "name",
    "avatar_url",
    "org_role",
    "in_org",
    "is_portal_admin",
    "last_login_at",
    "activity_state",
    "requested",
    "prs_reviewed",
    "auto_reviews",
    "engaged",
    "cost_triggered",
    "last_activity_at",
)


async def directory(session: AsyncSession, f: Filters, query: DirectoryQuery) -> dict:
    """Everyone in the org with their usage in the slice, filtered and sorted (not paged).

    `active` is how many people did anything in the slice, for the small-group check.
    """
    rows, roster_known = await _profiles(session, f, None)
    active = sum(r["activity_state"] != "none" for r in rows)
    if query.q:
        needle = query.q.lower()
        rows = [r for r in rows if needle in r["login"].lower() or needle in (r["name"] or "").lower()]
    if query.role != "all":
        rows = [r for r in rows if r["org_role"] == query.role]
    # Without a synced member list (a personal account install), everyone counts as in the org.
    in_scope = [r for r in rows if r["in_org"] or not roster_known]
    counts = {"all": len(in_scope)} | {
        state: sum(r["activity_state"] == state for r in in_scope)
        for state in ("engaged", "auto_only", "none")
    }
    counts["not_in_org"] = len(rows) - len(in_scope)
    if query.activity == "not_in_org":
        rows = [r for r in rows if roster_known and not r["in_org"]]
    elif query.activity == "all":
        rows = in_scope
    else:
        rows = [r for r in in_scope if r["activity_state"] == query.activity]
    order = query.order or ("asc" if query.sort == "name" else "desc")
    rows = calc.sort_people(rows, query.sort, order)
    return {
        "active": active,
        "counts": counts,
        "rows": [{k: r[k] for k in DIRECTORY_FIELDS} for r in rows],
    }


async def canonical_login(session: AsyncSession, login: str) -> str | None:
    """The login as GitHub spells it, from the member list, sign-ins or runs. None if Chakshu never saw it."""
    key = login.lower()
    for stmt in (
        select(OrgMember.login).where(OrgMember.login_lower == key),
        select(User.login).where(func.lower(User.login) == key),
        select(Run.requested_by).where(_asked(key)),
        select(Run.pr_author).where(_owns(key)),
    ):
        if found := await session.scalar(stmt.limit(1)):
            return found
    return None


async def person(session: AsyncSession, login: str, f: Filters) -> dict:
    """One person's profile: who they are, and when they last used Chakshu (all time)."""
    rows, _ = await _profiles(session, f, {login.lower()})
    row = rows[0]
    return {
        k: row[k]
        for k in (
            "login",
            "name",
            "avatar_url",
            "org_role",
            "in_org",
            "is_portal_admin",
            "last_login_at",
            "first_activity_at",
            "last_activity_at",
            "activity_state",
        )
    } | {"github_url": f"{get_settings().github_url}/{row['login']}"}


async def person_totals(session: AsyncSession, login: str, f: Filters) -> dict:
    key = login.lower()
    asked, owns = _asked(key), _owns(key)
    row = (
        (
            await session.execute(
                _runs(
                    select(
                        func.count(case((asked, 1))).label("requested"),
                        func.count(
                            distinct(case((owns & _review, tuple_(Run.repo_id, Run.pr_number))))
                        ).label("prs_reviewed"),
                        func.count(case((owns & _review & (Run.trigger == "auto"), 1))).label("auto_reviews"),
                        func.count(case((asked & (Run.trigger == REPLY), 1))).label("replies"),
                        func.count(case((asked & owns, 1))).label("self_requested_on_own_prs"),
                        func.coalesce(func.sum(case((asked, Run.cost_usd))), 0).label("cost_triggered"),
                        func.coalesce(func.sum(case((owns, Run.cost_usd))), 0).label("cost_on_own_prs"),
                    ).where(asked | owns),
                    f,
                )
            )
        )
        .one()
        ._asdict()
    )
    return row | {k: round(float(row[k]), 4) for k in ("cost_triggered", "cost_on_own_prs")}


BREAKDOWN_CAP = 9  # rows before the rest are added up as Other


async def person_breakdowns(session: AsyncSession, login: str, f: Filters) -> dict:
    """Runs a person asked for or whose PRs were reviewed, by trigger, repository and reviewer."""
    key = login.lower()
    involved = _asked(key) | _owns(key)
    runs, spent = func.count().label("runs"), func.coalesce(func.sum(Run.cost_usd), 0).label("cost_usd")

    async def grouped(*labels, extra=(), joins=()):
        stmt = select(*labels, *extra, runs, spent)
        for table, on in joins:
            stmt = stmt.join(table, on)
        stmt = _runs(stmt.where(involved), f).group_by(*labels)
        return [
            r._asdict() | {"cost_usd": round(float(r.cost_usd), 4)}
            for r in (await session.execute(stmt.order_by(runs.desc(), *labels))).all()
        ]

    prs = func.count(distinct(tuple_(Run.repo_id, Run.pr_number))).label("prs")
    by_repo = await grouped(
        Repo.id.label("repo_id"),
        Repo.full_name.label("repo"),
        extra=[prs],
        joins=[(Repo, Run.repo_id == Repo.id)],
    )
    by_repo = [r | {"repo_id": str(r["repo_id"])} for r in by_repo]
    by_reviewer = await grouped(
        Reviewer.name.label("reviewer"), joins=[(Reviewer, Run.reviewer_id == Reviewer.id)]
    )
    return {
        "by_trigger": await grouped(Run.trigger.label("trigger")),
        "by_repo": calc.top_with_other(
            by_repo, BREAKDOWN_CAP, "repo", ("runs", "prs", "cost_usd"), repo_id=None
        ),
        "by_reviewer": calc.top_with_other(by_reviewer, BREAKDOWN_CAP, "reviewer", ("runs", "cost_usd")),
    }


async def person_daily(session: AsyncSession, login: str, f: Filters, days: int) -> list[dict]:
    """One entry per day for the last `days` days. Runs on the partial first day count on the first entry."""
    key = login.lower()
    asked, owns = _asked(key), _owns(key)
    day = func.date_trunc("day", Run.created_at)
    found = (
        await session.execute(
            _runs(
                select(
                    day.label("day"),
                    func.count(case((asked, 1))).label("requested"),
                    func.count(distinct(case((owns & _review, tuple_(Run.repo_id, Run.pr_number))))).label(
                        "own_prs_reviewed"
                    ),
                ).where(asked | owns),
                f,
            ).group_by(day)
        )
    ).all()
    series = calc.last_days(f.end, days)
    totals = {d: {"requested": 0, "own_prs_reviewed": 0} for d in series}
    for r in found:
        bucket = totals[max(r.day.date(), series[0])]
        bucket["requested"] += r.requested
        bucket["own_prs_reviewed"] += r.own_prs_reviewed
    return [{"day": d.isoformat(), **totals[d]} for d in series]


async def person_activity(
    session: AsyncSession, login: str, f: Filters, *, cursor: str | None, limit: int
) -> dict:
    """A person's runs, newest first, a page at a time. The cursor is the last row's (created_at, id)."""
    key = login.lower()
    asked, owns = _asked(key), _owns(key)
    stmt = (
        _runs(select(Run, Repo.full_name, Reviewer.name).where(asked | owns), f)
        .join(Repo, Run.repo_id == Repo.id)
        .join(Reviewer, Run.reviewer_id == Reviewer.id)
    )
    if cursor:
        when, run_id = calc.decode_cursor(cursor)
        stmt = stmt.where(tuple_(Run.created_at, Run.id) < tuple_(when, run_id))
    rows = (await session.execute(stmt.order_by(Run.created_at.desc(), Run.id.desc()).limit(limit + 1))).all()
    items = []
    for run, repo, reviewer in rows[:limit]:
        mine = (run.requested_by or "").lower() == key, (run.pr_author or "").lower() == key
        items.append(
            {
                "run_id": str(run.id),
                "created_at": run.created_at.isoformat(),
                "role": "both" if all(mine) else "requested" if mine[0] else "author",
                "trigger": run.trigger,
                "repo": repo,
                "repo_id": str(run.repo_id),
                "pr_number": run.pr_number,
                "pr_title": run.pr_title,
                "reviewer": reviewer,
                "status": run.status,
                "review_url": run.review_url,
                "cost_usd": float(run.cost_usd) if run.cost_usd is not None else None,
            }
        )
    last = rows[limit - 1][0] if len(rows) > limit else None
    return {"items": items, "next_cursor": calc.encode_cursor(last.created_at, last.id) if last else None}


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


async def record_access(
    session: AsyncSession,
    login: str,
    action: str,
    view: str,
    filters: dict,
    target_login: str | None = None,
) -> None:
    """Write one audit row and commit. `action` is e.g. people.detail.view; see AnalyticsAudit."""
    session.add(
        AnalyticsAudit(
            id=uuid.uuid4(),
            user_login=login,
            action=action,
            view=view,
            filters=filters,
            target_login=target_login,
            created_at=datetime.now(UTC),
        )
    )
    await session.commit()


async def audit_log(session: AsyncSession, limit: int = 200) -> list[dict]:
    """The newest audit rows: who viewed, exported or changed analytics about named people."""
    rows = (
        await session.scalars(select(AnalyticsAudit).order_by(AnalyticsAudit.created_at.desc()).limit(limit))
    ).all()
    return [
        {
            "at": row.created_at.isoformat(),
            "user": row.user_login,
            "action": row.action,
            "target": row.target_login,
            "details": row.filters,
        }
        for row in rows
    ]
