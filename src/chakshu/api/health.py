from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from chakshu import __version__
from chakshu.db.session import SessionDep

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness: the process is up and serving requests."""
    return {"status": "ok", "version": __version__}


@router.get("/readyz")
async def readyz(session: SessionDep) -> JSONResponse:
    """Readiness: the database answers."""
    try:
        await session.execute(text("select 1"))
    except Exception as exc:  # noqa: BLE001 - any DB failure means not ready
        return JSONResponse({"status": "unavailable", "detail": type(exc).__name__}, status_code=503)
    return JSONResponse({"status": "ok"})
