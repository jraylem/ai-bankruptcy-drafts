"""Redis Stream-backed event emission for SSE push notifications.

Every task state mutation emits an entry onto the user's stream key
(`user_events:{user_id}`). The SSE endpoint (`src/routes/events.py`) tails
this stream and forwards entries to the browser, which uses the native
`Last-Event-ID` header to resume after disconnects.
"""
import json
import logging
from typing import Literal, Optional

import redis
import redis.asyncio as aredis

from .redis_client import make_async_redis, make_sync_redis

logger = logging.getLogger(__name__)

TaskType = Literal["pleading", "review"]
EventType = Literal[
    "status_changed",
    "progress",
    "input_required",
    "existing_found",
    "completed",
    "failed",
    "cancelled",
    "removed",
]

STREAM_PREFIX = "user_events:"
STREAM_MAXLEN = 500
STREAM_TTL = 7200


def _stream_key(user_id: str) -> str:
    return f"{STREAM_PREFIX}{user_id}"


_sync_client: Optional[redis.Redis] = None
_async_client: Optional[aredis.Redis] = None


def _get_sync_client() -> redis.Redis:
    global _sync_client
    if _sync_client is None:
        _sync_client = make_sync_redis()
    return _sync_client


def get_async_client() -> aredis.Redis:
    """Async Redis client for the SSE endpoint (supports XREAD BLOCK)."""
    global _async_client
    if _async_client is None:
        # SSE uses XREAD BLOCK which deliberately holds the socket open
        # for long stretches; don't let socket_timeout abort it.
        _async_client = make_async_redis(socket_timeout=None)
    return _async_client


def emit_task_event(task: dict, task_type: TaskType, event_type: EventType) -> None:
    """Append a task-state event to the user's Redis Stream.

    `task` must be the full task record (includes user_id and task_id).
    Failure is logged and swallowed — a broadcast failure must not break
    the originating state mutation.
    """
    user_id = task.get("user_id")
    task_id = task.get("task_id")
    if not user_id or not task_id:
        logger.warning(
            "emit_task_event skipped: missing user_id or task_id (task_type=%s, event_type=%s)",
            task_type, event_type,
        )
        return

    key = _stream_key(user_id)
    try:
        client = _get_sync_client()
        client.xadd(
            key,
            {
                "task_id": task_id,
                "task_type": task_type,
                "event_type": event_type,
                "data": json.dumps(task),
            },
            maxlen=STREAM_MAXLEN,
            approximate=True,
        )
        client.expire(key, STREAM_TTL)
    except Exception as e:
        logger.exception(
            "Failed to emit task event (user_id=%s, task_id=%s, event_type=%s): %s",
            user_id, task_id, event_type, e,
        )
