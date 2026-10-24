"""Spot a request for Chakshu in a pull request comment."""

import re

# The empty org team people mention or request: @<org>/chakshu.
HANDLE_TEAM = "chakshu"
# Each reviewer also gets a child team, chakshu-<name>, so it can be picked in a PR's Reviewers box.
REVIEWER_TEAM_PREFIX = f"{HANDLE_TEAM}-"
# In the description of every reviewer team Chakshu creates, so it only ever removes its own.
TEAM_MARKER = "Managed by Chakshu."


def reviewer_team(name: str) -> str:
    """The team slug for a reviewer. Reviewer names are already valid slugs."""
    return f"{REVIEWER_TEAM_PREFIX}{name}"


def reviewer_from_team(slug: str | None) -> str | None:
    """The reviewer a requested team stands for, or None for any other team."""
    if not slug or not slug.startswith(REVIEWER_TEAM_PREFIX):
        return None
    return slug[len(REVIEWER_TEAM_PREFIX) :] or None


def handle(org: str) -> str:
    return f"@{org}/{HANDLE_TEAM}"


def parse_request(body: str, org: str) -> str | None:
    """The note that follows the mention ('' if none), or None if Chakshu wasn't called.

    Matches `@<org>/chakshu` anywhere outside quoted lines and code blocks, and
    `/chakshu` at the start of a line (for personal repos, which have no teams).
    """
    text = re.sub(r"```.*?```", "", body or "", flags=re.S)
    lines = [line for line in text.splitlines() if not line.lstrip().startswith(">")]
    mention = re.compile(
        rf"(?<![\w/-])(?:@{re.escape(org)}/{HANDLE_TEAM}|^\s*/{HANDLE_TEAM})(?![\w-])(.*)$", re.IGNORECASE
    )
    for line in lines:
        match = mention.search(line)
        if match:
            return match.group(1).strip(" \t:,-")
    return None
