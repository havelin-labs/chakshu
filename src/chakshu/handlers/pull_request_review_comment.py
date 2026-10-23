"""A reply in a review thread. Chakshu answers when the thread is one of its findings."""

from chakshu.handlers.context import Context, Payload, resolve
from chakshu.services import replies


async def handle(ctx: Context, payload: Payload) -> None:
    comment = payload.get("comment") or {}
    if payload.get("action") != "created" or not comment.get("in_reply_to_id"):
        return
    # Chakshu's own answers, and other apps, never get one.
    if (payload.get("sender") or {}).get("type") == "Bot":
        return
    resolved = await resolve(ctx, payload)
    if resolved is None:
        return
    installation, repo = resolved
    pr = payload["pull_request"]
    reply = replies.Reply(
        installation=installation,
        repo=repo,
        pr_number=pr["number"],
        pr_title=pr.get("title") or "",
        pr_author=(pr.get("user") or {}).get("login"),
        head_sha=pr["head"]["sha"],
        comment_id=comment["id"],
        root_id=comment["in_reply_to_id"],
        author=payload["sender"]["login"],
    )
    await replies.request(ctx.session, ctx.creds, reply)
