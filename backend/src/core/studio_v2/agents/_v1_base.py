"""V2 Agent base subclass — attaches the Langfuse LangChain handler to
every `_structured_llm` build.

v1's `src/core/agents/llm/base.Agent` is the structured-output base that
several v2 agents (`DeriveAgent`, `UserInputHealAgentV2`,
`ExplanationEnhanceAgentV2`, `ExtractFromDraftAgentV2`,
`TemplateAgentV2`) inherit from. The base hard-codes the LangChain
`callbacks` list to `[CostTrackingCallback(...)]`. We can't modify v1
(parallel-namespace invariant), so we subclass it here and override
`_structured_llm` to append the Langfuse handler when enabled.

Inheritance pattern:
    class DeriveAgent(StudioV2Agent[_DerivedValue]): ...

When Langfuse env vars are missing, `langfuse_callback()` returns
`None` and the override is a no-op — same behavior as before.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel

from src.core.agents.llm.base import Agent
from src.core.common.cost_tracking import (
    CostTrackingCallback,
    build_cost_context_for_agent,
)

from ..observability import langfuse_callback

TOutput = TypeVar("TOutput", bound=BaseModel)


class StudioV2Agent(Agent[TOutput], Generic[TOutput]):
    """v2 base — same contract as v1's `Agent[T]`, but with Langfuse
    callback attached when env-configured.

    Reuses v1's `_invoke` / `_invoke_multimodal` / class-var config
    (`model`, `temperature`, `max_tokens`, `output_type`, etc.). The
    only override is `_structured_llm` so the merged callback list
    includes Langfuse alongside the existing CostTrackingCallback.
    """

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
        callbacks: list[Any] = [CostTrackingCallback(cost_context=cost_ctx)]
        lf_handler = langfuse_callback()
        if lf_handler is not None:
            callbacks.append(lf_handler)
        config: dict[str, Any] = {
            "run_name": run_name,
            "tags": cls.tags,
            "metadata": metadata or {},
            "callbacks": callbacks,
        }
        return llm.with_structured_output(cls.output_type).with_config(config)
