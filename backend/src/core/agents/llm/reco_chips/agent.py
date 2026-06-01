"""
Recommendation-chips generation agent.

LLM call site that takes a RecoChipsEmailSourceParams or
RecoChipsCaseVectorSourceParams plus raw fetched context for a reco-chips
field, and returns up to 3 short text candidates the user can click as a
starting point for an editable textfield. Peer of group_dropdown/agent.py —
uses the same ChatAnthropic + with_structured_output pattern.

Unlike GroupDropdownAgent (extractive), this agent is GENERATIVE: it writes
new candidate phrases grounded in the source material rather than pulling
structured pairs out of it.

Orchestration (fanning out one call per reco-chips field and bundling
results into pause-descriptor envelopes) lives in
resolvers/user_input_resolver.py.
"""

import logging

from pydantic import BaseModel, Field

from ...context import FetchedContext
from ...types.sources import (
    RecoChipsCaseVectorSourceParams,
    RecoChipsEmailSourceParams,
    RecoChipsFromDependentVariablesSourceParams,
)
from ..base import Agent
from .prompt_builder import (
    _EXAMPLE_SENTENCE_BLOCK,
    _GENERATION_PROMPT,
    _render_instruction_block,
)

# The agent only reads `label` and `example_sentence`, both of which live on
# all reco-chips param shapes — so the arg type is the union.
RecoChipsParams = (
    RecoChipsEmailSourceParams
    | RecoChipsCaseVectorSourceParams
    | RecoChipsFromDependentVariablesSourceParams
)

logger = logging.getLogger(__name__)


class _ExtractedChips(BaseModel):
    """Structured-output target for the reco-chips generation LLM call."""
    chips: list[str] = Field(default_factory=list, max_length=3)


class RecoChipsAgent(Agent[_ExtractedChips]):
    """Generate up to 3 short text candidates grounded in fetched source material for the author to pick from."""

    output_type = _ExtractedChips
    max_tokens = 2000
    tags = ["core", "agent", "user_input"]
    cost_kind = "reco_chips"

    @classmethod
    async def run(
        cls,
        variable_name: str,
        params: RecoChipsParams,
        fetched: FetchedContext,
    ) -> list[str]:
        """Generate up to 3 chip candidates grounded in fetched source material; return `[]` on LLM failure."""
        example_sentence_block = (
            _EXAMPLE_SENTENCE_BLOCK.format(example_sentence=params.example_sentence.strip())
            if params.example_sentence and params.example_sentence.strip()
            else ""
        )
        instruction_block = _render_instruction_block(fetched.instruction)
        prompt = _GENERATION_PROMPT.format(
            variable_name=variable_name,
            label=params.label,
            example_sentence_block=example_sentence_block,
            instruction_block=instruction_block,
            source_material=repr(fetched.raw_result),
        )
        try:
            result = await cls._invoke(
                prompt,
                run_name="RecoChipsGenerator",
                metadata={"variable": variable_name},
            )
            return list(result.chips) if result else []
        except Exception as e:
            logger.error(f"Reco-chips generation failed for '{variable_name}': {e}")
            return []
