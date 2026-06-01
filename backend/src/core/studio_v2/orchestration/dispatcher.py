"""WizardResolver — the (source × shape) → resolver/agent dispatch table.

Single entry point the v2 pipeline calls per field:

    rv = await WizardResolver.dispatch(
        field=field,
        ctx=tool_context,
        parent_context=parent_context,
        by_name=resolved_so_far,
    )

The dispatch picks the right resolver/agent per the field's
`params.source` and `params.presentation_shape`:

| Source                   | Shape          | Handler                                  | Slice |
|--------------------------|----------------|------------------------------------------|-------|
| current_date             | raw            | resolve_current_date (deterministic)     | A     |
| constants                | raw            | resolve_constant (deterministic)         | A     |
| attorney                 | raw            | resolve_attorney_static (deterministic)  | A     |
| value_from_parent_bundle | raw            | resolve_inherit_from_parent              | A     |
| derived_from_variable    | raw            | DeriveAgent.run (LLM, no tools)          | A     |
| gmail / case_file        | raw            | DraftAgentV2 (LLM + tools)               | B     |
| gmail / case_file        | dropdown       | DropdownAgentV2 (LLM + tools)            | B     |
| gmail / case_file        | chip           | RecoChipsAgentV2 (LLM + tools)           | B     |
| gmail / case_file        | multi_select   | MultiSelectAgentV2 (LLM + tools)         | B     |
                              ↑ tools are filtered by source via `_tools_for_source`:
                                gmail → [gmail_search]
                                case_file → [case_vector_query, vision_fallback]
| attorney                 | dropdown       | PendingAttorneyPickV2 (UserInputResolver)| F     |
| attorney                 | multi_select   | PendingAttorneyPickV2 (UserInputResolver)| F     |
| author_input             | any            | PendingAuthor*V2 (UserInputResolver)     | F     |

Slice A (this commit) populates the deterministic resolvers + DeriveAgent
rows. Slices B and F return a placeholder `ResolvedTemplateValueV2`
with `confidence="none"` and a `note` flagging the unimplemented path,
so the pipeline can still complete a dry-run for templates that only
use slice-A sources (current_date, constants, attorney-raw, inherit,
derived) — useful for early end-to-end testing.
"""

from __future__ import annotations

import logging
from typing import Any, Union

from ..agents.derive import DeriveAgent
from ..agents.extractors import (
    DraftAgentV2,
    DropdownAgentV2,
    MultiSelectAgentV2,
    RecoChipsAgentV2,
)
from ..types.fields import TemplateFieldV2
from ..types.orchestration import ParentBundleContextV2
from ..types.pending import PendingUserInputV2
from ..types.resolution import ResolvedTemplateValueV2
from ..types.wizard_sources import PresentationShape, SourceKind
from ..resolvers.attorney import resolve_attorney_static
from ..resolvers.constants import resolve_constant
from ..resolvers.current_date import resolve_current_date
from ..resolvers.inherit_from_parent import resolve_inherit_from_parent
from ..resolvers.user_input import (
    emit_attorney_pick_envelope,
    emit_author_input_envelope,
)

logger = logging.getLogger(__name__)


# Dispatch return type: `ResolvedTemplateValueV2` for non-pausing paths,
# `PendingUserInputV2` for paths that need a paralegal pick at draft time.
# The orchestrator (slice C) splits the per-field dispatch results into
# `all_resolved` (the ResolvedTemplateValueV2 list) and `pending_inputs`
# (the {var: envelope} map) returned in `InitialStagesResultV2`.
DispatchResult = Union[ResolvedTemplateValueV2, PendingUserInputV2]


class WizardResolver:
    """Stateless dispatch — every method classmethod / staticmethod."""

    @classmethod
    async def dispatch(
        cls,
        *,
        field: TemplateFieldV2,
        ctx: Any | None = None,
        toolset: list[Any] | None = None,
        parent_context: ParentBundleContextV2 | None = None,
        by_name: dict[str, ResolvedTemplateValueV2] | None = None,
        case_context: dict[str, str] | None = None,
        dependency_values: dict[str, str] | None = None,
    ) -> DispatchResult:
        """Resolve a single field by routing on (source, shape).

        Returns either:
        - `ResolvedTemplateValueV2` for fields that resolve without a
          paralegal pause (current_date / constants / attorney-raw /
          value_from_parent_bundle / derived_from_variable / gmail|case_file
          with `raw` shape).
        - `PendingUserInputV2` for fields that pause for a paralegal pick
          (gmail|case_file with `dropdown` / `chip` / `multi_select` shape;
          attorney with `dropdown` / `multi_select` shape; author_input).
          The orchestrator surfaces these as `AwaitingInputResponseV2`.

        Args:
            field: The v2 template field; carries the variable name +
                `params` (source + shape + author config).
            ctx: `StudioV2ToolContext` for tool-using agents. Currently
                only used to skip extractor paths when ctx is None
                (the toolset is built per-resolution by the orchestrator).
            toolset: Pre-built list of bound tools for the extractor
                agents (gmail_search / case_vector_query / vision_fallback).
                Built by the orchestrator from `StudioV2ToolContext`. When
                None, extractor paths return a placeholder with
                `confidence='none'`.
            parent_context: For companion templates only — the parent's
                resolved values + draft text + slot configs.
            by_name: The full resolved-so-far map. DeriveAgent reads it
                to find the parent variable's `ResolvedTemplateValueV2`
                (preferring `raw_context` over `value`).
            dependency_values: Map of resolved values for fields in
                `params.query_dependencies`. Passed to extractor agents
                as a labeled context block in the prompt.
        """
        params = field.params
        if params is None:
            return ResolvedTemplateValueV2(
                template_variable=field.template_variable,
                value="",
                confidence="none",
                note=(
                    "WizardResolver: field has no params — paralegal hasn't "
                    "configured this variable yet."
                ),
            )

        source = params.source
        shape = params.presentation_shape

        # ─── Slice A: deterministic + DeriveAgent ─────────────────────

        if source == SourceKind.CURRENT_DATE:
            return resolve_current_date(
                template_variable=field.template_variable,
                params=params,
            )

        if source == SourceKind.CONSTANTS:
            return await resolve_constant(
                template_variable=field.template_variable,
                params=params,
            )

        if source == SourceKind.ATTORNEY and shape == PresentationShape.RAW:
            return await resolve_attorney_static(
                template_variable=field.template_variable,
                params=params,
            )

        if source == SourceKind.VALUE_FROM_PARENT_BUNDLE:
            return await resolve_inherit_from_parent(
                template_variable=field.template_variable,
                params=params,
                parent_context=parent_context,
            )

        if source == SourceKind.DERIVED_FROM_VARIABLE:
            return await cls._dispatch_derive(
                field=field,
                by_name=by_name or {},
            )

        # ─── Slice B: LLM extractors (gmail / case_file) ──────────────

        if source in (SourceKind.GMAIL, SourceKind.CASE_FILE):
            if toolset is None:
                return ResolvedTemplateValueV2(
                    template_variable=field.template_variable,
                    value="",
                    confidence="none",
                    note=(
                        f"WizardResolver: source={source.value} requires a "
                        f"toolset (orchestrator must build from StudioV2ToolContext)."
                    ),
                )

            # Narrow the toolset to ONLY the data lookups that match
            # this field's source. Without this, an LLM extracting
            # from case_file would still see `gmail_search` bound and
            # could (and did) wander off-source — costing tool calls
            # against Gmail for fields the author scoped to the case
            # file. case_file gets case_vector_query + vision_fallback
            # (petition PDF corroborates case_file extractions);
            # gmail gets gmail_search only.
            scoped_tools = _tools_for_source(source, toolset)

            if shape == PresentationShape.RAW:
                return await DraftAgentV2.run(
                    field=field,
                    tools=scoped_tools,
                    case_context=case_context,
                    dependency_values=dependency_values,
                    template_property_marker=field.template_property_marker,
                )
            if shape == PresentationShape.DROPDOWN:
                return await DropdownAgentV2.run(
                    field=field,
                    tools=scoped_tools,
                    case_context=case_context,
                    dependency_values=dependency_values,
                    template_property_marker=field.template_property_marker,
                )
            if shape == PresentationShape.CHIP:
                return await RecoChipsAgentV2.run(
                    field=field,
                    tools=scoped_tools,
                    case_context=case_context,
                    dependency_values=dependency_values,
                    template_property_marker=field.template_property_marker,
                )
            if shape == PresentationShape.MULTI_SELECT:
                return await MultiSelectAgentV2.run(
                    field=field,
                    tools=scoped_tools,
                    case_context=case_context,
                    dependency_values=dependency_values,
                    template_property_marker=field.template_property_marker,
                )
            # Defensive — every PresentationShape value is handled above.
            logger.warning(
                "WizardResolver: extractor source=%s with unhandled shape=%s",
                source.value, shape.value,
            )
            return ResolvedTemplateValueV2(
                template_variable=field.template_variable,
                value="",
                confidence="none",
                note=f"WizardResolver: unhandled shape={shape.value} for source={source.value}",
            )

        # ─── User-input pending envelopes (attorney pick + author_input) ─

        if (source == SourceKind.ATTORNEY
                and shape in (PresentationShape.DROPDOWN, PresentationShape.MULTI_SELECT)):
            return await emit_attorney_pick_envelope(
                template_variable=field.template_variable,
                params=params,
                multi_select=(shape == PresentationShape.MULTI_SELECT),
            )

        if source == SourceKind.AUTHOR_INPUT:
            return emit_author_input_envelope(
                template_variable=field.template_variable,
                params=params,
            )

        # Defensive: unknown source kind (shouldn't reach here given the
        # discriminated SourceKind enum, but keeps the dispatch total).
        logger.warning(
            "WizardResolver: unhandled (source=%s, shape=%s) for %s",
            source, shape, field.template_variable,
        )
        return ResolvedTemplateValueV2(
            template_variable=field.template_variable,
            value="",
            confidence="none",
            note=f"WizardResolver: no handler for source={source.value} shape={shape.value}",
        )

    @classmethod
    async def _dispatch_derive(
        cls,
        *,
        field: TemplateFieldV2,
        by_name: dict[str, ResolvedTemplateValueV2],
    ) -> ResolvedTemplateValueV2:
        """Resolve a `derived_from_variable` field by looking up the
        parent's resolved row in `by_name` and calling DeriveAgent.

        Returns a row with `confidence="none"` if the parent isn't
        present in `by_name` yet — the orchestrator's wave classification
        is responsible for resolving the parent first; this guard is
        belt-and-braces.
        """
        params = field.params
        assert params is not None  # caller checked

        parent_variable = (params.dependent_variable or "").strip()
        if not parent_variable:
            return ResolvedTemplateValueV2(
                template_variable=field.template_variable,
                value="",
                confidence="none",
                note=(
                    "derived_from_variable: no dependent_variable on params — "
                    "paralegal didn't pick a parent in the wizard's Find step."
                ),
            )

        parent_resolved = by_name.get(parent_variable)
        if parent_resolved is None:
            return ResolvedTemplateValueV2(
                template_variable=field.template_variable,
                value="",
                confidence="none",
                note=(
                    f"derived_from_variable: parent '{parent_variable}' has "
                    f"not been resolved yet — orchestrator wave ordering bug."
                ),
            )

        return await DeriveAgent.run(
            child_variable=field.template_variable,
            parent_variable=parent_variable,
            parent_raw_context=parent_resolved.raw_context,
            parent_value=parent_resolved.value,
            extraction_prompt=params.extraction_prompt or "",
            output_expectation=params.output_expectation,
        )


# Tool-name discriminators. Stay in sync with each tool builder's
# `@tool(name=...)` (or the LangChain default derived from the
# coroutine name).
_GMAIL_SEARCH_TOOL_NAME = "gmail_search"
_CASE_VECTOR_QUERY_TOOL_NAME = "case_vector_query"
_VISION_FALLBACK_TOOL_NAME = "vision_fallback"


def _tools_for_source(source: SourceKind, toolset: list[Any]) -> list[Any]:
    """Return only the tools an extractor for `source` should see.

    Hard restriction by source — the LLM never sees off-source tools,
    so prompt-level "use the right one" guidance can't be ignored.

    - `gmail` → gmail_search only.
    - `case_file` → case_vector_query + vision_fallback (the petition
      PDF lives in the case file and corroborates text extractions
      from low-confidence or scanned chunks).
    - any other source: empty list — extractors aren't called for
      non-extractor sources, but be defensive if a future caller
      misroutes.
    """
    if source == SourceKind.GMAIL:
        allowed = {_GMAIL_SEARCH_TOOL_NAME}
    elif source == SourceKind.CASE_FILE:
        allowed = {_CASE_VECTOR_QUERY_TOOL_NAME, _VISION_FALLBACK_TOOL_NAME}
    else:
        return []
    return [t for t in toolset if getattr(t, "name", None) in allowed]
