"""Arithmetic behind the analytics pages. Pure functions, no I/O.

Definitions the portal relies on:
- fix rate: fixed / (fixed + dismissed). Open findings have no verdict yet and
  are left out, the same "acted on" denominator Qodo uses.
- dismissed rate: dismissed / (fixed + dismissed), the noise signal.
- engaged: a run someone asked for (mention, review request, portal, reply),
  as opposed to `auto`, which ran because a reviewer opted in to PR events.
- a person's activity state in a slice: `engaged` if they asked for any
  review, `auto_only` if they didn't but their pull requests were reviewed,
  `none` otherwise.
"""

import base64
import csv
import io
import uuid
from calendar import monthrange
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal

ENGAGED_TRIGGERS = ("mention", "review_requested", "portal", "reply")
MIN_GROUP_FLOOR = 3  # the smallest group size an admin may choose, other than off
MIN_GROUP_OFF = 1  # never hide small groups
MIN_GROUP_MAX = 100

ActivityState = Literal["engaged", "auto_only", "none"]
PeopleSort = Literal["name", "last_activity", "requested", "prs_reviewed", "cost"]
SORT_FIELD = {"requested": "requested", "prs_reviewed": "prs_reviewed", "cost": "cost_triggered"}
OTHER = "Other"


def ratio(part: float, whole: float) -> float | None:
    return round(part / whole, 4) if whole else None


def fix_rate(fixed: int, dismissed: int) -> float | None:
    return ratio(fixed, fixed + dismissed)


def dismissed_rate(fixed: int, dismissed: int) -> float | None:
    return ratio(dismissed, fixed + dismissed)


def per_unit(cost: Decimal | float | None, units: int) -> float | None:
    """Cost per review, per fixed finding and so on. None when there's nothing to divide by."""
    return round(float(cost or 0) / units, 4) if units else None


def change(current: float | None, previous: float | None) -> float | None:
    """Relative change from the previous period, or None when it can't be stated honestly."""
    if current is None or not previous:
        return None
    return round((current - previous) / previous, 4)


def valid_min_group(value: int) -> bool:
    return value == MIN_GROUP_OFF or MIN_GROUP_FLOOR <= value <= MIN_GROUP_MAX


def visible(people: int, min_group: int) -> bool:
    """Grouped numbers about fewer people than `min_group` are hidden. Zero people hides nothing."""
    if min_group == MIN_GROUP_OFF:
        return True
    return people == 0 or people >= max(min_group, MIN_GROUP_FLOOR)


def activity_state(requested: int, prs_reviewed: int) -> ActivityState:
    if requested:
        return "engaged"
    return "auto_only" if prs_reviewed else "none"


def sort_people(rows: list[dict], sort: PeopleSort, order: Literal["asc", "desc"]) -> list[dict]:
    """Sort directory rows. Ties break by login (A to Z), and people with no activity date go last."""
    rows = sorted(rows, key=lambda r: r["login"].lower())
    reverse = order == "desc"
    if sort == "name":
        return sorted(rows, key=lambda r: (r["name"] or r["login"]).lower(), reverse=reverse)
    if sort == "last_activity":
        dated = [r for r in rows if r["last_activity_at"]]
        undated = [r for r in rows if not r["last_activity_at"]]
        return sorted(dated, key=lambda r: r["last_activity_at"], reverse=reverse) + undated
    return sorted(rows, key=lambda r: r[SORT_FIELD[sort]], reverse=reverse)


def page(rows: list[dict], number: int, size: int) -> list[dict]:
    start = (number - 1) * size
    return rows[start : start + size]


def top_with_other(
    rows: list[dict], limit: int, label: str, sums: Sequence[str], **other: object
) -> list[dict]:
    """The first `limit` rows, then one row named Other adding up the rest. Rows come sorted."""
    if len(rows) <= limit:
        return rows
    rest = rows[limit:]
    total = {k: round(sum(r[k] for r in rest), 4) for k in sums}
    return rows[:limit] + [{label: OTHER, **other, **total}]


def last_days(end: datetime, count: int) -> list[date]:
    """The `count` calendar days ending on `end`'s day, oldest first."""
    last = end.date()
    return [last - timedelta(days=n) for n in range(count - 1, -1, -1)]


def encode_cursor(created_at: datetime, row_id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(f"{created_at.isoformat()},{row_id}".encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    """Raises ValueError for a cursor this module didn't make."""
    try:
        when, row_id = base64.urlsafe_b64decode(cursor.encode()).decode().split(",")
        return datetime.fromisoformat(when), uuid.UUID(row_id)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("bad cursor") from exc


@dataclass(frozen=True)
class Forecast:
    month_to_date: float
    projected: float  # straight-line projection to the end of the month
    cap: float | None
    cap_hit_on: date | None  # when the cap is reached at the current daily rate, if this month


def forecast(spent: float, cap: float | None, today: date) -> Forecast:
    days_in_month = monthrange(today.year, today.month)[1]
    per_day = spent / today.day
    projected = round(per_day * days_in_month, 4)
    hit_on = None
    if cap and per_day > 0:
        if spent >= cap:
            hit_on = today
        else:
            days_left = (cap - spent) / per_day
            day = today + timedelta(days=int(days_left) + 1)
            hit_on = day if day.month == today.month else None
    return Forecast(month_to_date=round(spent, 4), projected=projected, cap=cap, cap_hit_on=hit_on)


def days(start: datetime, end: datetime) -> list[date]:
    """Every calendar day in [start, end], so charts have no gaps."""
    first, last = start.date(), end.date()
    return [first + timedelta(days=n) for n in range((last - first).days + 1)]


def to_csv(rows: Iterable[dict], columns: Sequence[str]) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(columns), extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()
