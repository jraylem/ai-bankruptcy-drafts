"""
Explanation-enhance agent.

Runs inside UserInputResolver.expand_picks on resume for every USER_INPUT
field whose source is user_input_with_supporting_docs. Takes the user's
free-text explanation plus a set of pre-uploaded supporting docs (already
parsed into SupportingDoc variants) and produces ONE compact, legally-
worded paragraph that:

  - Preserves every fact the user asserted.
  - Corroborates / sharpens specific claims using the attached docs.
  - Does NOT fabricate facts absent from both user text and the docs.

Multimodal invocation: PDFs and images attach as document/image content
blocks on a single HumanMessage (same pattern CaseIngestionAgent uses);
DOCX/TXT/MD bodies inline as text sections inside the prompt string.

Error policy: on None / exception / empty result, return the user's raw
text unchanged. Enhancement is best-effort polish, never a hard dependency
of the fill pipeline.
"""

import logging

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from src.core.common.constants import CLAUDE_MODEL_ADVANCED
from src.core.common.documents.supporting_doc_reader import (
    AttachedImageDoc,
    AttachedPdfDoc,
    InlineTextDoc,
    SupportingDoc,
)

from ..base import Agent
from .prompt_builder import build_enhance_prompt

logger = logging.getLogger(__name__)


class _EnhancedExplanation(BaseModel):
    """Structured-output target for the enhancement LLM call."""
    text: str = Field(
        description="The compact, corroborated, legally-worded paragraph that fills the placeholder",
    )


class ExplanationEnhanceAgent(Agent[_EnhancedExplanation]):
    """Produce one polished, corroborated paragraph from a user's free-form explanation + uploaded supporting docs (multimodal)."""

    model = CLAUDE_MODEL_ADVANCED
    output_type = _EnhancedExplanation
    max_tokens = 4000
    tags = ["core", "agent", "explanation_enhance"]
    cost_kind = "explanation_enhance"

    @classmethod
    async def run(
        cls,
        variable_name: str,
        label: str,
        user_text: str,
        supporting_docs: list[SupportingDoc],
    ) -> str:
        """Return the enhanced paragraph, or `user_text` unchanged on any failure.

        Callers hand in already-parsed `SupportingDoc` variants
        (InlineTextDoc / AttachedPdfDoc / AttachedImageDoc); this agent does
        not download or parse — that's the caller's responsibility.
        """
        inline_docs = [d for d in supporting_docs if isinstance(d, InlineTextDoc)]
        attached_pdfs = [d for d in supporting_docs if isinstance(d, AttachedPdfDoc)]
        attached_images = [d for d in supporting_docs if isinstance(d, AttachedImageDoc)]

        prompt_text = build_enhance_prompt(label=label, user_text=user_text, inline_docs=inline_docs)

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
                run_name="ExplanationEnhance",
                metadata={"variable": variable_name},
            )
        except Exception as e:
            logger.warning(
                f"ExplanationEnhanceAgent failed for '{variable_name}': {e}; "
                "returning raw user text"
            )
            return user_text

        if result is None or not result.text or not result.text.strip():
            logger.warning(
                f"ExplanationEnhanceAgent returned empty for '{variable_name}'; "
                "returning raw user text"
            )
            return user_text

        return result.text.strip()
