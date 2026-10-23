import uuid
from datetime import date
from decimal import Decimal

import pytest

from chakshu.api import deps
from chakshu.db.models import JobStatus, Run, User
from chakshu.helpers import alerts as text
from chakshu.services import alerts
from chakshu.services import settings_store as store
from chakshu.services.settings_store import Key


def test_thresholds_are_parsed_sorted_and_bounded():
    assert text.parse_thresholds("80, 50,100,abc,0,250,50") == [50, 80, 100]
    assert text.parse_thresholds(None) == []


def test_only_newly_crossed_thresholds_are_due():
    assert text.due(45, 100, [50, 80, 100], []) == []
    assert text.due(85, 100, [50, 80, 100], []) == [50, 80]
    assert text.due(85, 100, [50, 80, 100], [50]) == [80]
    assert text.due(85, None, [50], []) == []  # no cap, nothing to warn about


def test_week_and_month_keys():
    assert text.week_key(date(2026, 10, 19)) == "2026-W43"
    assert text.month_key(date(2026, 1, 5)) == "2026-01"


def test_spend_message_says_what_happens_at_the_cap():
    msg = text.spend_message(100, 50.0, 50.0, 80.0, None, "https://c/analytics?tab=cost")
    assert "100%" in msg and "paused" in msg and "<https://c/analytics?tab=cost|" in msg
    assert "around 2026-10-28" in text.spend_message(80, 40.0, 50.0, 60.0, "2026-10-28", "x")


def test_digest_lists_repos_and_skills_but_never_people():
    data = {
        "totals": {"reviews": 4, "prs": 3, "spend": 1.25, "posted": 6, "fixed": 2, "dismissed": 1},
        "fixed_by_severity": {"high": 1, "medium": 1},
        "noisiest_skill": {"key": "style", "dismissed_rate": 0.6, "fixed": 2, "dismissed": 3},
        "top_repos": [{"key": "acme/api", "spend": 1.0}],
        "month_spend": 5.0,
        "cap": 20.0,
    }
    msg = text.digest_message("2026-W43", data, "https://c/analytics")
    assert "4 reviews on 3 pull requests" in msg
    assert "$5.00 of $20.00 this month" in msg
    assert "`style` (60% of 5 with a verdict)" in msg
    assert "acme/api $1.00" in msg
    assert "@" not in msg


async def _spend(db, seed_runs, cost: str) -> None:
    (run_id,) = await seed_runs(1)
    run = await db.get(Run, run_id)
    run.cost_usd, run.status = Decimal(cost), JobStatus.SUCCEEDED
    await db.commit()


async def test_each_threshold_is_announced_once_a_month(db, seed_runs, monkeypatch):
    sent = []

    async def fake_post(webhook, message):
        sent.append((webhook, message))

    monkeypatch.setattr(alerts, "post", fake_post)
    await store.put(db, Key.ALERTS_WEBHOOK, "https://hooks.example.com/x")
    await store.put(db, Key.MONTHLY_CAP_USD, "10")
    await store.put(db, Key.ALERTS_DIGEST, "false")
    await db.commit()

    await alerts.run(db)
    assert sent == []  # nothing spent yet

    await _spend(db, seed_runs, "8.5")
    await alerts.run(db)
    await alerts.run(db)
    assert len(sent) == 1 and "80%" in sent[0][1]  # 50 and 80 crossed together: one message, the higher one


async def test_no_webhook_means_no_alerts(db, seed_runs, monkeypatch):
    async def boom(*_):
        raise AssertionError("should not post")

    monkeypatch.setattr(alerts, "post", boom)
    await store.put(db, Key.MONTHLY_CAP_USD, "1")
    await db.commit()
    await _spend(db, seed_runs, "5")
    await alerts.run(db)


@pytest.fixture
def as_admin(client):
    app = client._transport.app
    app.dependency_overrides[deps.optional_user] = lambda: User(
        id=uuid.uuid4(), github_id=1, login="owner", is_admin=True
    )
    yield client
    app.dependency_overrides.clear()


async def test_alert_settings_keep_the_webhook_write_only(as_admin):
    csrf = {"X-CSRF-Token": (await as_admin.get("/api/session")).json()["csrf_token"]}
    body = {
        "webhook": "https://hooks.slack.com/services/T/B/secretpart",
        "thresholds": [100, 80],
        "digest": False,
    }
    saved = (await as_admin.put("/api/settings/alerts", json=body, headers=csrf)).json()
    assert saved["webhook"]["set"] is True and "secretpart" not in saved["webhook"]["hint"]
    assert saved["thresholds"] == [80, 100] and saved["digest"] is False

    bad = await as_admin.put("/api/settings/alerts", json=body | {"webhook": "http://insecure"}, headers=csrf)
    assert bad.status_code == 422
    kept = (await as_admin.put("/api/settings/alerts", json=body | {"webhook": None}, headers=csrf)).json()
    assert kept["webhook"]["set"] is True
