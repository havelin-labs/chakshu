"""Spend alerts and the weekly digest: when to send and what to say. Pure functions, no I/O.

Messages are Slack mrkdwn. The digest describes the organization, repositories
and skills only; it never names people.
"""

from collections.abc import Iterable
from datetime import date

DEFAULT_THRESHOLDS = (50, 80, 100)


def parse_thresholds(text: str | None) -> list[int]:
    """'80, 50,100' -> [50, 80, 100]. Ignores anything that isn't a percentage from 1 to 200."""
    values = set()
    for part in (text or "").replace(" ", "").split(","):
        if part.isdigit() and 1 <= int(part) <= 200:
            values.add(int(part))
    return sorted(values)


def due(spent: float, cap: float | None, thresholds: Iterable[int], already: Iterable[int]) -> list[int]:
    """Thresholds this month's spend has crossed that haven't been announced yet."""
    if not cap:
        return []
    used = spent / cap * 100
    sent = set(already)
    return [t for t in sorted(thresholds) if used >= t and t not in sent]


def month_key(day: date) -> str:
    return f"{day.year}-{day.month:02d}"


def week_key(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def money(value: float | None) -> str:
    return "none" if value is None else f"${value:,.2f}"


def spend_message(
    threshold: int, spent: float, cap: float, projected: float, cap_hit_on: str | None, link: str
) -> str:
    lines = [
        f":warning: *Chakshu has used {threshold}% of this month's review budget.*",
        f"Spent {money(spent)} of {money(cap)}. "
        f"At this month's rate it reaches {money(projected)} by month end.",
    ]
    if threshold >= 100:
        lines.append("New reviews are paused until the cap is raised or the month ends.")
    elif cap_hit_on:
        lines.append(f"The cap would be reached around {cap_hit_on}.")
    lines.append(f"<{link}|Open the cost view>")
    return "\n".join(lines)


def digest_message(week: str, data: dict, link: str) -> str:
    """The weekly summary. `data` holds totals, fixed by severity, the noisiest skill and top repos."""
    totals = data["totals"]
    lines = [
        f"*Chakshu weekly digest, {week}*",
        f"• {totals['reviews']} reviews on {totals['prs']} pull requests, {money(totals['spend'])} spent"
        + (f" ({money(data['month_spend'])} of {money(data['cap'])} this month)" if data.get("cap") else ""),
        f"• {totals['posted']} findings posted, {totals['fixed']} fixed, {totals['dismissed']} dismissed",
    ]
    fixed = data.get("fixed_by_severity") or {}
    if fixed:
        lines.append("• Fixed by severity: " + ", ".join(f"{s} {n}" for s, n in fixed.items()))
    noisy = data.get("noisiest_skill")
    if noisy:
        lines.append(
            f"• Most dismissed skill: `{noisy['key']}` "
            f"({round(noisy['dismissed_rate'] * 100)}% of "
            f"{noisy['fixed'] + noisy['dismissed']} with a verdict)"
        )
    repos = data.get("top_repos") or []
    if repos:
        lines.append("• Most spend: " + ", ".join(f"{r['key']} {money(r['spend'])}" for r in repos))
    lines.append(f"<{link}|Open analytics>")
    return "\n".join(lines)
