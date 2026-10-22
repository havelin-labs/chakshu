from fastapi import APIRouter, Query

from chakshu.api.deps import UserDep
from chakshu.db.session import SessionDep
from chakshu.services import finding_stats

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/skills")
async def skill_stats(session: SessionDep, _: UserDep, days: int = Query(90, ge=1, le=365)) -> list[dict]:
    return await finding_stats.per_skill(session, days)
