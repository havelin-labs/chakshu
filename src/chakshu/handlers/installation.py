"""installation and installation_repositories: keep orgs, repos and reviewers current."""

from chakshu.handlers.context import Context, Payload, installation_for
from chakshu.services import catalog, installations


async def handle(ctx: Context, payload: Payload) -> None:
    github_id = payload["installation"]["id"]
    if payload.get("action") == "deleted":
        await installations.remove_installation(ctx.session, github_id)
        return
    await installations.sync_installation(ctx.session, ctx.creds, github_id)
    installation = await installation_for(ctx, payload)
    if installation is not None and not installation.suspended:
        await catalog.sync_installation(ctx.session, ctx.creds, installation)
