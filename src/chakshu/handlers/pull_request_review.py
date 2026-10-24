"""pull_request_review: the first review by a person, for review speed."""

from chakshu.handlers.context import Context, Payload
from chakshu.handlers.pull_request import record_speed


async def handle(ctx: Context, payload: Payload) -> None:
    if payload.get("action") == "submitted":
        await record_speed(ctx, payload)
