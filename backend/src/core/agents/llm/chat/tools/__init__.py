"""Chat-agent tool registry — import-time side effect registers each tool.

The agent imports `.registry.get_all_tools()` to discover what to bind.
Adding a new tool: drop a module here, decorate the class with
`@register_tool`, then `from . import <module>` in this file so the
decorator runs.
"""

from . import (  # noqa: F401
    case_emails_search,
    case_vector_search,
    gmail_search,
    list_drafted_motions,
    petition_vision,
)
from .base import BaseChatTool, ToolContext
from .registry import get_all_tools, register_tool

__all__ = [
    "BaseChatTool",
    "ToolContext",
    "get_all_tools",
    "register_tool",
]
