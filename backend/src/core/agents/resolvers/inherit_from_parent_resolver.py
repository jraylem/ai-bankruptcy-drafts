"""Resolver for child template fields whose source is INHERIT_FROM_PARENT.

Two operating modes, gated on whether `parent_context` is supplied:

  - **Phase 1B / standalone child dry-run** (parent_context is None):
    each slot resolves to its `fallback_value` (or a `[parent.slot.<name>]`
    placeholder marker). No LLM, no IO. Lets authors iterate on a child
    template without standing up a parent.

  - **Phase 2 / bundling run** (parent_context is supplied): each slot's
    fill strategy is taken from `parent_context.slot_configurations[name]`.
      * `parent_variable`   → look up by name in `resolved_values`.
      * `literal`           → return the companion's hardcoded string.
      * `extract_from_draft`→ run ExtractFromDraftAgent against
        `parent_context.draft_text` per the slot's extract_instruction.

Slots whose name is not present in `slot_configurations` fall back to
the standalone path so partially-configured parents still surface useful
values for the configured slots and clear placeholders for the others.
"""

import asyncio

from ..llm.extract_from_draft import ExtractFromDraftAgent
from ..types.bundling import (
    ExtractFromDraftSlotConfig,
    LiteralSlotConfig,
    ParentBundleContext,
    ParentVariableSlotConfig,
)
from ..types.resolution import ResolvedTemplateValue, ResolverStage
from ..types.sources import FieldSource, InheritFromParentSourceParams
from ..types.spec import TemplateField


class InheritFromParentResolver:
    """Resolve INHERIT_FROM_PARENT-stage fields from parent context (Phase 2) or fallback (Phase 1B)."""

    stage = ResolverStage.INHERIT_FROM_PARENT

    @classmethod
    async def apply(
        cls,
        template_fields: list[TemplateField],
        parent_context: ParentBundleContext | None = None,
    ) -> list[ResolvedTemplateValue]:
        """Compute resolved values for every inherit_from_parent entry in the spec.

        When `parent_context` is None the resolver is in Phase-1B mode and
        produces only fallbacks (no LLM, no IO). When supplied, slot
        configurations dispatch to one of three strategies — extraction
        slots run their LLM calls in parallel via asyncio.gather.
        """
        inherit_fields: list[TemplateField] = [
            f for f in template_fields
            if f.source == FieldSource.INHERIT_FROM_PARENT
        ]
        if not inherit_fields:
            return []

        slot_fields = [
            f for f in inherit_fields
            if isinstance(f.source_params, InheritFromParentSourceParams)
        ]
        invalid_results = [
            ResolvedTemplateValue.low_confidence(
                f.property_name,
                "source_params did not match InheritFromParentSourceParams.",
            )
            for f in inherit_fields
            if not isinstance(f.source_params, InheritFromParentSourceParams)
        ]

        if parent_context is None:
            return invalid_results + [_resolve_fallback(f) for f in slot_fields]

        return invalid_results + await _resolve_with_parent_context(slot_fields, parent_context)


def _resolve_fallback(field: TemplateField) -> ResolvedTemplateValue:
    """Return the slot's fallback_value or an empty unresolved value.

    Two sub-cases:
      - `fallback_value` is set on the source_params → fill the docx
        with that string. The author opted into the placeholder text,
        so we honor it even though heal-pass is intentionally skipped
        for fallback values (see UserInputHealAgent guard).
      - `fallback_value` is unset (or empty) → emit a value-less
        ResolvedTemplateValue. `finalize_run` drops empty values from
        `resolved_dict`, so the original `[[<slot>]]` marker stays
        verbatim in the rendered docx — visually obvious to the
        author that the slot is unfilled. The unresolved-placeholder
        warning surfaces it in the validation output.
    """
    params = field.source_params
    fallback_value = (
        params.fallback_value
        if isinstance(params, InheritFromParentSourceParams)
        else None
    )
    if fallback_value:
        return ResolvedTemplateValue.high_confidence(
            field.property_name,
            fallback_value,
            "No parent context threaded; using author-supplied fallback.",
        )
    return ResolvedTemplateValue.low_confidence(
        field.property_name,
        "No parent context threaded and no fallback_value configured; leaving placeholder unfilled.",
    )


async def _resolve_with_parent_context(
    slot_fields: list[TemplateField],
    parent_context: ParentBundleContext,
) -> list[ResolvedTemplateValue]:
    """Dispatch each slot to its configured fill strategy and gather extraction calls in parallel."""
    extraction_jobs: list[tuple[int, TemplateField, ExtractFromDraftSlotConfig]] = []
    deterministic: list[tuple[int, ResolvedTemplateValue]] = []

    for idx, field in enumerate(slot_fields):
        slot_config = parent_context.slot_configurations.get(field.property_name)
        if slot_config is None:
            deterministic.append((idx, _resolve_fallback(field)))
            continue

        if isinstance(slot_config, ParentVariableSlotConfig):
            value = parent_context.resolved_values.get(slot_config.parent_variable, "")
            deterministic.append((idx, ResolvedTemplateValue.high_confidence(
                field.property_name,
                value,
                f"Inherited from parent variable '{slot_config.parent_variable}'.",
            )))
            continue

        if isinstance(slot_config, LiteralSlotConfig):
            deterministic.append((idx, ResolvedTemplateValue.high_confidence(
                field.property_name,
                slot_config.literal_value,
                "Filled by literal slot config.",
            )))
            continue

        if isinstance(slot_config, ExtractFromDraftSlotConfig):
            extraction_jobs.append((idx, field, slot_config))
            continue

        deterministic.append((idx, _resolve_fallback(field)))

    extracted_values: list[str] = []
    if extraction_jobs:
        extracted_values = await asyncio.gather(*(
            ExtractFromDraftAgent.run(
                slot_name=field.property_name,
                draft_text=parent_context.draft_text,
                extract_instruction=cfg.extract_instruction,
                template_property_marker=field.template_property_marker,
            )
            for _, field, cfg in extraction_jobs
        ))

    out: list[ResolvedTemplateValue | None] = [None] * len(slot_fields)
    for idx, value in deterministic:
        out[idx] = value
    for (idx, field, _), extracted in zip(extraction_jobs, extracted_values):
        if extracted:
            out[idx] = ResolvedTemplateValue.high_confidence(
                field.property_name,
                extracted,
                "Extracted from parent draft text.",
            )
        else:
            out[idx] = ResolvedTemplateValue.low_confidence(
                field.property_name,
                "ExtractFromDraftAgent returned empty; check extract_instruction or parent draft text.",
            )

    return [r for r in out if r is not None]
