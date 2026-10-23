"""organization: keep the People directory's member list current between syncs."""

from chakshu.handlers.context import Context, Payload
from chakshu.services import members


async def handle(ctx: Context, payload: Payload) -> None:
    action = payload.get("action")
    membership = payload.get("membership") or {}
    user = membership.get("user") or {}
    login = user.get("login")
    if not login:
        return  # member_invited and renames carry no membership to apply
    if action == "member_added":
        await members.mark_added(ctx.session, login, user.get("avatar_url"), membership.get("role"))
    elif action == "member_removed":
        await members.mark_removed(ctx.session, login)
