"""
Group-dropdown extraction agent.

LLM call site that takes a GroupDropdownComposite and the raw fetched
context for that composite, and returns a list of {left, right} pairs the
user will later pick from. Peer of draft/agent.py, template/agent.py, and
case_ingestion/agent.py — uses the same ChatAnthropic +
with_structured_output pattern.

Orchestration (fanning out one call per composite and bundling results
into pause-descriptor envelopes) lives in resolvers/user_input_resolver.py.
"""

import logging

from pydantic import BaseModel, Field

from ...context import FetchedContext
from ...types.sources import GroupDropdownComposite
from ..base import Agent
from .prompt_builder import _EXTRACTION_PROMPT

logger = logging.getLogger(__name__)


class DropdownOption(BaseModel):
    """One {left, right} pair rendered as a single group-dropdown option; display_value is computed server-side for the FE."""

    left: str
    right: str
    display_value: str = Field(default="", description="Server-computed '{left} - {right}' for FE rendering")


class _ExtractedPairs(BaseModel):
    """Structured-output target for the extraction LLM call."""
    options: list[DropdownOption] = Field(default_factory=list)


class GroupDropdownAgent(Agent[_ExtractedPairs]):
    """Extract {left, right} dropdown pairs that populate two sibling template variables on a single pick."""

    output_type = _ExtractedPairs
    max_tokens = 4000
    tags = ["core", "agent", "user_input"]
    cost_kind = "group_dropdown"

    @classmethod
    async def run(
        cls,
        composite_name: str,
        params: GroupDropdownComposite,
        fetched: FetchedContext,
    ) -> list[DropdownOption]:
        """Extract {left, right} pairs from fetched source material; return `[]` on LLM failure."""
        prompt = _EXTRACTION_PROMPT.format(
            left_label=params.left_label,
            left_guidance=f"The value to extract for the '{params.left_variable}' template variable.",
            right_label=params.right_label,
            right_guidance=f"The value to extract for the '{params.right_variable}' template variable.",
            raw_data=repr(fetched.raw_result),
        )
        try:
            result = await cls._invoke(
                prompt,
                run_name="GroupDropdownExtractor",
                metadata={"composite": composite_name},
            )
            return result.options if result else []
        except Exception as e:
            logger.error(f"Group dropdown extraction failed for '{composite_name}': {e}")
            return []
