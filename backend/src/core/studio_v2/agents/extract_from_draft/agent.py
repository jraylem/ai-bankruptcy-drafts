"""ExtractFromDraftAgentV2 — single-purpose LLM call to pull ONE
fragment from a parent's filled draft text per an author-supplied
`extract_instruction`.

Used by `inherit_from_parent_v2.resolve` for `extract_from_draft`
slot configs. Reuses v1's `Agent` base class for structured-output +
cost-attribution wiring (read-only import).

Error policy: returns `""` on None / exception. The caller treats an
empty return as "extraction failed" and falls through to the field's
`parent_bundle_fallback` (or empty + warning).
"""

from __future__ import annotations

import logging
from typing import ClassVar

from pydantic import BaseModel, Field

from src.core.studio_v2.agents._v1_base import StudioV2Agent
from src.core.common.constants import CLAUDE_MODEL_ADVANCED

from .prompt_builder import build_extract_from_draft_prompt

logger = logging.getLogger(__name__)


class _ExtractedValueV2(BaseModel):
    """Structured-output target for the LLM call."""

    value: str = Field(
        default="",
        description=(
            "The extracted fragment from the parent draft text. "
            "Empty when extraction fails."
        ),
    )


class ExtractFromDraftAgentV2(StudioV2Agent[_ExtractedValueV2]):
    """Pull one fragment from a parent's filled draft per author instruction."""

    output_type: ClassVar[type[BaseModel]] = _ExtractedValueV2
    model: ClassVar[str] = CLAUDE_MODEL_ADVANCED
    max_tokens: ClassVar[int] = 500
    tags: ClassVar[list[str]] = ["core", "agent", "studio_v2", "extract_from_draft"]
    cost_kind: ClassVar[str] = "extract_from_draft_v2"

    @classmethod
    async def run(
        cls,
        *,
        slot_name: str,
        draft_text: str,
        extract_instruction: str,
        template_property_marker: str | None = None,
    ) -> str:
        """Return the extracted fragment, or `""` on any failure.

        `slot_name` is forwarded to LangSmith metadata only — it
        identifies which slot the extraction is for (debugging) and
        isn't part of the prompt content.
        """
        if not draft_text or not extract_instruction:
            return ""

        prompt = build_extract_from_draft_prompt(
            draft_text=draft_text,
            extract_instruction=extract_instruction,
            template_property_marker=template_property_marker,
        )
        try:
            result = await cls._invoke(
                prompt,
                run_name=f"ExtractFromDraftV2:{slot_name}",
                metadata={"slot_name": slot_name},
            )
        except Exception as err:  # noqa: BLE001
            logger.warning(
                "ExtractFromDraftAgentV2: LLM call failed for slot '%s' (%s); "
                "returning empty extracted value",
                slot_name, err,
            )
            return ""

        if result is None or not result.value:
            return ""
        return result.value.strip()
