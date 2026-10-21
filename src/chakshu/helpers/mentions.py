"""Spot a request for Chakshu in a pull request comment."""

import re

# The empty org team people mention or request: @<org>/chakshu.
HANDLE_TEAM = "chakshu"


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
