"""The worker process: handle webhook events and run reviews from the database queues."""

import asyncio
import logging
import tempfile
import time
import uuid
from pathlib import Path

from chakshu import handlers
from chakshu.core.config import get_settings
from chakshu.db.models import Run, WebhookEvent
from chakshu.db.session import get_sessionmaker
from chakshu.services import events, queue, review_runner

log = logging.getLogger("chakshu.worker")

POLL_SECONDS = 2.0
PRUNE_EVERY = 3600.0
# Touched on every loop. The container healthcheck fails if it goes stale.
HEARTBEAT = Path(tempfile.gettempdir()) / "chakshu-worker.alive"


async def _handle_next_event() -> bool:
    """Handle one queued webhook event. False when there was nothing to do."""
    async with get_sessionmaker()() as session:
        event = await queue.claim(session, WebhookEvent)
        if event is None:
            return False
        try:
            await handlers.handle(session, event)
            await session.commit()
            error = None
        except Exception as exc:  # noqa: BLE001 - recorded on the event, retried by the queue
            log.exception("Webhook %s (%s) failed", event.event, event.id)
            await session.rollback()
            error = exc
        event = await session.get(WebhookEvent, event.id, populate_existing=True)
        await queue.finish(session, event, error)
        return True


async def event_loop() -> None:
    last_prune = 0.0
    while True:
        HEARTBEAT.write_text(str(time.time()))
        try:
            busy = await _handle_next_event()
            if time.monotonic() - last_prune > PRUNE_EVERY:
                async with get_sessionmaker()() as session:
                    await events.prune(session)
                last_prune = time.monotonic()
        except Exception:
            log.exception("Event loop error; retrying")
            busy = False
        if not busy:
            await asyncio.sleep(POLL_SECONDS)


async def _review(run_id: uuid.UUID, slots: asyncio.Semaphore) -> None:
    try:
        await review_runner.process(run_id)
    except Exception:
        log.exception("Run %s crashed the runner", run_id)
    finally:
        slots.release()


async def _claim_run() -> uuid.UUID | None:
    async with get_sessionmaker()() as session:
        run = await queue.claim(session, Run)
        return run.id if run else None


async def run_loop(concurrency: int) -> None:
    slots = asyncio.Semaphore(concurrency)
    tasks: set[asyncio.Task] = set()
    while True:
        await slots.acquire()
        try:
            run_id = await _claim_run()
        except Exception:
            log.exception("Couldn't claim a run; retrying")
            run_id = None
        if run_id is None:
            slots.release()
            await asyncio.sleep(POLL_SECONDS)
            continue
        log.info("Claimed run %s", run_id)
        task = asyncio.create_task(_review(run_id, slots))
        tasks.add(task)
        task.add_done_callback(tasks.discard)


async def run_forever() -> None:
    concurrency = max(1, get_settings().worker_concurrency)
    async with get_sessionmaker()() as session:
        if requeued := await queue.requeue_stale(session):
            log.warning("Requeued %s job(s) left behind by a stopped worker", requeued)
    log.info("Worker started, up to %s review(s) at a time", concurrency)
    await asyncio.gather(event_loop(), run_loop(concurrency))


def heartbeat_ok(max_age: float = 60) -> bool:
    try:
        return time.time() - float(HEARTBEAT.read_text()) < max_age
    except (OSError, ValueError):
        return False
