"""Text Chakshu posts on pull requests. Kept together so the voice stays consistent."""

from collections.abc import Iterable

MARKER = "<!-- chakshu -->"


def needs_write_access(login: str) -> str:
    return f"{MARKER}\n@{login} only people with write access to this repository can ask for a review."


def nothing_matched(login: str | None, owners: Iterable[tuple[str, str]]) -> str:
    who = f"@{login} " if login else ""
    owners = list(owners)
    if not owners:
        return (
            f"{MARKER}\n{who}no reviewer covers this repository yet. "
            "A team can add one in the reviewers repo; "
            "see https://chakshu.havelin.in/docs/concepts/reviewers/"
        )
    listed = "\n".join(f"- `{name}`, owned by @{team}" for name, team in owners)
    return (
        f"{MARKER}\n{who}none of the reviewers for this repository belong to your teams, "
        f"and there's no `default` reviewer. These cover it:\n\n{listed}\n\n"
        "Ask someone on one of those teams, or have your team add its own reviewer."
    )


def over_budget(login: str | None, spent: float, cap: float) -> str:
    who = f"@{login} " if login else ""
    return (
        f"{MARKER}\n{who}reviews are paused: this month's spend (${spent:.2f}) has reached the "
        f"${cap:.2f} cap. An admin can raise it in Chakshu's settings."
    )


def queued(names: Iterable[str]) -> str:
    return f"{MARKER}\nQueued: " + ", ".join(f"`{n}`" for n in names)
