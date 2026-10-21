"""`@<org>/chakshu` in a pull request comment."""

from chakshu.handlers.context import Context, Payload, resolve
from chakshu.helpers import mentions
from chakshu.services import github, triggers


async def handle(ctx: Context, payload: Payload) -> None:
    issue = payload.get("issue") or {}
    if payload.get("action") != "created" or "pull_request" not in issue:
        return
    if (payload.get("sender") or {}).get("type") == "Bot":
        return
    resolved = await resolve(ctx, payload)
    if resolved is None:
        return
    installation, repo = resolved
    comment = payload["comment"]
    note = mentions.parse_request(comment.get("body", ""), installation.account_login)
    if note is None:
        return

    owner, name = repo.full_name.split("/", 1)
    client = github.installation_client(ctx.creds, installation.github_id)
    await client.rest.reactions.async_create_for_issue_comment(owner, name, comment["id"], content="eyes")

    request = triggers.ReviewRequest(
        installation=installation,
        repo=repo,
        pr_number=issue["number"],
        trigger="mention",
        source_id=str(comment["id"]),
        requester=payload["sender"]["login"],
        note=note,
    )
    outcome = await triggers.request_review(ctx.session, ctx.creds, request)
    if outcome.refused:
        await triggers.reply(ctx.creds, request, outcome.refused)
