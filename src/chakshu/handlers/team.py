"""team and membership: keep teams and dated memberships current between nightly syncs."""

from chakshu.handlers.context import Context, Payload, installation_for
from chakshu.services import teams


async def handle_team(ctx: Context, payload: Payload) -> None:
    team = payload.get("team")
    install = await installation_for(ctx, payload)
    if not team or install is None:
        return
    await teams.apply_team(ctx.session, install, payload.get("action", ""), team)


async def handle_membership(ctx: Context, payload: Payload) -> None:
    team, member = payload.get("team"), payload.get("member") or {}
    if payload.get("scope") != "team" or not team or not member.get("login"):
        return
    install = await installation_for(ctx, payload)
    if install is None:
        return
    await teams.apply_membership(ctx.session, install, payload.get("action", ""), team, member["login"])
