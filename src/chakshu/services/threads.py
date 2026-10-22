"""Chakshu's review threads: resolve the ones that are done, and read what became of each finding.

Only threads whose first comment carries a Chakshu finding marker are looked at;
threads people started are never touched.

- Chakshu resolves a thread when GitHub marks it outdated (the code changed) and
  the latest review didn't raise the same finding again. Outcome: fixed.
- A thread someone else resolved after the code changed: fixed.
- A thread someone resolved while the code is unchanged: dismissed.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field

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


@dataclass
class Scan:
    resolve: list[str] = field(default_factory=list)  # thread IDs Chakshu should resolve now
    fixed: set[str] = field(default_factory=set)  # finding IDs
    dismissed: set[str] = field(default_factory=set)


def classify(threads: Iterable[Thread], still_found: set[str]) -> Scan:
    scan = Scan()
    for thread in threads:
        marker = MARKER_RE.search(thread.first_comment)
        if not marker:
            continue
        finding_id = marker.group(1)
        if thread.resolved:
            (scan.fixed if thread.outdated else scan.dismissed).add(finding_id)
        elif thread.outdated and finding_id not in still_found:
            scan.resolve.append(thread.id)
            scan.fixed.add(finding_id)
    return scan


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


async def tidy(client: GitHub, full_name: str, number: int, still_found: set[str]) -> Scan:
    """Resolve finished Chakshu threads and return the outcome of every Chakshu thread."""
    owner, name = full_name.split("/", 1)
    scan = classify(await _threads(client, owner, name, number), still_found)
    for thread_id in scan.resolve:
        await client.async_graphql(RESOLVE_MUTATION, {"id": thread_id})
    if scan.resolve:
        log.info("Resolved %s outdated Chakshu thread(s) on %s#%s", len(scan.resolve), full_name, number)
    return scan
