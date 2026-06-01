"""DropdownAgentV2 — extracts up to 20 candidate values, each with
per-option `raw_context`.

Used by (gmail | case_file) × dropdown. Produces a
`PendingDropdownV2` envelope (the FE's awaiting-input modal renders
the dropdown). When the paralegal picks one, the per-option
`raw_context` flows to derived children — that's the load-bearing
invariant from the plan.
"""

from __future__ import annotations

import logging
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from ...types.fields import TemplateFieldV2
from ...types.pending import PendingDropdownV2
from .base import ExtractorAgentV2, make_initial_messages
from .prompts import build_system_prompt, build_user_prompt

logger = logging.getLogger(__name__)


class _ExtractedOption(BaseModel):
    """One candidate row inside `_SubmitOptions`."""

    model_config = ConfigDict(extra="forbid")

    display: str = Field(
        description=(
            "The candidate value as it should appear in the dropdown. "
            "Shape to the author's example_format when supplied."
        ),
    )
    raw_context: str = Field(
        default="",
        max_length=2000,
        description=(
            "The source slice (≤ 2000 chars) this option was extracted "
            "from. Must be REAL source material — a derived child of "
            "the picked option reads this verbatim, so include enough "
            "surrounding context to support further extraction."
        ),
    )


class _SubmitOptions(BaseModel):
    """Structured output for dropdown + multi_select extraction."""

    model_config = ConfigDict(extra="forbid")

    completeness: Literal["full", "partial", "unknown"] = Field(
        default="unknown",
        description=(
            "Self-assessment of whether the source material contained "
            "the complete list of items relevant to the variable. "
            "'full' = saw and extracted everything; 'partial' = saw "
            "fragmentary evidence (headers, totals, related-schedule "
            "chunks) but not the itemized rows; 'unknown' = can't "
            "judge. Logged for diagnostics; does not affect FE behavior."
        ),
    )
    completeness_reasoning: str = Field(
        default="",
        description=(
            "ONE short sentence justifying the completeness call. "
            "Debug-only — captured in LangSmith and app logs."
        ),
    )
    options: list[_ExtractedOption] = Field(
        default_factory=list,
        max_length=20,
        description=(
            "Up to 20 distinct candidate options. Each option must come "
            "from a DIFFERENT source chunk; do not duplicate. Each "
            "carries its own raw_context."
        ),
    )


class DropdownAgentV2(ExtractorAgentV2[_SubmitOptions]):
    """Dropdown-shape extraction. (gmail|case_file) × dropdown."""

    output_type: ClassVar[type[BaseModel]] = _SubmitOptions
    submit_tool_name: ClassVar[str] = "_SubmitOptions"
    cost_kind: ClassVar[str] = "dropdown_v2"

    @classmethod
    async def run(
        cls,
        *,
        field: TemplateFieldV2,
        tools: list,
        case_context: dict[str, str] | None = None,
        dependency_values: dict[str, str] | None = None,
        template_property_marker: str | None = None,
    ) -> PendingDropdownV2:
        """Extract dropdown candidates for `field`.

        Returns a `PendingDropdownV2` envelope ready to surface in the
        FE's awaiting-input modal. The envelope carries every option's
        display + per-option raw_context so the post-pick handler can
        forward the right raw_context to derived children.

        On failure (no params, loop exhaustion, validation error) the
        envelope has an empty `options` list — the FE shows "No
        candidates extracted; pick another source" / similar.
        """
        params = field.params
        label = _derive_label(field)

        if params is None:
            return PendingDropdownV2(label=label, options=[], raw_contexts=[])

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
            tools=[*tools, _SubmitOptions],
            agent_name="DropdownAgentV2",
            metadata={"template_variable": field.template_variable},
        )

        if result.output is None:
            return PendingDropdownV2(label=label, options=[], raw_contexts=[])

        cls._log_completeness(field.template_variable, result.output)

        displays = [opt.display for opt in result.output.options]
        raw_contexts = [opt.raw_context for opt in result.output.options]
        return PendingDropdownV2(
            label=label,
            options=displays,
            raw_contexts=raw_contexts,
            instruction=(params.output_expectation or None),
        )

    @classmethod
    def _log_completeness(cls, variable_name: str, output: _SubmitOptions) -> None:
        logger.info(
            "DropdownAgentV2[%s] completeness=%s reasoning=%s options=%d",
            variable_name,
            output.completeness,
            output.completeness_reasoning or "<none>",
            len(output.options),
        )


def _derive_label(field: TemplateFieldV2) -> str:
    """Use the wizard-saved `label` if present; otherwise humanize the
    variable name."""
    params = field.params
    if params and params.label and params.label.strip():
        return params.label.strip()
    pretty = field.template_variable.replace("_", " ").strip()
    return f"Pick the {pretty}" if pretty else "Pick a value"
