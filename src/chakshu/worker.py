"""The worker process: handle webhook events and hand queued runs to GitHub Actions.

Reviews themselves run on Actions runners, so everything here is short: a
webhook handler or a workflow dispatch. On SIGTERM the worker finishes the job
in hand, then hands anything it still holds back to the queue.
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
from chakshu.db.models import Run, WebhookEvent
from chakshu.db.session import get_sessionmaker
from chakshu.services import dispatcher, events, github, members, pr_authors, queue, review_results

log = logging.getLogger("chakshu.worker")

POLL_SECONDS = 2.0
PRUNE_EVERY = 3600.0
# Touched by the maintenance loop. The container healthcheck fails if it goes stale.
ALIVE_FILE = Path(tempfile.gettempdir()) / "chakshu-worker.alive"


class Worker:
    def __init__(self):
        self.id = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.stopping = asyncio.Event()

    async def _pause(self, seconds: float) -> None:
        """Sleep, but wake up straight away when shutdown starts."""
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self.stopping.wait(), seconds)

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

    async def _dispatch_next_run(self) -> bool:
        async with get_sessionmaker()() as session:
            run = await queue.claim(session, Run, self.id)
            if run is None:
                return False
            log.info("Dispatching run %s", run.id)
            await dispatcher.dispatch(session, run.id)
            return True

    async def _loop(self, step) -> None:
        while not self.stopping.is_set():
            try:
                busy = await step()
            except Exception:
                log.exception("%s failed; retrying", step.__name__)
                busy = False
            if not busy:
                await self._pause(POLL_SECONDS)

    # Heartbeats, recovery of jobs from dead workers, expiry of silent runners, member sync, pruning.
    async def maintenance_loop(self) -> None:
        last_prune = 0.0
        last_members = -members.SYNC_EVERY.total_seconds()  # sync on the first pass
        while True:
            ALIVE_FILE.write_text(str(time.time()))
            try:
                async with get_sessionmaker()() as session:
                    await queue.heartbeat(session, self.id)
                    if requeued := await queue.requeue_stale(session):
                        log.warning("Requeued %s job(s) from a worker that stopped", requeued)
                    if expired := await review_results.expire_dispatched(session):
                        log.warning("Gave up on %s run(s) that GitHub Actions never finished", expired)
                    if creds := await github.load_credentials(session):
                        await pr_authors.backfill(session, creds)
                        if time.monotonic() - last_members > members.SYNC_EVERY.total_seconds():
                            last_members = time.monotonic()
                            await members.sync(session, creds)
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
        await asyncio.gather(self._loop(self._handle_next_event), self._loop(self._dispatch_next_run))
        maintenance.cancel()
        async with get_sessionmaker()() as session:
            if released := await queue.release(session, self.id):
                log.warning("Handed %s unfinished job(s) back to the queue", released)
        log.info("Worker stopped")


async def run_forever() -> None:
    worker = Worker()
    log.info("Worker %s started", worker.id)
    await worker.run()


def heartbeat_ok(max_age: float = 60) -> bool:
    try:
        return time.time() - float(ALIVE_FILE.read_text()) < max_age
    except (OSError, ValueError):
        return False
