"""v2 case chat agent — agentic streaming Claude assistant for a (user, case) session.

`CaseChatAgent` (in `.agent`) is the entry point used by the chat router's
SSE endpoint. The tool layer (in `.tools`) is the extensibility seam:
declare a new `BaseChatTool`, decorate with `@register_tool`, and it joins
the bound tool set on the next call.
"""

from .agent import CaseChatAgent
from .tools.base import BaseChatTool, ToolContext
from .tools.registry import get_all_tools, register_tool

__all__ = [
    "BaseChatTool",
    "CaseChatAgent",
    "ToolContext",
    "get_all_tools",
    "register_tool",
]
