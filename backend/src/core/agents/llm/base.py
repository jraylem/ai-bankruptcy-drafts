"""Shared base class for structured-output Claude agents.

Every concrete agent under this package is a one-shot LLM call that
targets a Pydantic output type. The Agent base class encapsulates the
ChatAnthropic client construction and the with_structured_output /
with_config wiring so subclasses only declare their config and their
public entry point.

Subclasses declare config as ClassVars:
    model         — Claude model name (default: CLAUDE_MODEL_ADVANCED)
    output_type   — Pydantic class for structured output (required)
    max_tokens    — default 4000
    temperature   — default 0
    max_retries   — default 3
    tags          — LangChain run tags (default: [])
    cost_kind     — bucket label used in llm_cost_logs.kind ('draft' /
                    'template' / 'auto_derive' / ...). Subclass override
                    required if you want this agent's spend grouped
                    independently in the studio Costs panel; otherwise
                    it logs under 'unknown'.

and call cls._invoke(prompt, run_name, metadata) from their public
classmethod (by convention, `run`). Prompt assembly, error policy, and
multi-call orchestration belong in the subclass.

Cost tracking: when the caller wraps its work in
`with cost_attribution(firm_id=..., case_id=..., user_id=...):`, every
nested LLM call here picks the attribution up via contextvar and a
`CostTrackingCallback` is attached automatically — usage metadata
lands in `llm_cost_logs` without per-call-site plumbing.
"""

from typing import Any, ClassVar, Generic, TypeVar

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from src.core.common.constants import CLAUDE_MODEL_ADVANCED
from src.core.common.cost_tracking import (
    CostTrackingCallback,
    build_cost_context_for_agent,
)

TOutput = TypeVar("TOutput", bound=BaseModel)


class Agent(Generic[TOutput]):
    """Base class for every structured-output Claude agent in core/."""
    model: ClassVar[str] = CLAUDE_MODEL_ADVANCED
    output_type: ClassVar[type[BaseModel]]
    max_tokens: ClassVar[int] = 4000
    temperature: ClassVar[float] = 0
    max_retries: ClassVar[int] = 3
    tags: ClassVar[list[str]] = []
    cost_kind: ClassVar[str] = "unknown"

    @classmethod
    def _structured_llm(cls, run_name: str, metadata: dict | None = None):
        llm = ChatAnthropic(
            model=cls.model,
            temperature=cls.temperature,
            max_tokens=cls.max_tokens,
            max_retries=cls.max_retries,
        )
        cost_ctx = build_cost_context_for_agent(
            kind=cls.cost_kind,
            agent_name=cls.__name__,
        )
        config: dict[str, Any] = {
            "run_name": run_name,
            "tags": cls.tags,
            "metadata": metadata or {},
            "callbacks": [CostTrackingCallback(cost_context=cost_ctx)],
        }
        return llm.with_structured_output(cls.output_type).with_config(config)

    @classmethod
    async def _invoke(
        cls,
        prompt: Any,
        run_name: str,
        metadata: dict | None = None,
    ) -> TOutput | None:
        structured = cls._structured_llm(run_name, metadata)
        return await structured.ainvoke(prompt)

    @classmethod
    async def _invoke_multimodal(
        cls,
        content_blocks: list[dict],
        run_name: str,
        metadata: dict | None = None,
    ) -> TOutput | None:
        """Same structured-output round-trip as `_invoke`, but the prompt is
        a list of LangChain content blocks (text + image_url + document)
        rather than a string. Used by agents that need to feed Claude
        multimodal content — e.g. the case_vector vision-fallback agent
        attaches the petition PDF as a `document` block alongside the
        text instructions.

        `content_blocks` follows the Anthropic content-block schema:
        `[{"type": "document", "source": {...}}, {"type": "text", "text": "..."}]`.
        """
        structured = cls._structured_llm(run_name, metadata)
        return await structured.ainvoke([HumanMessage(content=content_blocks)])
