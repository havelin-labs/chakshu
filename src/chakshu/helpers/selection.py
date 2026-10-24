"""Which reviewers apply to a pull request. Pure functions, no I/O.

People can name reviewers (`@org/chakshu security perf`), and those run whatever
their repos and paths say. Otherwise:

1. repos:  the reviewer covers this repository (glob on the repo name)
2. paths:  at least one changed file matches (no paths means every file)
3. event:  for automatic runs, the reviewer opted in to this PR event
Nothing left and someone asked: fall back to the org's `default` reviewer.
`default` is also an ordinary reviewer: if its own repos and paths cover the pull
request (the template uses repos ["*"]), it runs alongside the others, not only as
the fallback. To run just one reviewer, name it or request its own team (chakshu-<name>).
"""

import re
from collections.abc import Iterable, Sequence
from fnmatch import fnmatchcase
from typing import Protocol

import pathspec

DEFAULT_REVIEWER = "default"


class ReviewerLike(Protocol):
    name: str
    owner_team: str
    repos: list[str]
    paths: list[str]
    auto: list[str]
    errors: list[str]


def covers_repo(patterns: Iterable[str], full_name: str) -> bool:
    short = full_name.split("/", 1)[-1].lower()
    return any(fnmatchcase(short, p.lower()) or fnmatchcase(full_name.lower(), p.lower()) for p in patterns)


def touches_paths(patterns: Sequence[str], changed_files: Iterable[str]) -> bool:
    if not patterns:
        return True
    spec = pathspec.PathSpec.from_lines("gitwildmatch", patterns)
    return any(spec.match_file(path) for path in changed_files)


def applicable[R: ReviewerLike](
    reviewers: Iterable[R], full_name: str, changed_files: Sequence[str], *, event: str | None = None
) -> list[R]:
    """Steps 1-3: healthy reviewers that cover this repo, these files and (if automatic) this event."""
    return [
        r
        for r in reviewers
        if not r.errors
        and covers_repo(r.repos, full_name)
        and touches_paths(r.paths, changed_files)
        and (event is None or event in r.auto)
    ]


_LEADING_WORD = re.compile(r"([^\s,:]+)[\s,:]*")


def pick_named[R: ReviewerLike](reviewers: Iterable[R], note: str) -> tuple[list[R], str]:
    """Reviewers named at the start of the note, and what's left of the note.

    Names match healthy reviewers without regard to case, separated by spaces or
    commas: "security, perf check refunds" picks security and perf, leaving "check refunds".
    """
    by_name = {r.name.lower(): r for r in reviewers if not r.errors}
    picked: list[R] = []
    rest = note.strip()
    while match := _LEADING_WORD.match(rest):
        reviewer = by_name.get(match.group(1).lower())
        if reviewer is None:
            break
        if reviewer not in picked:
            picked.append(reviewer)
        rest = rest[match.end() :]
    return picked, rest


def by_names[R: ReviewerLike](reviewers: Iterable[R], names: Iterable[str]) -> tuple[list[R], list[str]]:
    """Healthy reviewers with these names, and the names that matched none."""
    by_name = {r.name.lower(): r for r in reviewers if not r.errors}
    picked: list[R] = []
    unknown: list[str] = []
    for name in names:
        reviewer = by_name.get(name.strip().lower())
        if reviewer is None:
            unknown.append(name)
        elif reviewer not in picked:
            picked.append(reviewer)
    return picked, unknown


def fallback[R: ReviewerLike](reviewers: Iterable[R], full_name: str) -> list[R]:
    return [
        r
        for r in reviewers
        if r.name == DEFAULT_REVIEWER and not r.errors and covers_repo(r.repos, full_name)
    ]
