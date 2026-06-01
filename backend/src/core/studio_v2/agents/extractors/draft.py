"""DraftAgentV2 — verbatim single-value extraction (presentation_shape=raw).

Used by (gmail | case_file) × raw. The agent decides autonomously
whether to call gmail_search, case_vector_query, vision_fallback, or
some combination, then calls `_SubmitValue` to finalize.

`raw_context` on the resolved row carries the source slice the value
was extracted from — so any DERIVED CHILD of this field reads the
full source chunk (email body / pgvector hit / vehicle paragraph)
rather than the cleaned display string.
"""

from __future__ import annotations

import logging
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from ...types.fields import TemplateFieldV2
from ...types.resolution import ResolvedTemplateValueV2
from .base import ExtractorAgentV2, make_initial_messages
from .prompts import build_system_prompt, build_user_prompt

logger = logging.getLogger(__name__)


class _SubmitValue(BaseModel):
    """Structured output for the raw-shape single-value extraction.

    The agent calls this as its FINAL tool when it has the answer.
    """

    model_config = ConfigDict(extra="forbid")

    value: str = Field(
        description=(
            "The final extracted value, verbatim from the source. "
            "Empty string if the source material doesn't contain the answer."
        ),
    )
    raw_context: str = Field(
        default="",
        max_length=2000,
        description=(
            "The source slice (email body chunk, pgvector chunk, "
            "petition paragraph) the value was extracted from — "
            "capped at 2000 chars. Derived children of this field "
            "read this instead of `value`, so include enough surrounding "
            "context to support further extraction (e.g. for a "
            "vehicle_record, include the full vehicle paragraph with "
            "VIN + make + model + mileage + valuation method)."
        ),
    )
    confidence: Literal["high", "medium", "low", "none"] = Field(
        default="medium",
        description=(
            "Self-assessment: 'high' = exact match in source; "
            "'medium' = strong signal; 'low' = best guess; "
            "'none' = source didn't contain the answer (value is empty)."
        ),
    )
    note: str = Field(
        default="",
        description=(
            "One short sentence explaining the call. Surfaced in "
            "warnings when confidence < high; consumed by the dry-run "
            "result modal's debug pane."
        ),
    )


class DraftAgentV2(ExtractorAgentV2[_SubmitValue]):
    """Verbatim value extraction. (gmail|case_file) × raw."""

    output_type: ClassVar[type[BaseModel]] = _SubmitValue
    submit_tool_name: ClassVar[str] = "_SubmitValue"
    cost_kind: ClassVar[str] = "draft_v2"

    @classmethod
    async def run(
        cls,
        *,
        field: TemplateFieldV2,
        tools: list,
        case_context: dict[str, str] | None = None,
        dependency_values: dict[str, str] | None = None,
        template_property_marker: str | None = None,
    ) -> ResolvedTemplateValueV2:
        """Extract a single verbatim value for `field`.

        `tools` is the orchestrator-built toolset (already filtered
        for `None`s from missing OAuth / collection / petition). The
        loop appends `_SubmitValue` to it so the agent can finalize.
        """
        params = field.params
        if params is None:
            return ResolvedTemplateValueV2(
                template_variable=field.template_variable,
                value="",
                confidence="none",
                note="DraftAgentV2: field has no params.",
            )

        messages = make_initial_messages(
            system_prompt=build_system_prompt(submit_tool_name=cls.submit_tool_name),
            user_prompt=build_user_prompt(
                template_variable=field.template_variable,
                params=params,
                submit_tool_name=cls.submit_tool_name,
                case_context=case_context,
                dependency_values=dependency_values,
                template_property_marker=template_property_marker,
            ),
        )
        result = await cls._run_loop(
            messages=messages,
            tools=[*tools, _SubmitValue],
            agent_name="DraftAgentV2",
            metadata={"template_variable": field.template_variable},
        )

        if result.output is None:
            return ResolvedTemplateValueV2(
                template_variable=field.template_variable,
                value="",
                confidence="none",
                note=(
                    f"DraftAgentV2: loop exhausted (tool_calls={result.tool_call_count}, "
                    f"iterations={result.iterations}) without _SubmitValue."
                ),
            )

        return ResolvedTemplateValueV2(
            template_variable=field.template_variable,
            value=(result.output.value or "").strip(),
            raw_context=(result.output.raw_context or "").strip(),
            confidence=result.output.confidence,
            note=result.output.note,
        )
