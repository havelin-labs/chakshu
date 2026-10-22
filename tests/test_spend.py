from datetime import UTC, datetime
from decimal import Decimal

from chakshu.db.models import Run
from chakshu.services import settings_store as store
from chakshu.services import spend
from chakshu.services.settings_store import Key


def test_month_start():
    assert spend.month_start(datetime(2026, 10, 22, 15, 30, tzinfo=UTC)) == datetime(2026, 10, 1, tzinfo=UTC)


async def test_no_cap_means_never_over(db):
    budget = await spend.current(db)
    assert budget.cap is None and not budget.over_cap


async def test_cap_counts_this_months_runs(db, seed_runs):
    ids = await seed_runs(2)
    for run_id, cost in zip(ids, ("1.25", "0.75"), strict=True):
        (await db.get(Run, run_id)).cost_usd = Decimal(cost)
    await store.put(db, Key.MONTHLY_CAP_USD, "2")
    await db.commit()

    budget = await spend.current(db)
    assert budget.month_to_date == Decimal("2.0000")
    assert budget.over_cap
