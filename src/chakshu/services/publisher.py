"""Post a finished review: one GitHub review with inline comments, nothing repeated."""

import logging
import uuid
from dataclasses import dataclass

from githubkit import GitHub
from githubkit.exception import RequestFailed

from chakshu.helpers import findings as f
from chakshu.helpers.diff import commentable_lines

log = logging.getLogger(__name__)


@dataclass
class Published:
    review_url: str | None
    plan: f.Plan
    chosen: list[f.Finding]
    # IDs of everything the agent found this time, posted or not; older threads for these stay open.
    found_ids: set[str]


async def _markers(client: GitHub, owner: str, repo: str, number: int) -> set[str]:
    comments = [
        c.body
        async for c in client.rest.paginate(client.rest.pulls.async_list_review_comments, owner, repo, number)
    ]
    reviews = [
        r.body async for r in client.rest.paginate(client.rest.pulls.async_list_reviews, owner, repo, number)
    ]
    return f.existing_markers(comments + reviews)


async def publish(
    client: GitHub,
    *,
    full_name: str,
    number: int,
    head_sha: str,
    reviewer: str,
    summary: str,
    raw_findings: list[dict],
    patches: dict[str, str | None],
    limits: dict,
    ns: uuid.UUID,
    pr_key: uuid.UUID,
    reviewer_id: uuid.UUID,
) -> Published:
    owner, repo = full_name.split("/", 1)
    parsed = [f.Finding.parse(raw) for raw in raw_findings]
    found_ids = {str(f.identify(ns, pr_key, reviewer_id, finding).id) for finding in parsed}
    chosen = f.choose(parsed, limits.get("min_severity") or "medium", int(limits.get("max_findings") or 10))
    items = [f.identify(ns, pr_key, reviewer_id, finding) for finding in chosen]
    commentable = {path: commentable_lines(patch) for path, patch in patches.items()}
    plan = f.plan(items, commentable, await _markers(client, owner, repo, number))

    if not plan.new and plan.repeats:
        return Published(review_url=None, plan=plan, chosen=chosen, found_ids=found_ids)

    try:
        review = await _post(client, owner, repo, number, head_sha, reviewer, summary, plan)
    except RequestFailed as exc:
        if exc.response.status_code != 422 or not plan.inline:
            raise
        # GitHub disagreed about a line being in the diff. Keep everything, just not inline.
        log.warning("Inline comments rejected on %s#%s; posting as summary", full_name, number)
        plan = f.Plan(summary_only=plan.inline + plan.summary_only, repeats=plan.repeats)
        review = await _post(client, owner, repo, number, head_sha, reviewer, summary, plan)
    return Published(review_url=review.html_url, plan=plan, chosen=chosen, found_ids=found_ids)


async def _post(client, owner, repo, number, head_sha, reviewer, summary, plan: f.Plan):
    comments = [
        {
            "path": i.finding.path,
            "line": i.finding.line,
            "side": "RIGHT",
            "body": f.render_comment(i, reviewer),
        }
        for i in plan.inline
    ]
    resp = await client.rest.pulls.async_create_review(
        owner,
        repo,
        number,
        commit_id=head_sha,
        event="COMMENT",
        body=f.render_review_body(reviewer, summary, plan),
        comments=comments,
    )
    return resp.parsed_data
