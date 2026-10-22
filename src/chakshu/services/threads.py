"""Resolve Chakshu's own review threads once the code they pointed at has changed.

A thread is resolved only when all of these hold: its first comment carries a
Chakshu finding marker, GitHub marks it outdated, and the latest review didn't
raise the same finding again. Threads started by people are never touched.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass

from githubkit import GitHub

from chakshu.helpers.findings import MARKER_RE

log = logging.getLogger(__name__)

THREADS_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes { id isResolved isOutdated comments(first: 1) { nodes { body } } }
      }
    }
  }
}
"""

RESOLVE_MUTATION = """
mutation($id: ID!) { resolveReviewThread(input: {threadId: $id}) { thread { id } } }
"""


@dataclass(frozen=True)
class Thread:
    id: str
    resolved: bool
    outdated: bool
    first_comment: str


def to_resolve(threads: Iterable[Thread], still_found: set[str]) -> list[str]:
    """IDs of Chakshu threads that are outdated and whose finding didn't come back."""
    ids = []
    for thread in threads:
        if thread.resolved or not thread.outdated:
            continue
        marker = MARKER_RE.search(thread.first_comment)
        if marker and marker.group(1) not in still_found:
            ids.append(thread.id)
    return ids


async def _threads(client: GitHub, owner: str, name: str, number: int) -> list[Thread]:
    threads, after = [], None
    while True:
        data = await client.async_graphql(
            THREADS_QUERY, {"owner": owner, "name": name, "number": number, "after": after}
        )
        page = data["repository"]["pullRequest"]["reviewThreads"]
        for node in page["nodes"]:
            comments = node["comments"]["nodes"]
            threads.append(
                Thread(
                    node["id"],
                    node["isResolved"],
                    node["isOutdated"],
                    comments[0]["body"] if comments else "",
                )
            )
        if not page["pageInfo"]["hasNextPage"]:
            return threads
        after = page["pageInfo"]["endCursor"]


async def resolve_outdated(client: GitHub, full_name: str, number: int, still_found: set[str]) -> int:
    owner, name = full_name.split("/", 1)
    ids = to_resolve(await _threads(client, owner, name, number), still_found)
    for thread_id in ids:
        await client.async_graphql(RESOLVE_MUTATION, {"id": thread_id})
    if ids:
        log.info("Resolved %s outdated Chakshu thread(s) on %s#%s", len(ids), full_name, number)
    return len(ids)
