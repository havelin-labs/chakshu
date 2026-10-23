"""Text Chakshu posts on pull requests. Kept together so the voice stays consistent."""

from collections.abc import Iterable

MARKER = "<!-- chakshu -->"


def needs_write_access(login: str) -> str:
    return f"{MARKER}\n@{login} only people with write access to this repository can ask for a review."


def _listed(names: Iterable[str]) -> str:
    return "\n".join(f"- `{name}`" for name in names)


def nothing_matched(login: str | None, handle: str, names: Iterable[str]) -> str:
    """No reviewer covers the repo and files. `names` are the reviewers that could be called by name."""
    who = f"@{login} " if login else ""
    names = list(names)
    if not names:
        return (
            f"{MARKER}\n{who}there are no reviewers yet. "
            "A team can add one in the reviewers repo; "
            "see https://chakshu.havelin.in/docs/concepts/reviewers/"
        )
    return (
        f"{MARKER}\n{who}no reviewer covers this repository and these files, "
        f"and there's no `default` reviewer. Name one to run it anyway, "
        f"for example `{handle} {names[0]}`. These are available:\n\n{_listed(names)}"
    )


def unknown_reviewers(login: str | None, unknown: Iterable[str], names: Iterable[str]) -> str:
    who = f"@{login} " if login else ""
    missing = ", ".join(f"`{n}`" for n in unknown)
    return (
        f"{MARKER}\n{who}there's no working reviewer called {missing}. Try one of these:\n\n{_listed(names)}"
    )


def over_budget(login: str | None, spent: float, cap: float) -> str:
    who = f"@{login} " if login else ""
    return (
        f"{MARKER}\n{who}reviews are paused: this month's spend (${spent:.2f}) has reached the "
        f"${cap:.2f} cap. An admin can raise it in Chakshu's settings."
    )


def queued(names: Iterable[str]) -> str:
    return f"{MARKER}\nQueued: " + ", ".join(f"`{n}`" for n in names)
