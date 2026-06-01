"""Draft agent — runs once per draft/dry-run to resolve every LLM_DRAFT-stage field in a single multi-field Claude call."""

import logging

from pydantic import BaseModel, Field

from ...context import FetchedContext
from ...types.resolution import ResolvedTemplateValue
from ...types.spec import AgentConfig
from ..base import Agent
from .prompt_builder import _build_draft_prompt

logger = logging.getLogger(__name__)


class DraftAgentOutput(BaseModel):
    """Structured output from the draft agent: one resolved value per template field."""
    resolved_values: list[ResolvedTemplateValue] = Field(default_factory=list)


class DraftAgent(Agent[DraftAgentOutput]):
    """Resolve every LLM_DRAFT-stage field in one multi-field call using fetched per-field context."""

    output_type = DraftAgentOutput
    max_tokens = 30000
    tags = ["core", "agent", "draft"]
    cost_kind = "draft"

    @classmethod
    async def run(
        cls,
        agent_config: AgentConfig,
        context: list[FetchedContext],
        case_details: dict[str, str | int | None] | None = None,
    ) -> DraftAgentOutput:
        """Resolve every LLM_DRAFT-stage field in a single Claude call; return empty output on LLM failure."""
        prompt = _build_draft_prompt(
            agent_config,
            context,
            case_details=case_details,
        )
        try:
            result = await cls._invoke(
                prompt,
                run_name="DraftAgent",
                metadata={"template_id": agent_config.template_id},
            )
            return result or DraftAgentOutput(resolved_values=[])
        except Exception as e:
            logger.error(f"Draft agent LLM error: {e}")
            return DraftAgentOutput(resolved_values=[])
