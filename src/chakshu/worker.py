"""The worker process: handle webhook events and run reviews from the database queues.

On SIGTERM it stops claiming, lets running reviews finish for up to GRACE, then
hands anything still unfinished back to the queue for another worker.
"""

import asyncio
import contextlib
import logging
import os
import signal
import socket
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
# Keep below the compose stop_grace_period so hand-back happens before SIGKILL.
GRACE_SECONDS = 9 * 60
# Touched by the maintenance loop. The container healthcheck fails if it goes stale.
ALIVE_FILE = Path(tempfile.gettempdir()) / "chakshu-worker.alive"


class Worker:
    def __init__(self, concurrency: int):
        self.id = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.slots = asyncio.Semaphore(concurrency)
        self.stopping = asyncio.Event()
        self.reviews: set[asyncio.Task] = set()

    async def _pause(self, seconds: float) -> None:
        """Sleep, but wake up straight away when shutdown starts."""
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self.stopping.wait(), seconds)

    # Webhook events: quick, one at a time.
    async def _handle_next_event(self) -> bool:
        async with get_sessionmaker()() as session:
            event = await queue.claim(session, WebhookEvent, self.id)
            if event is None:
                return False
            # Read these now: after a rollback the object is expired and touching it would hit the DB lazily.
            event_id, event_name = event.id, event.event
            try:
                await handlers.handle(session, event)
                await session.commit()
                error = None
            except Exception as exc:  # noqa: BLE001 - recorded on the event, retried by the queue
                log.exception("Webhook %s (%s) failed", event_name, event_id)
                await session.rollback()
                error = exc
            event = await session.get(WebhookEvent, event_id, populate_existing=True)
            await queue.finish(session, event, error)
            return True

    async def event_loop(self) -> None:
        while not self.stopping.is_set():
            try:
                busy = await self._handle_next_event()
            except Exception:
                log.exception("Event loop error; retrying")
                busy = False
            if not busy:
                await self._pause(POLL_SECONDS)

    # Reviews: slow, several at a time.
    async def _review(self, run_id: uuid.UUID) -> None:
        try:
            await review_runner.process(run_id)
        except Exception:
            log.exception("Run %s crashed the runner", run_id)
        finally:
            self.slots.release()

    async def run_loop(self) -> None:
        while not self.stopping.is_set():
            if self.slots.locked():
                await self._pause(POLL_SECONDS)
                continue
            await self.slots.acquire()
            try:
                async with get_sessionmaker()() as session:
                    run = await queue.claim(session, Run, self.id)
            except Exception:
                log.exception("Couldn't claim a run; retrying")
                run = None
            if run is None:
                self.slots.release()
                await self._pause(POLL_SECONDS)
                continue
            log.info("Claimed run %s", run.id)
            task = asyncio.create_task(self._review(run.id))
            self.reviews.add(task)
            task.add_done_callback(self.reviews.discard)

    # Heartbeats, recovery of jobs from dead workers, pruning. Keeps going during shutdown.
    async def maintenance_loop(self) -> None:
        last_prune = 0.0
        while True:
            ALIVE_FILE.write_text(str(time.time()))
            try:
                async with get_sessionmaker()() as session:
                    await queue.heartbeat(session, self.id)
                    if requeued := await queue.requeue_stale(session):
                        log.warning("Requeued %s job(s) from a worker that stopped", requeued)
                    if time.monotonic() - last_prune > PRUNE_EVERY:
                        await events.prune(session)
                        last_prune = time.monotonic()
            except Exception:
                log.exception("Maintenance failed; retrying")
            await asyncio.sleep(queue.HEARTBEAT_EVERY.total_seconds())

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            with contextlib.suppress(NotImplementedError):  # not available on Windows
                loop.add_signal_handler(sig, self.stopping.set)

        maintenance = asyncio.create_task(self.maintenance_loop())
        await asyncio.gather(self.event_loop(), self.run_loop())

        if self.reviews:
            log.info("Stopping: waiting up to %ss for %s review(s)", GRACE_SECONDS, len(self.reviews))
            _, unfinished = await asyncio.wait(self.reviews, timeout=GRACE_SECONDS)
            for task in unfinished:
                task.cancel()
            await asyncio.gather(*unfinished, return_exceptions=True)
        maintenance.cancel()
        async with get_sessionmaker()() as session:
            if released := await queue.release(session, self.id):
                log.warning("Handed %s unfinished job(s) back to the queue", released)
        log.info("Worker stopped")


async def run_forever() -> None:
    concurrency = max(1, get_settings().worker_concurrency)
    worker = Worker(concurrency)
    log.info("Worker %s started, up to %s review(s) at a time", worker.id, concurrency)
    await worker.run()


def heartbeat_ok(max_age: float = 60) -> bool:
    try:
        return time.time() - float(ALIVE_FILE.read_text()) < max_age
    except (OSError, ValueError):
        return False
