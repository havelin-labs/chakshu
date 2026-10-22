from chakshu.db.models import JobStatus, WebhookEvent
from chakshu.services import events, queue


async def test_redeliveries_are_dropped(db):
    assert await events.store(db, "d-1", "push", {"ref": "refs/heads/main"})
    assert not await events.store(db, "d-1", "push", {"ref": "refs/heads/main"})


async def test_failed_events_retry_then_stop(db):
    await events.store(db, "d-2", "pull_request", {"action": "opened"})
    await db.commit()

    for attempt in range(1, queue.MAX_ATTEMPTS + 1):
        event = await queue.claim(db, WebhookEvent, "w")
        assert event.id == "d-2" and event.attempts == attempt
        await queue.finish(db, event, RuntimeError("boom"))

    assert event.status == JobStatus.FAILED
    assert await queue.claim(db, WebhookEvent, "w") is None
    assert [e.id for e in await events.recent_failures(db)] == ["d-2"]

    assert await events.retry(db, "d-2")
    event = await queue.claim(db, WebhookEvent, "w")
    await queue.finish(db, event)
    assert event.status == JobStatus.SUCCEEDED and event.error is None
