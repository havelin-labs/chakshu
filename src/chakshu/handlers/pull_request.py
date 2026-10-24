"""Pull request events: review requests (the chakshu team or a reviewer's own team), automatic runs,
closing, and review speed."""

from chakshu.handlers.context import Context, Payload, installation_for, resolve
from chakshu.helpers import mentions
from chakshu.services import finding_stats, github, installations, review_speed, triggers

AUTO_ACTIONS = frozenset({"opened", "reopened", "ready_for_review", "synchronize"})


async def _closed(ctx: Context, payload: Payload) -> None:
    """Last chance to read what became of Chakshu's findings on this PR."""
    resolved = await resolve(ctx, payload)
    if resolved is None:
        return
    installation, repo = resolved
    client = github.installation_client(ctx.creds, installation.github_id)
    await finding_stats.sweep(ctx.session, client, repo.full_name, payload["pull_request"]["number"], set())


async def record_speed(ctx: Context, payload: Payload) -> None:
    """Review speed covers every repo, including ones Chakshu doesn't review, for the comparison."""
    installation = await installation_for(ctx, payload)
    if installation is None or not payload.get("repository") or not payload.get("pull_request"):
        return
    repo = await installations.ensure_repo(ctx.session, ctx.creds, installation, payload["repository"])
    if review := payload.get("review"):
        await review_speed.from_review(ctx.session, repo, review, payload["pull_request"])
    else:
        await review_speed.from_pull_request(
            ctx.session, repo, payload.get("action"), payload["pull_request"]
        )


async def handle(ctx: Context, payload: Payload) -> None:
    action = payload.get("action")
    pr = payload.get("pull_request") or {}
    await record_speed(ctx, payload)
    requested_team = (payload.get("requested_team") or {}).get("slug")
    named = mentions.reviewer_from_team(requested_team)

    if action == "closed":
        await _closed(ctx, payload)
        return
    if action == "review_requested" and requested_team == mentions.HANDLE_TEAM:
        trigger, requester, event, reviewers = "review_requested", payload["sender"]["login"], None, None
    elif action == "review_requested" and named:
        # A reviewer's own team (chakshu-<name>): run just that reviewer.
        trigger, requester, event, reviewers = "review_requested", payload["sender"]["login"], None, [named]
    elif action in AUTO_ACTIONS and not pr.get("draft"):
        trigger, requester, event, reviewers = "auto", None, action, None
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
        reviewers=reviewers,
    )
    outcome = await triggers.request_review(ctx.session, ctx.creds, request)
    if outcome.refused and requester:
        await triggers.reply(ctx.creds, request, outcome.refused)
    if requester and not outcome.queued:
        # Nothing new will run (refused, or already reviewed at this commit), so nothing would clear
        # the request later. Clear it now so the PR doesn't wait on it.
        await triggers.clear_team_request(
            ctx.creds, installation.github_id, repo.full_name, request.pr_number, teams=[requested_team or ""]
        )
