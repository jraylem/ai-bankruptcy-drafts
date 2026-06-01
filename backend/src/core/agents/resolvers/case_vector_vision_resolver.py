"""Second-pass resolver: re-extract low-confidence case_vector values from the petition PDF.

Runs after `DraftAgent` (Pass 1) + `DateHealingResolver` and BEFORE
`SystemValueResolver` / Pass 2 fetch substitution, so vision-corrected
values feed `{{var}}` substitution in dependent Pass 2 queries.

No-op when:
  - The kill switch (`CASE_VECTOR_VISION_FALLBACK_ENABLED`) is off.
  - The case has no `petition_pdf_url`.
  - All `case_vector` fields resolved at high confidence.
  - The PDF download fails (logged warning, original values pass through).
  - The vision agent returns an empty list.
"""

import base64
import logging
from typing import Any

from src.config import settings

from ..llm.case_vector_vision import CaseVectorVisionAgent
from ..utils import fetch_petition_pdf_bytes
from ..types.resolution import ResolvedTemplateValue
from ..types.sources import FieldSource
from ..types.spec import AgentConfig

logger = logging.getLogger(__name__)


class CaseVectorVisionResolver:
    """Replaces low-confidence case_vector resolutions with values re-extracted from the petition PDF via claude-opus-4-6."""

    @classmethod
    async def apply(
        cls,
        agent_config: AgentConfig,
        case_details: dict[str, Any] | None,
        petition_pdf_url: str | None,
        resolved_values: list[ResolvedTemplateValue],
    ) -> list[ResolvedTemplateValue]:
        """Return `resolved_values` with low-confidence case_vector entries replaced.

        On any short-circuit condition (kill switch off, no PDF, no
        eligible fields, agent failure) returns the input list unchanged.
        High-confidence entries are NEVER touched.
        """
        if not settings.CASE_VECTOR_VISION_FALLBACK_ENABLED:
            return resolved_values
        if not petition_pdf_url:
            return resolved_values

        threshold = settings.CASE_VECTOR_VISION_FALLBACK_THRESHOLD
        eligible_confidences = {"low"} if threshold == "low" else {"low", "medium"}

        case_vector_field_names = {
            f.property_name for f in agent_config.template_fields
            if f.source == FieldSource.CASE_VECTOR
        }
        if not case_vector_field_names:
            return resolved_values

        low_conf_by_name: dict[str, ResolvedTemplateValue] = {}
        for rv in resolved_values:
            if (
                rv.property_name in case_vector_field_names
                and rv.confidence in eligible_confidences
            ):
                low_conf_by_name[rv.property_name] = rv
        if not low_conf_by_name:
            return resolved_values

        pdf_bytes = await fetch_petition_pdf_bytes(petition_pdf_url)
        if not pdf_bytes:
            logger.warning(
                "CaseVectorVisionResolver: petition_pdf_url present but fetch "
                "returned no bytes; falling through to low-confidence values."
            )
            return resolved_values
        pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")

        target_fields = [
            f for f in agent_config.template_fields
            if f.property_name in low_conf_by_name
        ]
        vision_results = await CaseVectorVisionAgent.run(
            petition_pdf_b64=pdf_b64,
            fields=target_fields,
            case_details=case_details,
        )
        if not vision_results:
            return resolved_values

        vision_by_name = {rv.property_name: rv for rv in vision_results}

        merged: list[ResolvedTemplateValue] = []
        for rv in resolved_values:
            corrected = vision_by_name.get(rv.property_name)
            if corrected is None or rv.property_name not in low_conf_by_name:
                merged.append(rv)
                continue
            merged.append(corrected.model_copy(update={
                "reasoning": (
                    f"{corrected.reasoning} "
                    "(corrected via vision over petition PDF)"
                ),
            }))
        return merged
