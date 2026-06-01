"""SSE wire framing for the chat stream endpoint.

Translates `ChatStreamEvent` dataclasses to the `event:`/`data:` lines an
`EventSource` consumer expects. Auth via `?token=<jwt>` (matching the
pleading SSE pattern at `src/core/components/pleading/sse.py`) since
EventSource cannot send Authorization headers — chat-stream additionally
exposes a POST entry point that does take Authorization headers, so the
token-query path is only used by FE wiring when needed.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
from typing import AsyncIterator

from fastapi.responses import StreamingResponse

from src.core.agents.llm.chat.events import ChatStreamEvent, StreamError

logger = logging.getLogger(__name__)


SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Pragma": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
    "Content-Type": "text/event-stream",
}


def _event_to_frame(event: ChatStreamEvent) -> str:
    """Render one typed event as an SSE frame."""
    payload = dataclasses.asdict(event)
    name = payload.pop("event", "message")
    return f"event: {name}\ndata: {json.dumps(payload, default=str)}\n\n"


async def render_sse_response(
    events: AsyncIterator[ChatStreamEvent],
) -> StreamingResponse:
    """Wrap an async event iterator as a `StreamingResponse`.

    A swallow-and-emit error guard means a mid-stream exception in the
    underlying agent surfaces as one final `event: error` frame rather
    than killing the HTTP response abruptly.
    """

    async def gen() -> AsyncIterator[str]:
        try:
            async for event in events:
                yield _event_to_frame(event)
        except asyncio.CancelledError:
            logger.debug("Chat SSE cancelled")
            raise
        except Exception as e:
            logger.exception("Chat SSE generator error: %s", e)
            yield _event_to_frame(StreamError(message=f"Stream failed: {e}"))

    return StreamingResponse(gen(), media_type="text/event-stream", headers=SSE_HEADERS)
