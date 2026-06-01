"""Third-pass resolver: enhance opt-in case_vector / Gmail values via Anthropic web search.

Runs after `CaseVectorVisionResolver` (so `current_value` is the most
accurate the upstream pipeline can produce) and BEFORE Pass 2 fetch
substitution / `SystemValueResolver`. Web-enhanced values flow through
`{{var}}` substitution in dependent Pass 2 queries the same way vision
corrections do.

No-op (returns the input list unchanged) when:
  - The kill switch (`WEB_SEARCH_ENHANCE_ENABLED`) is off.
  - No case_vector / Gmail field has `source_params.enable_web_search=True`.
  - Every flagged field has an empty `current_value` (skipped, with a
    warning surfaced both in logs and in the resolved value's
    `reasoning` so the author can fix their `text_query` / Gmail queries).
  - Every flagged field is missing a `template_property_marker` (no
    shape to match — should only happen on malformed templates).

Per-field, the agent is allowed to fail freely — `WebSearchEnhanceAgent.run`
returns the original `current_value` on any error, so the resolver always
produces a non-broken merged list.
"""

import logging
from typing import Any

from src.config import settings
from src.core.common.documents.docx_template import DocxTemplateService

from ..llm.web_search_enhance import WebSearchEnhanceAgent
from ..types.resolution import ResolvedTemplateValue
from ..types.sources import CaseVectorSourceParams, FieldSource, GmailSourceParams
from ..types.spec import AgentConfig, TemplateField

logger = logging.getLogger(__name__)


_WEB_SEARCH_ENABLED_SOURCES = frozenset({FieldSource.CASE_VECTOR, FieldSource.GMAIL})
_WEB_SEARCH_ENABLED_PARAM_TYPES = (CaseVectorSourceParams, GmailSourceParams)


_EMPTY_ANCHOR_NOTE = (
    "Web-search enhancement was requested for this variable "
    "(enable_web_search=True) but skipped because the upstream "
    "case_vector / Gmail retrieval returned an empty value. Add or refine "
    "`source_params` (text_query / subject_query / body_query) so the "
    "upstream source pulls a non-empty anchor."
)


class WebSearchEnhanceResolver:
    """Replaces opt-in case_vector and Gmail resolutions with values reshaped by Anthropic web search."""

    @classmethod
    async def apply(
        cls,
        agent_config: AgentConfig,
        case_details: dict[str, Any] | None,
        template_bytes: bytes | None,
        resolved_values: list[ResolvedTemplateValue],
    ) -> list[ResolvedTemplateValue]:
        """Return `resolved_values` with web-enhanced replacements for flagged case_vector fields.

        Always returns a list of the same length (and same property_name
        order) as the input. Non-flagged fields, unflagged sources, and
        skip cases pass through unchanged.
        """
        if not settings.WEB_SEARCH_ENHANCE_ENABLED:
            return resolved_values

        flagged_fields = _collect_flagged_fields(agent_config.template_fields)
        if not flagged_fields:
            return resolved_values

        rv_by_name = {rv.property_name: rv for rv in resolved_values}
        enhanced_by_name: dict[str, ResolvedTemplateValue] = {}

        for field in flagged_fields:
            rv = rv_by_name.get(field.property_name)
            if rv is None:
                continue

            marker = (field.template_property_marker or "").strip()
            if not marker:
                logger.warning(
                    "WebSearchEnhanceResolver: skipping '%s' — flagged for "
                    "enhancement but no template_property_marker is set.",
                    field.property_name,
                )
                continue

            if not (rv.value or "").strip():
                logger.warning(
                    "WebSearchEnhanceResolver: skipping '%s' — flagged for "
                    "enhancement but current_value is empty. Author should "
                    "check source_params.text_query.",
                    field.property_name,
                )
                enhanced_by_name[field.property_name] = rv.model_copy(update={
                    "reasoning": f"{rv.reasoning} ({_EMPTY_ANCHOR_NOTE})".strip(),
                })
                continue

            paragraph = _resolve_paragraph(template_bytes, field)

            # Author-supplied directives, role-scoped:
            #   web_search_instruction → only WebSearchEnhanceAgent reads it
            #   output_instruction     → final-shape rule, also read by heal
            #                            (for non-case_vector sources). For
            #                            case_vector + web search, this agent
            #                            is the final shaper.
            params = field.source_params
            web_search_instruction = (
                (params.web_search_instruction or "").strip() or None
                if isinstance(params, _WEB_SEARCH_ENABLED_PARAM_TYPES)
                else None
            )
            output_instruction = (field.output_instruction or "").strip() or None

            try:
                new_value = await WebSearchEnhanceAgent.run(
                    variable_name=field.property_name,
                    current_value=rv.value,
                    template_property_marker=marker,
                    template_paragraph=paragraph,
                    case_details=case_details,
                    web_search_instruction=web_search_instruction,
                    output_instruction=output_instruction,
                )
            except Exception as e:
                logger.warning(
                    "WebSearchEnhanceResolver: agent raised for '%s' — "
                    "passing through original current_value. Error: %s",
                    field.property_name, e,
                )
                continue

            if not new_value or new_value.strip() == rv.value.strip():
                continue

            enhanced_by_name[field.property_name] = rv.model_copy(update={
                "value": new_value,
                "reasoning": f"{rv.reasoning} (enhanced via web search)",
            })

        if not enhanced_by_name:
            return resolved_values

        return [
            enhanced_by_name.get(rv.property_name, rv)
            for rv in resolved_values
        ]


def _collect_flagged_fields(template_fields: list[TemplateField]) -> list[TemplateField]:
    flagged: list[TemplateField] = []
    for field in template_fields:
        if field.source not in _WEB_SEARCH_ENABLED_SOURCES:
            continue
        params = field.source_params
        if not isinstance(params, _WEB_SEARCH_ENABLED_PARAM_TYPES):
            continue
        if not params.enable_web_search:
            continue
        flagged.append(field)
    return flagged


def _resolve_paragraph(template_bytes: bytes | None, field: TemplateField) -> str | None:
    """Read the docx paragraph that contains this field's placeholder.

    Returns None on any failure — the agent is told to fall back to a
    marker-shape-only enhancement when the surrounding paragraph isn't
    available (e.g. the docx wasn't downloaded, or the placeholder
    string can't be located).
    """
    if not template_bytes:
        return None
    placeholder = (field.template_variable_string or "").strip()
    if not placeholder:
        return None
    try:
        return DocxTemplateService.find_paragraph_containing(template_bytes, placeholder)
    except Exception as e:
        logger.warning(
            "WebSearchEnhanceResolver: failed to read paragraph for '%s' "
            "(placeholder %r): %s",
            field.property_name, placeholder, e,
        )
        return None
