"""The worker process: claim queued runs and review them, a few at a time."""

import asyncio
import logging
import tempfile
import time
import uuid
from pathlib import Path

from chakshu.core.config import get_settings
from chakshu.db.session import get_sessionmaker
from chakshu.services import queue, review_runner

log = logging.getLogger("chakshu.worker")

POLL_SECONDS = 2.0
# Touched on every loop. The container healthcheck fails if it goes stale.
HEARTBEAT = Path(tempfile.gettempdir()) / "chakshu-worker.alive"


async def _claim() -> uuid.UUID | None:
    async with get_sessionmaker()() as session:
        return await queue.claim_next(session)


async def _review(run_id: uuid.UUID, slots: asyncio.Semaphore) -> None:
    try:
        await review_runner.process(run_id)
    except Exception:
        log.exception("Run %s crashed the runner", run_id)
    finally:
        slots.release()


async def run_forever() -> None:
    concurrency = max(1, get_settings().worker_concurrency)
    slots = asyncio.Semaphore(concurrency)
    tasks: set[asyncio.Task] = set()

    async with get_sessionmaker()() as session:
        if requeued := await queue.requeue_stale(session):
            log.warning("Requeued %s run(s) left behind by a stopped worker", requeued)
    log.info("Worker started, up to %s review(s) at a time", concurrency)

    while True:
        HEARTBEAT.write_text(str(time.time()))
        await slots.acquire()
        try:
            run_id = await _claim()
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


def heartbeat_ok(max_age: float = 60) -> bool:
    try:
        return time.time() - float(HEARTBEAT.read_text()) < max_age
    except (OSError, ValueError):
        return False
