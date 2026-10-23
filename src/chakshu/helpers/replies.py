"""Decide whether to answer a reply to one of Chakshu's review comments. Pure functions.

A thread is Chakshu's when its first comment was posted by the app and carries
a finding marker. GitHub points every reply at that first comment.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from chakshu.helpers.findings import MARKER_RE
from chakshu.helpers.prompt import ThreadComment

# Answers Chakshu gives in one thread, so two people (or one stubborn one) can't run up the bill.
MAX_ANSWERS_PER_THREAD = 5


@dataclass(frozen=True)
class Comment:
    id: int
    in_reply_to: int | None
    author: str
    body: str


def bot_login(app_slug: str) -> str:
    return f"{app_slug}[bot]"


def finding_id(root_body: str | None, root_author: str | None, app_slug: str) -> str | None:
    """The finding a thread is about, or None if Chakshu didn't start it."""
    if (root_author or "").lower() != bot_login(app_slug).lower():
        return None
    marker = MARKER_RE.search(root_body or "")
    return marker.group(1) if marker else None


def may_answer(replier: str, pr_author: str | None, *, writer: bool) -> bool:
    """The pull request's author, or anyone who could ask for a review (write access)."""
    return writer or replier.lower() == (pr_author or "").lower()


def conversation(comments: Iterable[Comment], root_id: int) -> list[ThreadComment]:
    """The thread oldest first: its first comment, then the replies. `comments` come in posting order."""
    thread = [c for c in comments if c.id == root_id or c.in_reply_to == root_id]
    thread.sort(key=lambda c: c.id != root_id)  # stable: replies keep their order
    return [ThreadComment(author=c.author, body=c.body) for c in thread]
