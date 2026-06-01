"""SSE endpoint generator for the v2 composer-async stream.

Tails the per-user Redis Stream (`core:composer:events:{user_id}`) with
a 15s blocking XREAD. On connect, emits a synthetic `snapshot` event
with the user's currently-tracked tasks so a cold reload always
rehydrates the strip.

Mirrors `src/core/components/pleading/sse.py` 1:1 with composer-side
state + event-stream references.

Auth: prefers the `access_token` HttpOnly cookie (EventSource sends
cookies on same-origin GETs), falls back to a `?token=<jwt>` query
param for legacy Bearer FE during the cookie-migration transition.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from fastapi import HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from jose import JWTError, jwt

from src.auth.auth import ALGORITHM, SECRET_KEY, get_user_by_id
from src.auth.models import User
from src.tasks.redis_client import make_async_redis

from . import state
from .events import stream_key
from .schemas import V2ComposerTaskResponse

logger = logging.getLogger(__name__)

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Pragma": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

XREAD_BLOCK_MS = 15000
XREAD_COUNT = 50


async def decode_sse_token(token: str) -> User:
    """Decode a JWT and return the user, or 401. Enforces multi-tenancy
    via the firm_id claim — same rule as `get_current_user`."""
    credentials_exception = HTTPException(status_code=401, detail="Invalid SSE token")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        firm_id: str = payload.get("firm_id")
        if user_id is None or firm_id is None:
            raise credentials_exception
    except JWTError as exc:
        logger.warning("composer SSE JWT decode failed: %s", exc)
        raise credentials_exception
    user = await get_user_by_id(user_id)
    if user is None:
        raise credentials_exception
    return user


async def stream_events(
    request: Request,
    token: Optional[str] = Query(
        default=None,
        description="JWT fallback for legacy Bearer FE (post-cookie FE omits this and relies on the access_token cookie).",
    ),
):
    """Server-Sent Events handler for /api/v3/studio/composer-async/events."""
    cookie_token = request.cookies.get("access_token")
    raw_token = cookie_token or token
    if not raw_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = await decode_sse_token(raw_token)
    user_id = user.id
    key = stream_key(user_id)

    last_event_id = (
        request.headers.get("Last-Event-ID")
        or request.query_params.get("last_event_id")
    )

    redis_client = make_async_redis(socket_timeout=None)

    logger.info(
        "[composer-v2 sse] connect user=%s key=%s last_event_id=%s",
        user_id, key, last_event_id,
    )

    async def event_generator():
        try:
            if last_event_id:
                start_id = last_event_id
            else:
                latest = await redis_client.xrevrange(key, count=1)
                start_id = latest[0][0] if latest else "0-0"

            # Snapshot — use list_for_user so terminal pills survive
            # reconnect (same rationale as pleading SSE).
            all_for_user = await state.list_for_user(user_id)
            tasks_payload = [
                V2ComposerTaskResponse.from_record(r).model_dump(mode="json")
                for r in all_for_user
            ]
            logger.info(
                "[composer-v2 sse] snapshot user=%s start_id=%s task_count=%d",
                user_id, start_id, len(tasks_payload),
            )
            yield (
                "event: snapshot\n"
                f"data: {json.dumps({'tasks': tasks_payload})}\n\n"
            )

            current_id = start_id
            while True:
                if await request.is_disconnected():
                    logger.info("[composer-v2 sse] disconnect user=%s", user_id)
                    break
                try:
                    result = await redis_client.xread(
                        {key: current_id},
                        block=XREAD_BLOCK_MS,
                        count=XREAD_COUNT,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # noqa: BLE001
                    logger.exception(
                        "composer SSE XREAD failed on %s for user %s: %s",
                        key, user_id, e,
                    )
                    yield f": xread_error {type(e).__name__}\n\n"
                    break

                if not result:
                    yield ": keepalive\n\n"
                    continue

                for _, entries in result:
                    for entry_id, fields in entries:
                        current_id = entry_id
                        event_type = fields.get("event_type", "status_changed")
                        data = fields.get("data", "{}")
                        logger.info(
                            "[composer-v2 sse] yield user=%s entry=%s event=%s",
                            user_id, entry_id, event_type,
                        )
                        yield f"id: {entry_id}\nevent: {event_type}\ndata: {data}\n\n"
        except asyncio.CancelledError:
            logger.debug("composer SSE generator cancelled for user %s", user_id)
            raise
        except Exception as e:  # noqa: BLE001
            logger.exception("composer SSE generator failed for user %s: %s", user_id, e)
            raise
        finally:
            try:
                await redis_client.aclose()
            except Exception:
                pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
