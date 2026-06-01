"""SSE endpoint that pushes per-user task state transitions to the browser.

Resilient by design:
- Each event carries the Redis Stream entry ID; the browser echoes it back
  as `Last-Event-ID` on reconnect, and we resume the stream from that ID —
  no missed events on refresh, network blips, or server restarts.
- On connect, we always emit an initial snapshot of the user's active tasks
  so the UI renders correct state instantly even if `Last-Event-ID` is stale
  or absent.
- A 15-second blocking XREAD doubles as both the read loop and the heartbeat.
  If no events arrive, we yield an SSE comment (`:keepalive`) to keep the
  connection alive through intermediary proxies.
"""
import asyncio
import json
import logging

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from ..tasks.event_stream import STREAM_PREFIX, get_async_client
from ..tasks.task_state import task_state
from ..tasks.review_task_state import review_task_state
from ..tasks.orchestrator import get_motion_display_name

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Events"])

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Pragma": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

XREAD_BLOCK_MS = 15000
XREAD_COUNT = 50


@router.get("/events")
async def task_events(
    request: Request,
    user_id: str = Query(..., description="User whose task events to stream"),
):
    """Server-Sent Events stream of the user's pleading + review task updates."""
    last_event_id = request.headers.get("Last-Event-ID") or request.query_params.get(
        "last_event_id"
    )
    stream_key = f"{STREAM_PREFIX}{user_id}"
    redis_client = get_async_client()

    async def event_generator():
        try:
            # Fresh connections (without Last-Event-ID) need a stable stream cursor to avoid
            # missing fast events emitted between snapshot generation and the first XREAD call.
            if last_event_id:
                start_id = last_event_id
            else:
                latest_entry = await redis_client.xrevrange(stream_key, count=1)
                start_id = latest_entry[0][0] if latest_entry else "0-0"

            pleading_tasks, review_tasks = await asyncio.gather(
                asyncio.to_thread(task_state.get_visible_tasks, user_id),
                asyncio.to_thread(review_task_state.get_visible_tasks, user_id),
            )
            for task in pleading_tasks:
                if not task.get("motion_type_display") and task.get("motion_type"):
                    task["motion_type_display"] = get_motion_display_name(task["motion_type"])
            snapshot = {
                "pleading_tasks": pleading_tasks,
                "review_tasks": review_tasks,
            }
            yield f"event: snapshot\ndata: {json.dumps(snapshot)}\n\n"

            current_id = start_id
            while True:
                if await request.is_disconnected():
                    break

                try:
                    result = await redis_client.xread(
                        {stream_key: current_id},
                        block=XREAD_BLOCK_MS,
                        count=XREAD_COUNT,
                    )
                except Exception as e:
                    logger.exception(
                        "XREAD failed on %s for user %s: %s", stream_key, user_id, e
                    )
                    yield f': xread_error {type(e).__name__}\n\n'
                    break

                if not result:
                    yield ": keepalive\n\n"
                    continue

                for _, entries in result:
                    for entry_id, fields in entries:
                        current_id = entry_id
                        event_type = fields.get("event_type", "status_changed")
                        data = fields.get("data", "{}")
                        yield f"id: {entry_id}\nevent: {event_type}\ndata: {data}\n\n"
        except Exception as e:
            logger.exception("SSE generator failed for user %s: %s", user_id, e)
            raise

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
