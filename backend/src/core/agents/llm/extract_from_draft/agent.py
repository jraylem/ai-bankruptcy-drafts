"""ExtractFromDraftAgent.

Single-purpose LLM call: pull ONE value from a parent's filled draft text
per an author-supplied extract_instruction. Used by Phase 2's
InheritFromParentResolver when a slot's SlotConfig is `extract_from_draft`.

Error policy: returns "" on None/exception. The resolver treats empty as
"extraction failed" — the slot stays unresolved and surfaces as a warning.
"""

import logging

from pydantic import BaseModel, Field

from ..base import Agent
from .prompt_builder import build_prompt

logger = logging.getLogger(__name__)


class _ExtractedValue(BaseModel):
    """Structured-output target for the extract-from-draft LLM call."""
    value: str = Field(
        default="",
        description="The extracted fragment from the parent draft text. Empty when extraction fails.",
    )


class ExtractFromDraftAgent(Agent[_ExtractedValue]):
    """Extract a single fragment from a parent's produced draft text per author instruction."""

    output_type = _ExtractedValue
    max_tokens = 500
    tags = ["core", "agent", "extract_from_draft"]
    cost_kind = "extract_from_draft"

    @classmethod
    async def run(
        cls,
        slot_name: str,
        draft_text: str,
        extract_instruction: str,
        template_property_marker: str | None = None,
    ) -> str:
        """Return the extracted fragment, or "" on any failure.

        `slot_name` is forwarded to telemetry only — it identifies which
        slot the extraction is for (debugging) but isn't part of the
        prompt itself.
        """
        if not draft_text or not extract_instruction:
            return ""

        prompt = build_prompt(
            draft_text=draft_text,
            extract_instruction=extract_instruction,
            template_property_marker=template_property_marker,
        )
        try:
            result = await cls._invoke(
                prompt,
                run_name="ExtractFromDraft",
                metadata={"slot_name": slot_name},
            )
        except Exception as e:
            logger.warning(
                f"ExtractFromDraftAgent failed for slot '{slot_name}': {e}; "
                "returning empty extracted value"
            )
            return ""

        if result is None or not result.value:
            return ""
        return result.value.strip()
