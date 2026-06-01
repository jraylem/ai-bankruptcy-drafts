"""RecoChipsAgentV2 — produces 1-3 suggestion chips with per-chip
`raw_context`.

Used by (gmail | case_file) × chip. The paralegal picks one chip or
edits its text. Unlike dropdown / multi_select (which extract
exhaustively up to 20 candidates), the chip agent is GENERATIVE —
it produces a small number of plausible final values rather than a
list to pick from.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from ...types.fields import TemplateFieldV2
from ...types.pending import PendingChipV2
from .base import ExtractorAgentV2, make_initial_messages
from .dropdown import _derive_label
from .prompts import build_system_prompt, build_user_prompt

logger = logging.getLogger(__name__)


class _SuggestionChip(BaseModel):
    """One chip in the `_SubmitChips` payload."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(
        description="The suggestion text the paralegal will see / edit.",
    )
    raw_context: str = Field(
        default="",
        max_length=2000,
        description=(
            "The source slice (≤ 2000 chars) supporting this suggestion. "
            "Forwarded to derived children of the picked chip."
        ),
    )


class _SubmitChips(BaseModel):
    """Structured output for chip-shape extraction."""

    model_config = ConfigDict(extra="forbid")

    chips: list[_SuggestionChip] = Field(
        default_factory=list,
        max_length=3,
        description=(
            "1-3 suggestion chips. Favor brevity + confidence over "
            "completeness — the paralegal picks ONE and may edit it. "
            "If you can only confidently produce one chip, return one."
        ),
    )
    note: str = Field(
        default="",
        description="One short sentence justifying the suggestions; debug-only.",
    )


class RecoChipsAgentV2(ExtractorAgentV2[_SubmitChips]):
    """Chip-shape extraction. (gmail|case_file) × chip."""

    output_type: ClassVar[type[BaseModel]] = _SubmitChips
    submit_tool_name: ClassVar[str] = "_SubmitChips"
    cost_kind: ClassVar[str] = "reco_chips_v2"

    @classmethod
    async def run(
        cls,
        *,
        field: TemplateFieldV2,
        tools: list,
        case_context: dict[str, str] | None = None,
        dependency_values: dict[str, str] | None = None,
        template_property_marker: str | None = None,
    ) -> PendingChipV2:
        """Extract 1-3 chips for `field`. On failure returns an empty
        chips list — the FE shows "No suggestions; type it yourself"."""
        params = field.params
        label = _derive_label(field)

        if params is None:
            return PendingChipV2(label=label, chips=[], raw_contexts=[])

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
            tools=[*tools, _SubmitChips],
            agent_name="RecoChipsAgentV2",
            metadata={"template_variable": field.template_variable},
        )

        if result.output is None:
            return PendingChipV2(label=label, chips=[], raw_contexts=[])

        logger.info(
            "RecoChipsAgentV2[%s] chips=%d note=%s",
            field.template_variable,
            len(result.output.chips),
            result.output.note or "<none>",
        )

        chip_texts = [c.text for c in result.output.chips]
        raw_contexts = [c.raw_context for c in result.output.chips]
        return PendingChipV2(
            label=label,
            chips=chip_texts,
            raw_contexts=raw_contexts,
            instruction=(params.output_expectation or None),
        )
