"""Typed streaming events emitted by `CaseChatAgent.stream`.

Each event maps 1:1 to an SSE frame the FE consumes. Keep field names
stable — they are part of the wire contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Union


@dataclass
class ThinkingDelta:
    """Streaming chunk of extended-thinking text."""
    event: Literal["thinking_delta"] = "thinking_delta"
    delta: str = ""


@dataclass
class ContentDelta:
    """Streaming chunk of the final visible assistant text."""
    event: Literal["content_delta"] = "content_delta"
    delta: str = ""


@dataclass
class ToolUseStart:
    """The model has decided to call a tool — name announced before args stream."""
    tool_call_id: str
    tool_name: str
    event: Literal["tool_use_start"] = "tool_use_start"


@dataclass
class ToolUseInputDelta:
    """A streamed chunk of the JSON args for a pending tool call."""
    tool_call_id: str
    delta: str
    event: Literal["tool_use_input_delta"] = "tool_use_input_delta"


@dataclass
class ToolResult:
    """The dispatched tool finished — emit its JSON result to the FE."""
    tool_call_id: str
    tool_name: str
    result: Any
    event: Literal["tool_result"] = "tool_result"


@dataclass
class MessageComplete:
    """Final marker for the assistant turn — message has been persisted."""
    message_id: str
    sequence_number: int
    event: Literal["message_complete"] = "message_complete"


@dataclass
class StreamError:
    """Terminal error; FE should surface and stop reading."""
    message: str
    event: Literal["error"] = "error"


ChatStreamEvent = Union[
    ThinkingDelta,
    ContentDelta,
    ToolUseStart,
    ToolUseInputDelta,
    ToolResult,
    MessageComplete,
    StreamError,
]
