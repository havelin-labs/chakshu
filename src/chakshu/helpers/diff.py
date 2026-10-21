"""Which lines of a file GitHub will accept a review comment on."""

import re

HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def commentable_lines(patch: str | None) -> set[int]:
    """New-file line numbers inside the diff hunks (added and context lines)."""
    lines: set[int] = set()
    current: int | None = None
    for raw in (patch or "").splitlines():
        header = HUNK.match(raw)
        if header:
            current = int(header.group(1))
            continue
        if current is None or raw.startswith("\\"):
            continue
        if raw.startswith("-"):
            continue
        lines.add(current)
        current += 1
    return lines
