"""ExplanationEnhanceAgentV2 — multimodal Claude call that polishes
a paralegal's free-text explanation against attached supporting docs.

Used by `orchestration.picks.expand_picks_v2` for
`SupportingDocsPickV2`. The caller is responsible for:
1. Validating each `file_url` is scoped to the case's R2 prefix.
2. Downloading the file bytes from R2.
3. Parsing each blob into a `SupportingDoc` variant via v1's
   `read_supporting_doc` helper (read-only import).

This agent then composes the multimodal HumanMessage (text preamble +
inlined DOCX/TXT/MD docs as text + PDF/image docs as content blocks)
and invokes Claude. Returns the polished paragraph, or the user's
raw text unchanged on any failure.

Reuses v1's `Agent` base class for structured-output + cost-attribution
wiring.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from src.core.studio_v2.agents._v1_base import StudioV2Agent
from src.core.common.constants import CLAUDE_MODEL_ADVANCED
from src.core.common.documents.supporting_doc_reader import (
    AttachedImageDoc,
    AttachedPdfDoc,
    InlineTextDoc,
    SupportingDoc,
)

from .prompt_builder import build_explanation_enhance_prompt

logger = logging.getLogger(__name__)


class _EnhancedExplanationV2(BaseModel):
    """Structured-output target for the enhancement LLM call."""

    text: str = Field(
        description=(
            "The compact, corroborated, legally-worded paragraph that "
            "fills the placeholder."
        ),
    )


class ExplanationEnhanceAgentV2(StudioV2Agent[_EnhancedExplanationV2]):
    """Polish a paralegal's free-text explanation against attached
    supporting docs into one paragraph of formal third-person legal
    prose."""

    output_type: ClassVar[type[BaseModel]] = _EnhancedExplanationV2
    model: ClassVar[str] = CLAUDE_MODEL_ADVANCED
    max_tokens: ClassVar[int] = 4000
    tags: ClassVar[list[str]] = ["core", "agent", "studio_v2", "explanation_enhance"]
    cost_kind: ClassVar[str] = "explanation_enhance_v2"

    @classmethod
    async def run(
        cls,
        *,
        variable_name: str,
        label: str,
        user_text: str,
        supporting_docs: list[SupportingDoc],
        template_property_marker: str | None = None,
        output_expectation: str | None = None,
    ) -> str:
        """Return the enhanced paragraph, or `user_text` unchanged on
        any failure.

        Args:
            variable_name: The template variable being filled. Used for
                LangSmith metadata; not part of prompt content.
            label: The author-set label for this field (surfaces in the
                heal target hint inside the prompt).
            user_text: The paralegal's raw explanation.
            supporting_docs: Pre-parsed SupportingDoc variants from
                v1's `read_supporting_doc` helper. The caller owns
                download + parse.
            template_property_marker: The original sample sentence at
                this placeholder's position in the source .docx — a
                real example with the right tone, grammar, and length
                the LLM should mimic. Strong shape guidance.
            output_expectation: Author's tuning instruction from the
                wizard's Fine-tune step (e.g. "two sentences max,
                lead with the cause"). Overrides marker shape when
                set.
        """
        if not user_text or not user_text.strip():
            return user_text

        inline_docs = [d for d in supporting_docs if isinstance(d, InlineTextDoc)]
        attached_pdfs = [d for d in supporting_docs if isinstance(d, AttachedPdfDoc)]
        attached_images = [
            d for d in supporting_docs if isinstance(d, AttachedImageDoc)
        ]

        prompt_text = build_explanation_enhance_prompt(
            label=label,
            user_text=user_text,
            inline_docs=inline_docs,
            template_property_marker=template_property_marker,
            output_expectation=output_expectation,
        )

        content: list[dict] = [{"type": "text", "text": prompt_text}]
        for pdf in attached_pdfs:
            content.append({
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": pdf.base64_data,
                },
            })
        for img in attached_images:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": img.media_type,
                    "data": img.base64_data,
                },
            })

        message = HumanMessage(content=content)

        try:
            result = await cls._invoke(
                [message],
                run_name=f"ExplanationEnhanceV2:{variable_name}",
                metadata={"variable": variable_name},
            )
        except Exception as err:  # noqa: BLE001
            logger.warning(
                "ExplanationEnhanceAgentV2: LLM failed for '%s' (%s); "
                "returning raw user text",
                variable_name, err,
            )
            return user_text

        if result is None or not result.text or not result.text.strip():
            logger.warning(
                "ExplanationEnhanceAgentV2: empty result for '%s'; "
                "returning raw user text",
                variable_name,
            )
            return user_text

        return result.text.strip()
