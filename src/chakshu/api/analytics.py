"""Analytics for owners, and each person's own activity.

Org-level views are admin-only. The People directory and other people's pages
also need names turned on in the analytics settings, hide themselves for slices
under the minimum group size, and every view or export of them is written to the
audit log. Anyone signed in can open their own page; that isn't audited.
"""

import uuid
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse

from chakshu.api.deps import AdminDep, CredentialsDep, UserDep, csrf_protect
from chakshu.db.session import SessionDep
from chakshu.helpers import analytics as calc
from chakshu.services import analytics, members, teams
from chakshu.services.analytics import Dimension, Filters

router = APIRouter(prefix="/api/analytics", tags=["analytics"], dependencies=[Depends(csrf_protect)])

BREAKDOWN_COLUMNS = (
    "key",
    "reviews",
    "prs",
    "engaged",
    "spend",
    "cost_per_review",
    "posted",
    "fixed",
    "dismissed",
    "open",
    "fix_rate",
    "dismissed_rate",
    "cost_per_fixed",
)
PEOPLE_COLUMNS = (
    "login",
    "name",
    "org_role",
    "in_org",
    "activity_state",
    "requested",
    "prs_reviewed",
    "auto_reviews",
    "engaged",
    "cost_triggered",
    "last_activity_at",
)
PAGE_SIZES = (12, 24, 48)  # multiples of 2 and 3, so rows of cards come out even


async def filters(
    session: SessionDep,
    days: int = Query(30, ge=1, le=365),
    repo_id: uuid.UUID | None = None,
    reviewer: str | None = Query(None, max_length=100),
    trigger: str | None = Query(None, max_length=30),
    team: int | None = Query(None, ge=1),
) -> Filters:
    """The slice from the query string. A team slice about fewer people than the minimum group is refused."""
    f = Filters.last(days, repo_id=repo_id, reviewer=reviewer, trigger=trigger, team_id=team)
    if team is not None:
        min_group = (await analytics.privacy(session)).min_group
        if not calc.visible(await analytics.team_people(session, f), min_group):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"This team covers fewer than {min_group} people in this slice, so its numbers are hidden. "
                "Widen the period or clear a filter.",
            )
    return f


FiltersDep = Annotated[Filters, Depends(filters)]


def _csv(text: str, name: str) -> PlainTextResponse:
    return PlainTextResponse(
        text, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}.csv"'}
    )


@router.get("/overview")
async def overview(f: FiltersDep, session: SessionDep, _: AdminDep) -> dict:
    return await analytics.overview(session, f)


@router.get("/breakdown")
async def breakdown(by: Dimension, f: FiltersDep, session: SessionDep, _: AdminDep) -> list[dict]:
    return await analytics.breakdown(session, f, by)


@router.get("/breakdown.csv")
async def breakdown_csv(by: Dimension, f: FiltersDep, session: SessionDep, _: AdminDep) -> PlainTextResponse:
    rows = await analytics.breakdown(session, f, by)
    return _csv(calc.to_csv(rows, BREAKDOWN_COLUMNS), f"chakshu-by-{by}")


@router.get("/teams")
async def by_team(f: FiltersDep, session: SessionDep, _: AdminDep) -> dict:
    """One row per team. Rows overlap, since a run counts for every team its people were in."""
    min_group = (await analytics.privacy(session)).min_group
    return {
        "min_group": min_group,
        "teams_source": await teams.source(session),
        "rows": await analytics.by_team(session, f, min_group),
    }


@router.get("/teams/options")
async def team_options(session: SessionDep, _: AdminDep) -> list[dict]:
    return await teams.options(session)


@router.post("/teams/refresh")
async def refresh_teams(session: SessionDep, creds: CredentialsDep, _: AdminDep) -> dict:
    """Fetch teams and memberships from GitHub now, instead of waiting for the nightly sync."""
    return {"teams_source": await teams.sync(session, creds)}


@router.get("/cost")
async def cost(session: SessionDep, _: AdminDep) -> dict:
    return await analytics.cost(session)


@router.get("/roi")
async def roi(f: FiltersDep, session: SessionDep, _: AdminDep) -> dict:
    """Fixed findings and spend, valued with the admin's own assumptions. An estimate, not a measurement."""
    return await analytics.roi(session, f)


@router.get("/findings")
async def findings(
    f: FiltersDep,
    session: SessionDep,
    _: AdminDep,
    skill: str | None = Query(None, max_length=100),
    outcome: str | None = Query(None, pattern="^(open|fixed|dismissed)$"),
) -> list[dict]:
    return await analytics.findings(session, f, skill=skill, outcome=outcome)


def directory_query(
    q: str | None = Query(None, max_length=100),
    role: str = Query("all", pattern="^(owner|member|all)$"),
    activity: str = Query("all", pattern="^(all|engaged|auto_only|none|not_in_org)$"),
    sort: str = Query("name", pattern="^(name|last_activity|requested|prs_reviewed|cost)$"),
    order: str | None = Query(None, pattern="^(asc|desc)$"),
) -> analytics.DirectoryQuery:
    return analytics.DirectoryQuery(
        q=(q or "").strip() or None, role=role, activity=activity, sort=sort, order=order
    )


DirectoryQueryDep = Annotated[analytics.DirectoryQuery, Depends(directory_query)]


def _period(f: Filters, days: int) -> dict:
    return {"days": days, "from": f.start.date().isoformat(), "to": f.end.date().isoformat()}


def _days(days: int = Query(30, ge=1, le=365)) -> int:
    return days


DaysDep = Annotated[int, Depends(_days)]


def _hidden(reason: str | None, min_group: int) -> dict:
    return {"hidden": reason is not None, "hidden_reason": reason, "min_group": min_group}


async def _directory(session: SessionDep, f: Filters, query: analytics.DirectoryQuery) -> dict:
    """The directory, or why it isn't shown."""
    settings = await analytics.privacy(session)
    if not settings.show_names:
        return _hidden("names_off", settings.min_group) | {"counts": None, "rows": []}
    result = await analytics.directory(session, f, query)
    if not calc.visible(result["active"], settings.min_group):
        return _hidden("small_group", settings.min_group) | {"counts": None, "rows": []}
    return _hidden(None, settings.min_group) | {"counts": result["counts"], "rows": result["rows"]}


@router.get("/people")
async def people(
    f: FiltersDep,
    days: DaysDep,
    query: DirectoryQueryDep,
    session: SessionDep,
    user: AdminDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(12),
) -> dict:
    if page_size not in PAGE_SIZES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"page_size must be one of {PAGE_SIZES}.")
    result = await _directory(session, f, query)
    rows = result.pop("rows")
    if not result["hidden"]:
        await analytics.record_access(
            session, user.login, "people.directory.view", "people", _audit(f, query)
        )
    return result | {
        "period": _period(f, days),
        "members_source": await members.source(session),
        "total": len(rows),
        "page": page,
        "page_size": page_size,
        "rows": calc.page(rows, page, page_size),
    }


def _audit(f: Filters, query: analytics.DirectoryQuery | None = None) -> dict:
    described = f.describe()
    if query:
        described |= {k: v for k, v in asdict(query).items() if v not in (None, "all")}
    return described


@router.get("/people.csv")
async def people_csv(
    f: FiltersDep, query: DirectoryQueryDep, session: SessionDep, user: AdminDep
) -> PlainTextResponse:
    if not (await analytics.privacy(session)).export_people:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Exporting named people is turned off in the privacy settings."
        )
    result = await _directory(session, f, query)
    if result["hidden"] or not result["rows"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "There's nothing to export for this selection.")
    await analytics.record_access(session, user.login, "people.export", "people", _audit(f, query))
    note = "# Chakshu usage per person. For enablement and cost questions, not for judging performance.\n"
    return _csv(note + calc.to_csv(result["rows"], PEOPLE_COLUMNS), "chakshu-people")


@router.post("/people/refresh")
async def refresh_members(session: SessionDep, creds: CredentialsDep, _: AdminDep) -> dict:
    """Fetch the org member list from GitHub now, instead of waiting for the next sync."""
    return {"members_source": await members.sync(session, creds)}


async def _person_access(session: SessionDep, login: str, user: UserDep) -> tuple[str, bool]:
    """(canonical login, is it the signed-in person). Admins see anyone, everyone else only themselves."""
    is_self = login.lower() == user.login.lower()
    if not (is_self or user.is_admin):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only see your own activity.")
    canonical = await analytics.canonical_login(session, login)
    if canonical is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"No one with the login {login} is in this org or in Chakshu's history.",
        )
    return canonical, is_self


async def _person_hidden(session: SessionDep, f: Filters, is_self: bool) -> tuple[str | None, int]:
    """Why another person's page is hidden, if it is. Nobody is hidden from themselves."""
    settings = await analytics.privacy(session)
    if is_self:
        return None, settings.min_group
    if not settings.show_names:
        return "names_off", settings.min_group
    active = sum(row["activity_state"] != "none" for row in (await analytics.ledger(session, f)).values())
    return (None if calc.visible(active, settings.min_group) else "small_group"), settings.min_group


@router.get("/people/{login}")
async def person(login: str, f: FiltersDep, days: DaysDep, session: SessionDep, user: UserDep) -> dict:
    canonical, is_self = await _person_access(session, login, user)
    reason, min_group = await _person_hidden(session, f, is_self)
    result = _hidden(reason, min_group) | {"is_self": is_self, "period": _period(f, days)}
    if canonical != login:
        result["canonical_login"] = canonical
    if reason == "names_off":
        return result
    result["person"] = await analytics.person(session, canonical, f)
    if reason == "small_group":
        return result
    if not is_self:
        await analytics.record_access(
            session, user.login, "people.detail.view", "person", _audit(f), target_login=canonical
        )
    return result | {
        "totals": await analytics.person_totals(session, canonical, f),
        "previous_totals": await analytics.person_totals(session, canonical, f.previous()),
        **await analytics.person_breakdowns(session, canonical, f),
        "daily": await analytics.person_daily(session, canonical, f, days),
    }


@router.get("/people/{login}/activity")
async def person_activity(
    login: str,
    f: FiltersDep,
    session: SessionDep,
    user: UserDep,
    cursor: str | None = Query(None, max_length=200),
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    canonical, is_self = await _person_access(session, login, user)
    reason, _ = await _person_hidden(session, f, is_self)
    if reason:
        return {"hidden": True, "hidden_reason": reason, "items": [], "next_cursor": None}
    try:
        result = await analytics.person_activity(session, canonical, f, cursor=cursor, limit=limit)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That cursor isn't valid.") from exc
    if not is_self:
        await analytics.record_access(
            session, user.login, "people.activity.view", "person", _audit(f), target_login=canonical
        )
    return {"hidden": False, "hidden_reason": None} | result


@router.get("/me")
async def my_activity(f: FiltersDep, session: SessionDep, user: UserDep) -> dict:
    """The signed-in person's own row: exactly what an admin sees about them. Kept for older portals."""
    rows = await analytics.people(session, f, login=user.login)
    return {"row": rows[0] if rows else None}
