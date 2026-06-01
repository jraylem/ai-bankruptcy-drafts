"""Case-vector vision-fallback agent.

Re-extracts low-confidence `case_vector` field values directly from the
case's petition PDF using claude-opus-4-6's Document content block. Reads
checkboxes, tabular data, and form-layout-sensitive content that pgvector
chunks miss.

Triggered by `CaseVectorVisionResolver` after the first DraftAgent pass —
batched so ONE multimodal call covers every low-confidence case_vector
field for the case.
"""

import logging
from typing import Any

from pydantic import BaseModel, Field

from src.core.common.constants import CLAUDE_MODEL_VISION

from ...types.resolution import ResolvedTemplateValue
from ...types.spec import TemplateField
from ..base import Agent
from .prompt_builder import build_vision_extraction_prompt

logger = logging.getLogger(__name__)


class _VisionExtraction(BaseModel):
    """Structured-output target for the vision agent."""
    resolved_values: list[ResolvedTemplateValue] = Field(default_factory=list)


class CaseVectorVisionAgent(Agent[_VisionExtraction]):
    """Re-extract low-confidence case_vector field values from the petition PDF."""

    output_type = _VisionExtraction
    model = CLAUDE_MODEL_VISION
    max_tokens = 8000
    tags = ["core", "agent", "case_vector_vision"]
    cost_kind = "case_vector_vision"

    @classmethod
    async def run(
        cls,
        petition_pdf_b64: str,
        fields: list[TemplateField],
        case_details: dict[str, Any] | None = None,
    ) -> list[ResolvedTemplateValue]:
        """Run the vision pass over the attached petition PDF.

        Returns the parsed `resolved_values` list, or `[]` on any failure
        (logged) so the caller can fall through to the original
        low-confidence values without breaking the pipeline."""
        if not fields:
            return []
        prompt_text = build_vision_extraction_prompt(fields, case_details)
        content_blocks: list[dict] = [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": petition_pdf_b64,
                },
            },
            {"type": "text", "text": prompt_text},
        ]
        try:
            result = await cls._invoke_multimodal(
                content_blocks,
                run_name="CaseVectorVisionAgent",
                metadata={"field_count": str(len(fields))},
            )
            return list(result.resolved_values) if result else []
        except Exception as e:
            logger.error(f"CaseVectorVisionAgent failed: {e}")
            return []
