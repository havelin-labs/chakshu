"""A push to the reviewers repo's default branch resyncs that org's reviewers."""

from chakshu.handlers.context import Context, Payload, resolve
from chakshu.services import catalog


async def handle(ctx: Context, payload: Payload) -> None:
    repository = payload.get("repository") or {}
    if payload.get("ref") != f"refs/heads/{repository.get('default_branch')}":
        return
    resolved = await resolve(ctx, payload)
    if resolved is None:
        return
    installation, repo = resolved
    reviewers_repo = await catalog.reviewers_repo(ctx.session, installation)
    if reviewers_repo is not None and reviewers_repo.id == repo.id:
        await catalog.sync_installation(ctx.session, ctx.creds, installation)
