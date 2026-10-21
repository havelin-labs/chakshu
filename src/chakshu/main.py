import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from chakshu import __version__
from chakshu.api import health, session, setup
from chakshu.api.spa import mount_spa
from chakshu.core import crypto
from chakshu.core.config import get_settings
from chakshu.core.logging import configure_logging
from chakshu.db.session import get_sessionmaker
from chakshu.services import setup as setup_service

log = logging.getLogger("chakshu")


async def _announce_setup_code() -> None:
    """Until the GitHub App exists, print the one-time code that claims this instance."""
    try:
        async with get_sessionmaker()() as db:
            code = await setup_service.ensure_setup_code(db)
    except Exception:  # noqa: BLE001 - the DB may not be ready; /readyz reports that
        log.warning("Couldn't check setup state; is the database up?", exc_info=True)
        return
    if code:
        log.warning("Setup code: %s  (enter it at %s/setup)", code, get_settings().base_url)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await _announce_setup_code()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    crypto.require_secret_key()

    app = FastAPI(title="Chakshu", version=__version__, docs_url=None, redoc_url=None, lifespan=lifespan)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="chakshu_session",
        max_age=int(timedelta(days=14).total_seconds()),
        same_site="lax",
        https_only=settings.secure_cookies,
    )
    for module in (health, session, setup):
        app.include_router(module.router)
    # Registered last: its catch-all route must not shadow the API.
    mount_spa(app, Path(settings.frontend_dir))
    return app
