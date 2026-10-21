from fastapi import FastAPI

from chakshu import __version__
from chakshu.api import health
from chakshu.core.config import get_settings
from chakshu.core.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="Chakshu", version=__version__, docs_url=None, redoc_url=None)
    app.include_router(health.router)
    return app
