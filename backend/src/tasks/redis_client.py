"""Shared Redis client factory.

Centralizes connection settings so a stalled Redis (e.g. Railway proxy
dropping idle TCP connections) cannot hang the API indefinitely.

- socket_timeout caps any blocking read at SOCKET_TIMEOUT seconds.
  Pass None for long-blocking reads (e.g. XREAD BLOCK in SSE).
- socket_connect_timeout caps the TCP handshake.
- socket_keepalive enables OS-level TCP keepalive on the connection.
- health_check_interval makes redis-py PING any pooled connection idle
  for >N seconds before reuse, transparently re-establishing if the
  proxy killed it.
- retry_on_timeout retries once before raising.
"""
from typing import Optional

import redis
import redis.asyncio as aredis

from ..config import settings

SOCKET_TIMEOUT = 5
SOCKET_CONNECT_TIMEOUT = 5
HEALTH_CHECK_INTERVAL = 30


def make_sync_redis(
    *,
    socket_timeout: Optional[float] = SOCKET_TIMEOUT,
    socket_connect_timeout: float = SOCKET_CONNECT_TIMEOUT,
    decode_responses: bool = True,
) -> redis.Redis:
    return redis.Redis.from_url(
        settings.REDIS_URL,
        decode_responses=decode_responses,
        socket_timeout=socket_timeout,
        socket_connect_timeout=socket_connect_timeout,
        socket_keepalive=True,
        health_check_interval=HEALTH_CHECK_INTERVAL,
        retry_on_timeout=True,
    )


def make_async_redis(
    *,
    socket_timeout: Optional[float] = SOCKET_TIMEOUT,
    socket_connect_timeout: float = SOCKET_CONNECT_TIMEOUT,
    decode_responses: bool = True,
) -> aredis.Redis:
    return aredis.from_url(
        settings.REDIS_URL,
        decode_responses=decode_responses,
        socket_timeout=socket_timeout,
        socket_connect_timeout=socket_connect_timeout,
        socket_keepalive=True,
        health_check_interval=HEALTH_CHECK_INTERVAL,
        retry_on_timeout=True,
    )
