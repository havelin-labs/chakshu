"""Serve the built React portal.

Static files come from CHAKSHU_FRONTEND_DIR (frontend/dist). Any other GET
that isn't an API route returns index.html, so client-side routes like
/reviewers work on a hard refresh. If the build is missing (API-only
development), nothing is mounted and Vite's dev server serves the UI instead.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Paths the SPA fallback must never swallow.
RESERVED_PREFIXES = ("api/", "webhooks/", "auth/", "healthz", "readyz")


def mount_spa(app: FastAPI, dist: Path) -> bool:
    index = dist / "index.html"
    if not index.is_file():
        return False

    root = dist.resolve()
    app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

    # Plain def: FastAPI runs it in a thread, so the filesystem checks don't block the loop.
    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith(RESERVED_PREFIXES):
            raise HTTPException(status_code=404)
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(index)

    return True
