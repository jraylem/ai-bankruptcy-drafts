"""Module-level registry of chat-agent tools.

`@register_tool` is the only mutation entry point. `get_all_tools()` is
what the agent calls when binding tools to the LLM. Order in the registry
is import order — only matters for tie-breaking when the model is
ambiguous about which to call first, which it normally isn't.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from .base import BaseChatTool


_REGISTRY: list[type["BaseChatTool"]] = []

T = TypeVar("T", bound="type[BaseChatTool]")


def register_tool(cls: T) -> T:
    """Decorator: add a `BaseChatTool` subclass to the global registry.

    Idempotent across reloads (test reruns) because we check before append.
    """
    if cls not in _REGISTRY:
        _REGISTRY.append(cls)
    return cls


def get_all_tools() -> list[type["BaseChatTool"]]:
    """Return every registered tool class, in declaration order."""
    return list(_REGISTRY)


def get_tool_by_name(name: str) -> "type[BaseChatTool] | None":
    """Look up a registered tool by its `name` ClassVar."""
    for cls in _REGISTRY:
        if cls.name == name:
            return cls
    return None
