"""Taskiq broker configuration for async task processing."""

import asyncio
import os
import socket

from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

from .config import settings
from .tasks.redis_client import make_async_redis

WORKER_HEARTBEAT_PREFIX = "taskiq_worker:"
_WORKER_HEARTBEAT_TTL = 90  # seconds; refreshed every 30s by the loop

broker = ListQueueBroker(
    url=settings.REDIS_URL,
).with_result_backend(
    RedisAsyncResultBackend(redis_url=settings.REDIS_URL)
)

# Import tasks so workers can discover them
import src.tasks.pleading_tasks_taskiq  # noqa: F401, E402
import src.tasks.review_tasks_taskiq  # noqa: F401, E402
import src.tasks.cleanup_tasks_taskiq  # noqa: F401, E402


async def _heartbeat_loop(key: str) -> None:
    r = make_async_redis()
    try:
        while True:
            await r.setex(key, _WORKER_HEARTBEAT_TTL, "alive")
            await asyncio.sleep(30)
    finally:
        await r.aclose()


@broker.on_event("startup")
async def _register_worker_heartbeat() -> None:
    if not broker.is_worker_process:
        return
    key = f"{WORKER_HEARTBEAT_PREFIX}{socket.gethostname()}:{os.getpid()}"
    asyncio.create_task(_heartbeat_loop(key))


@broker.on_event("shutdown")
async def _deregister_worker_heartbeat() -> None:
    if not broker.is_worker_process:
        return
    key = f"{WORKER_HEARTBEAT_PREFIX}{socket.gethostname()}:{os.getpid()}"
    r = make_async_redis()
    await r.delete(key)
    await r.aclose()


async def startup():
    """Initialize broker on startup (called from FastAPI lifespan)."""
    if not broker.is_worker_process:
        await broker.startup()


async def shutdown():
    """Cleanup broker on shutdown (called from FastAPI lifespan)."""
    if not broker.is_worker_process:
        await broker.shutdown()
