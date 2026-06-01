"""inherit_from_parent (a.k.a. value_from_parent_bundle) resolver.

Companion templates (role = `part_of_packet`) declare fields with
`source = value_from_parent_bundle`. At resolve time, the bundling
engine has already filled in `parent_context` with:
  - `resolved_values`: the lead template's resolved variables
  - `draft_text`: the lead template's filled docx text
  - `slot_configurations`: per-variable slot configs assigned by the
    companion on the lead's BundleCompanion entry

This resolver dispatches per-variable on the slot config kind:

| Slot kind                       | Resolution                                                         |
|---------------------------------|--------------------------------------------------------------------|
| ParentVariableSlotConfig        | Look up `parent_context.resolved_values[parent_variable]`          |
| LiteralSlotConfig               | Use the literal_value verbatim                                     |
| ExtractFromDraftSlotConfig      | Defer to `ExtractFromDraftAgentV2.run(...)` (slice D)              |

Missing slot config → fall through to `params.parent_bundle_fallback`
(or empty string with a warning if no fallback).

Phase 2A note: ExtractFromDraftAgentV2 lands in slice D (bundling).
For now, `extract_from_draft` slot configs return a low-confidence
placeholder + a `note` so dry-runs still complete; slice D wires the
real agent.
"""

from __future__ import annotations

import logging

from ..types.bundling import (
    ExtractFromDraftSlotConfig,
    LiteralSlotConfig,
    ParentVariableSlotConfig,
    SlotConfig,
)
from ..types.orchestration import ParentBundleContextV2
from ..types.resolution import ResolvedTemplateValueV2
from ..types.wizard_sources import WizardSourceParams

logger = logging.getLogger(__name__)


async def resolve_inherit_from_parent(
    *,
    template_variable: str,
    params: WizardSourceParams,
    parent_context: ParentBundleContextV2 | None,
) -> ResolvedTemplateValueV2:
    """Resolve `(source=value_from_parent_bundle, shape=raw)` against
    the companion's slot configuration on the parent.

    Args:
        template_variable: The companion's variable name.
        params: The companion field's `WizardSourceParams`
            (carries `parent_bundle_fallback`).
        parent_context: Threaded in by the orchestrator. `None` when
            this template is rendered as a standalone (mis-config —
            value_from_parent_bundle outside a bundle).

    Returns:
        A `ResolvedTemplateValueV2` with the inherited value, or an
        empty/low-confidence row when no slot config + no fallback +
        no parent context are available.
    """
    if parent_context is None:
        return _fallback_or_empty(
            template_variable=template_variable,
            params=params,
            note=(
                "value_from_parent_bundle: no parent_context — this template "
                "may have been resolved standalone instead of as a companion."
            ),
        )

    slot_config = parent_context.slot_configurations.get(template_variable)
    if slot_config is None:
        return _fallback_or_empty(
            template_variable=template_variable,
            params=params,
            note=(
                f"value_from_parent_bundle: parent has no slot configuration "
                f"for '{template_variable}'."
            ),
        )

    # ParentVariableSlotConfig — read parent's resolved value directly.
    if isinstance(slot_config, ParentVariableSlotConfig):
        parent_value = parent_context.resolved_values.get(
            slot_config.parent_variable, ""
        )
        if not parent_value:
            return _fallback_or_empty(
                template_variable=template_variable,
                params=params,
                note=(
                    f"value_from_parent_bundle: parent variable "
                    f"'{slot_config.parent_variable}' resolved to empty value."
                ),
            )
        return ResolvedTemplateValueV2(
            template_variable=template_variable,
            value=parent_value,
            confidence="high",
            note=(
                f"value_from_parent_bundle: from parent."
                f"{slot_config.parent_variable}"
            ),
        )

    # LiteralSlotConfig — use the literal verbatim.
    if isinstance(slot_config, LiteralSlotConfig):
        return ResolvedTemplateValueV2(
            template_variable=template_variable,
            value=slot_config.literal_value,
            confidence="high",
            note="value_from_parent_bundle: literal slot",
        )

    # ExtractFromDraftSlotConfig — run ExtractFromDraftAgentV2 over
    # the parent's filled draft text using the author's instruction.
    if isinstance(slot_config, ExtractFromDraftSlotConfig):
        # Import locally to keep the resolver module light + avoid
        # pulling the LLM agent into every slice-A test that imports
        # this module.
        from ..agents.extract_from_draft import ExtractFromDraftAgentV2

        draft_text = (parent_context.draft_text or "").strip()
        if not draft_text:
            return _fallback_or_empty(
                template_variable=template_variable,
                params=params,
                note=(
                    "value_from_parent_bundle: extract_from_draft slot "
                    "needs parent draft text, but parent_context.draft_text "
                    "is empty."
                ),
            )

        extracted = await ExtractFromDraftAgentV2.run(
            slot_name=template_variable,
            draft_text=draft_text,
            extract_instruction=slot_config.extract_instruction,
        )
        if not extracted:
            return _fallback_or_empty(
                template_variable=template_variable,
                params=params,
                note=(
                    "value_from_parent_bundle: extract_from_draft "
                    "agent returned empty — slot extraction failed."
                ),
            )
        return ResolvedTemplateValueV2(
            template_variable=template_variable,
            value=extracted,
            confidence="high",
            note=(
                f"value_from_parent_bundle: extract_from_draft "
                f"({slot_config.extract_instruction[:60]}...)"
                if len(slot_config.extract_instruction) > 60
                else (
                    f"value_from_parent_bundle: extract_from_draft "
                    f"({slot_config.extract_instruction})"
                )
            ),
        )

    # Unknown slot kind — defensive; should be unreachable given the
    # discriminated union.
    logger.warning(
        "inherit_from_parent_v2: unknown slot config type %s for %s",
        type(slot_config).__name__, template_variable,
    )
    return _fallback_or_empty(
        template_variable=template_variable,
        params=params,
        note=f"value_from_parent_bundle: unknown slot kind {type(slot_config).__name__}",
    )


def _fallback_or_empty(
    *,
    template_variable: str,
    params: WizardSourceParams,
    note: str,
) -> ResolvedTemplateValueV2:
    """Return the field's `parent_bundle_fallback` if set; otherwise
    an empty value with a warning. Used for every failure path so the
    pipeline can continue past unresolvable inherit fields."""
    fallback = (params.parent_bundle_fallback or "").strip()
    if fallback:
        return ResolvedTemplateValueV2(
            template_variable=template_variable,
            value=fallback,
            confidence="low",
            note=f"{note} Using parent_bundle_fallback.",
        )
    return ResolvedTemplateValueV2(
        template_variable=template_variable,
        value="",
        confidence="none",
        note=note,
    )


__all__ = ["resolve_inherit_from_parent"]
