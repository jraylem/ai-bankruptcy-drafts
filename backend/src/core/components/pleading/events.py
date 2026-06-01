"""Per-user SSE event stream — Redis-Streams-backed.

Writes events to `core:pleading:events:{user_id}` as a ring buffer (XADD with
MAXLEN ~ 500). The SSE generator in `sse.py` tails the stream with `XREAD
BLOCK` and forwards every entry to the connected EventSource.

Durable across reconnects (`Last-Event-ID` resume) and worker restarts.
Pub/sub is NOT used — it's fire-and-forget and would lose events during
brief FE disconnects.
"""

from __future__ import annotations

import logging
from typing import Literal

from src.tasks.redis_client import make_async_redis

from . import state
from .schemas import V2TemplateDraftTaskResponse

logger = logging.getLogger(__name__)

STREAM_KEY_PREFIX = "core:pleading:events:"
STREAM_MAXLEN = 500
STREAM_TTL_SECONDS = 86400  # 24h sliding expiry — refreshed on every XADD

EventType = Literal[
    "snapshot",
    "status_changed",
    "awaiting_input",
    "existing_found",
    "completed",
    "failed",
    "cancelled",
    "removed",
]


def stream_key(user_id: str) -> str:
    return f"{STREAM_KEY_PREFIX}{user_id}"


async def emit(user_id: str, task_id: str, event_type: EventType) -> None:
    """Append one event for the user's stream. Reads the latest task record so
    the SSE consumer always sees fresh state."""
    record = await state.get(task_id)
    if record is None:
        logger.warning("emit: task %s not found, skipping %s event", task_id, event_type)
        return

    payload = V2TemplateDraftTaskResponse.from_record(record).model_dump_json()
    key = stream_key(user_id)

    r = make_async_redis()
    try:
        entry_id = await r.xadd(
            key,
            {"event_type": event_type, "data": payload},
            maxlen=STREAM_MAXLEN,
            approximate=True,
        )
        await r.expire(key, STREAM_TTL_SECONDS)
        logger.info(
            "[pleading-v2 emit] user=%s task=%s event=%s entry=%s status=%s",
            user_id, task_id, event_type, entry_id, record.status,
        )
    finally:
        await r.aclose()


async def emit_removed(user_id: str, task_id: str) -> None:
    """Lightweight removal event — used by DELETE /{task_id} when the record is gone."""
    key = stream_key(user_id)
    r = make_async_redis()
    try:
        await r.xadd(
            key,
            {"event_type": "removed", "data": f'{{"task_id":"{task_id}"}}'},
            maxlen=STREAM_MAXLEN,
            approximate=True,
        )
        await r.expire(key, STREAM_TTL_SECONDS)
    finally:
        await r.aclose()
