"""Abstract base class for chat-agent tools.

Tools are stateless classmethods that take a (case-aware) `ToolContext`
plus typed input and return a JSON-serializable result. The agent binds
them to the LangChain LLM via `to_langchain_tool()`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar

from pydantic import BaseModel

from src.core.common.storage.database import Case


@dataclass
class ToolContext:
    """Per-invocation context every tool receives.

    Carrying the loaded `Case` row means tools don't need to re-query the
    database for collection names / petition URL — the chat service loads
    the case once per turn and threads it through.
    """
    user_id: str
    case: Case


class BaseChatTool(ABC):
    """Base class for tools the chat agent can call."""

    name: ClassVar[str]
    description: ClassVar[str]
    input_schema: ClassVar[type[BaseModel]]

    @classmethod
    @abstractmethod
    async def invoke(cls, ctx: ToolContext, **kwargs: Any) -> dict:
        """Run the tool. Return value MUST be JSON-serializable."""
        ...

    @classmethod
    def to_langchain_tool(cls) -> dict:
        """Render the tool in the dict shape `ChatAnthropic.bind_tools()` expects."""
        schema = cls.input_schema.model_json_schema()
        # Strip the auto-generated $defs / title noise that confuses Claude.
        schema.pop("title", None)
        return {
            "name": cls.name,
            "description": cls.description,
            "input_schema": schema,
        }
