"""Analytics for owners, and each person's own activity.

Org-level views are admin-only. The people ledger also needs names turned on in
the analytics settings, hides itself for slices under the minimum group size,
and every view or export of it is written to the audit log. Anyone signed in can
see their own row, exactly as an admin would.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from chakshu.api.deps import AdminDep, UserDep, csrf_protect
from chakshu.db.session import SessionDep
from chakshu.helpers import analytics as calc
from chakshu.services import analytics
from chakshu.services import settings_store as store
from chakshu.services.analytics import Dimension, Filters
from chakshu.services.settings_store import Key

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
PEOPLE_COLUMNS = ("login", "name", "requested", "prs_reviewed", "auto_reviews", "engaged", "cost_triggered")


def filters(
    days: int = Query(30, ge=1, le=365),
    repo_id: uuid.UUID | None = None,
    reviewer: str | None = Query(None, max_length=100),
    trigger: str | None = Query(None, max_length=30),
) -> Filters:
    return Filters.last(days, repo_id=repo_id, reviewer=reviewer, trigger=trigger)


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


@router.get("/cost")
async def cost(session: SessionDep, _: AdminDep) -> dict:
    return await analytics.cost(session)


@router.get("/findings")
async def findings(
    f: FiltersDep,
    session: SessionDep,
    _: AdminDep,
    skill: str | None = Query(None, max_length=100),
    outcome: str | None = Query(None, pattern="^(open|fixed|dismissed)$"),
) -> list[dict]:
    return await analytics.findings(session, f, skill=skill, outcome=outcome)


async def _people(session: SessionDep, f: Filters) -> dict:
    """The ledger, or why it isn't shown."""
    settings = await analytics.privacy(session)
    if not settings.show_names:
        return {"hidden": "names_off", "min_group": settings.min_group, "rows": []}
    rows = await analytics.people(session, f)
    if not calc.visible(len(rows), settings.min_group):
        return {"hidden": "small_group", "min_group": settings.min_group, "rows": []}
    return {"hidden": None, "min_group": settings.min_group, "rows": rows}


@router.get("/people")
async def people(f: FiltersDep, session: SessionDep, user: AdminDep) -> dict:
    result = await _people(session, f)
    if result["rows"]:
        await analytics.record_access(session, user.login, "view", "people", f)
    return result


@router.get("/people.csv")
async def people_csv(f: FiltersDep, session: SessionDep, user: AdminDep) -> PlainTextResponse:
    result = await _people(session, f)
    if not result["rows"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "There's nothing to export for this selection.")
    await analytics.record_access(session, user.login, "export", "people", f)
    note = "# Chakshu usage per person. For enablement and cost questions, not for judging performance.\n"
    return _csv(note + calc.to_csv(result["rows"], PEOPLE_COLUMNS), "chakshu-people")


@router.get("/me")
async def my_activity(f: FiltersDep, session: SessionDep, user: UserDep) -> dict:
    """The signed-in person's own row: exactly what an admin sees about them."""
    rows = await analytics.people(session, f, login=user.login)
    return {"row": rows[0] if rows else None}


class PrivacyBody(BaseModel):
    show_names: bool
    min_group: int = Field(ge=calc.MIN_GROUP_FLOOR, le=100)


@router.get("/settings")
async def get_privacy(session: SessionDep, _: AdminDep) -> dict:
    settings = await analytics.privacy(session)
    return {"show_names": settings.show_names, "min_group": settings.min_group}


@router.put("/settings")
async def put_privacy(body: PrivacyBody, session: SessionDep, _: AdminDep) -> dict:
    await store.put_many(
        session,
        {
            Key.ANALYTICS_SHOW_NAMES: "true" if body.show_names else "false",
            Key.ANALYTICS_MIN_GROUP: str(body.min_group),
        },
    )
    await session.commit()
    return body.model_dump()
