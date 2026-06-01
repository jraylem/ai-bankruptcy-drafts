"""MultiSelectAgentV2 — extracts up to 20 candidates for a K-of-N pick.

Same `_SubmitOptions` schema as DropdownAgentV2 (per the wire-shape
parity in plan invariant: pick types discriminate by shape, not source).
The only differences are:
- The agent produces a `PendingMultiSelectV2` envelope (carries
  `min_picks` / `max_picks`).
- The system prompt's shape block tells the agent "K-of-N" framing.

Splitting MultiSelectAgentV2 from DropdownAgentV2 keeps the
per-shape extraction guidance in the prompt (vs hand-wired post-hoc)
AND keeps `cost_kind` separately bucketed for the Costs dashboard.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from pydantic import BaseModel

from ...types.fields import TemplateFieldV2
from ...types.pending import PendingMultiSelectV2
from .base import ExtractorAgentV2, make_initial_messages
from .dropdown import _derive_label
from .prompts import build_system_prompt, build_user_prompt

# We reuse the dropdown extractor's `_SubmitOptions` schema verbatim —
# both shapes need {options: [{display, raw_context}], completeness}.
# The semantic difference (single-pick vs K-of-N) lives in the prompt's
# `<multi_select_extraction>` shape block, not the schema.
from .dropdown import _SubmitOptions

logger = logging.getLogger(__name__)


class MultiSelectAgentV2(ExtractorAgentV2[_SubmitOptions]):
    """Multi-pick extraction. (gmail|case_file) × multi_select."""

    output_type: ClassVar[type[BaseModel]] = _SubmitOptions
    submit_tool_name: ClassVar[str] = "_SubmitOptions"
    cost_kind: ClassVar[str] = "multi_select_v2"

    @classmethod
    async def run(
        cls,
        *,
        field: TemplateFieldV2,
        tools: list,
        case_context: dict[str, str] | None = None,
        dependency_values: dict[str, str] | None = None,
        template_property_marker: str | None = None,
    ) -> PendingMultiSelectV2:
        """Extract multi-select candidates for `field`.

        Returns a `PendingMultiSelectV2` envelope. On failure the
        `options` list is empty — the FE shows "No candidates;
        re-extract or pick another source"."""
        params = field.params
        label = _derive_label(field)

        if params is None:
            return PendingMultiSelectV2(
                label=label, options=[], raw_contexts=[],
                min_picks=1, max_picks=5,
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
            tools=[*tools, _SubmitOptions],
            agent_name="MultiSelectAgentV2",
            metadata={"template_variable": field.template_variable},
        )

        if result.output is None:
            return PendingMultiSelectV2(
                label=label, options=[], raw_contexts=[],
                min_picks=params.min_picks, max_picks=params.max_picks,
            )

        logger.info(
            "MultiSelectAgentV2[%s] completeness=%s options=%d",
            field.template_variable,
            result.output.completeness,
            len(result.output.options),
        )

        displays = [opt.display for opt in result.output.options]
        raw_contexts = [opt.raw_context for opt in result.output.options]
        return PendingMultiSelectV2(
            label=label,
            options=displays,
            raw_contexts=raw_contexts,
            min_picks=params.min_picks,
            max_picks=params.max_picks,
            instruction=(params.output_expectation or None),
        )
