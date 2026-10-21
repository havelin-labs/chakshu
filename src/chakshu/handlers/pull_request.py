"""Pull request events: review requests for the chakshu team and automatic runs."""

from chakshu.handlers.context import Context, Payload, resolve
from chakshu.helpers import mentions
from chakshu.services import triggers

AUTO_ACTIONS = frozenset({"opened", "reopened", "ready_for_review", "synchronize"})


async def handle(ctx: Context, payload: Payload) -> None:
    action = payload.get("action")
    pr = payload.get("pull_request") or {}
    requested_team = (payload.get("requested_team") or {}).get("slug")

    if action == "review_requested" and requested_team == mentions.HANDLE_TEAM:
        trigger, requester, event = "review_requested", payload["sender"]["login"], None
    elif action in AUTO_ACTIONS and not pr.get("draft"):
        trigger, requester, event = "auto", None, action
    else:
        return

    resolved = await resolve(ctx, payload)
    if resolved is None:
        return
    installation, repo = resolved
    request = triggers.ReviewRequest(
        installation=installation,
        repo=repo,
        pr_number=pr["number"],
        trigger=trigger,
        source_id=ctx.delivery_id,
        requester=requester,
        event=event,
    )
    outcome = await triggers.request_review(ctx.session, ctx.creds, request)
    if outcome.refused and requester:
        await triggers.reply(ctx.creds, request, outcome.refused)
        await triggers.clear_team_request(
            ctx.creds, installation.github_id, repo.full_name, request.pr_number
        )
