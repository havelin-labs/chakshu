"""Arithmetic behind the analytics pages. Pure functions, no I/O.

Definitions the portal relies on:
- fix rate: fixed / (fixed + dismissed). Open findings have no verdict yet and
  are left out, the same "acted on" denominator Qodo uses.
- dismissed rate: dismissed / (fixed + dismissed), the noise signal.
- engaged: a run someone asked for (mention, review request, portal, reply),
  as opposed to `auto`, which ran because a reviewer opted in to PR events.
"""

import csv
import io
from calendar import monthrange
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

ENGAGED_TRIGGERS = ("mention", "review_requested", "portal", "reply")
MIN_GROUP_FLOOR = 3  # the smallest group size an admin may choose


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


def visible(people: int, min_group: int) -> bool:
    """Grouped numbers about fewer people than `min_group` are hidden. Zero people hides nothing."""
    return people == 0 or people >= max(min_group, MIN_GROUP_FLOOR)


@dataclass(frozen=True)
class Forecast:
    month_to_date: float
    projected: float  # straight-line projection to the end of the month
    cap: float | None
    cap_hit_on: date | None  # when the cap is reached at the current daily rate, if this month


def forecast(spent: float, cap: float | None, today: date) -> Forecast:
    days_in_month = monthrange(today.year, today.month)[1]
    per_day = spent / today.day
    projected = round(per_day * days_in_month, 2)
    hit_on = None
    if cap and per_day > 0:
        if spent >= cap:
            hit_on = today
        else:
            days_left = (cap - spent) / per_day
            day = today + timedelta(days=int(days_left) + 1)
            hit_on = day if day.month == today.month else None
    return Forecast(month_to_date=round(spent, 2), projected=projected, cap=cap, cap_hit_on=hit_on)


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
