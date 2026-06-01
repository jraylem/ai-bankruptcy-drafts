"""v2 pipeline orchestrator — initial + resume stages.

The orchestrator drives the full extractor + resolver + pause-resume
sequence between when the dry-run/draft route is hit and when
`finalize_run_v2` takes over.

Two public entry points:

    run_initial_stages_v2(spec, case, ...) -> InitialStagesResultV2
        1. Build the per-resolution `StudioV2ToolContext` + toolset
           once (so every extractor in this run shares the same
           tools).
        2. Topologically order fields by their derived-from /
           query_dependencies edges.
        3. Wave-A pass: for each non-DERIVED field whose wave is None
           or "A", dispatch to WizardResolver — get back either a
           ResolvedTemplateValueV2 (deterministic resolver, draft
           agent, derive agent) or a PendingUserInputV2 envelope
           (dropdown / chip / multi_select / author_input).
        4. Early auto-derive pass: resolve every derived_from_variable
           field whose root parent is LLM_DRAFT / SYSTEM (so wave-B
           extractors have those values to substitute later).
        5. Wave-B fields and any USER_INPUT-rooted derives stay
           deferred for `run_resume_stages_v2`.
        6. Returns `InitialStagesResultV2(all_resolved, pending_inputs)`.
           If `pending_inputs` is non-empty, the caller PAUSES.

    run_resume_stages_v2(spec, case, resolved_values, user_picks, ...)
        -> list[ResolvedTemplateValueV2]
        1. expand_picks_v2 → turn picks into resolved rows.
        2. Late auto-derive: resolve derived_from_variable children
           whose parent is now picked.
        3. Wave-B pass: re-dispatch wave-B fields now that
           dependency_values are populated.
        4. Final derivative pass: anything still derivable.
        Returns the complete `all_resolved` list for `finalize_run_v2`.

The orchestrator is STATELESS — the FE owns `resolved_values` +
`pending_inputs` + `user_picks` between pause and resume.
"""

from __future__ import annotations

import logging
from typing import Any

from src.core.components.cases.identity import case_resource_key

from ..orchestration.dispatcher import WizardResolver
from ..tools.case_vector_query import build_case_vector_query_tool
from ..tools.context import StudioV2ToolContext
from ..tools.gmail_search import build_gmail_search_tool, load_firm_gmail_credentials
from ..tools.vision_fallback import build_vision_fallback_tool
from ..types.fields import TemplateFieldV2, TemplateSpecV2
from ..types.orchestration import (
    InitialStagesResultV2,
    ParentBundleContextV2,
)
from ..types.pending import PendingUserInputV2
from ..types.picks import UserSelectionV2
from ..types.resolution import ResolvedTemplateValueV2
from ..types.wizard_sources import SourceKind
from .picks import expand_picks_v2
from .wave import classify_wave_v2, root_parent_stage_v2, stage_of_v2

logger = logging.getLogger(__name__)


async def run_initial_stages_v2(
    *,
    spec: TemplateSpecV2,
    case: Any,
    parent_context: ParentBundleContextV2 | None = None,
    toolset: list[Any] | None = None,
) -> InitialStagesResultV2:
    """Run the pre-pause resolver sequence for a fresh dry-run / draft.

    Args:
        spec: The v2 template spec (TemplateSpecV2; the working
            draft for dry-run, the published snapshot for draft).
        case: The SQLAlchemy Case row (or compatible). Carries
            `case_file_collection`, `petition_pdf_url` etc. used to
            construct the toolset.
        parent_context: Optional companion-template context — present
            only when this run is a child of a bundling parent.
        toolset: Optional pre-built toolset. When None, the
            orchestrator builds one from `case` + the firm's Gmail
            OAuth via `_build_default_toolset`.
    """
    by_name = {f.template_variable: f for f in spec.fields}

    if toolset is None:
        toolset = _build_default_toolset(case)

    case_context = _build_case_context(case)
    all_resolved: list[ResolvedTemplateValueV2] = []
    pending_inputs: dict[str, PendingUserInputV2] = {}

    # ─── Pass 1: wave-A LLM_DRAFT + SYSTEM + USER_INPUT envelopes ────
    # We classify and dispatch every non-DERIVED field. Wave-B fields
    # (LLM_DRAFT with USER_INPUT-rooted query_dependencies) skip this
    # pass — they're collected for Pass 3 in run_resume_stages_v2.
    for field in spec.fields:
        own_stage = stage_of_v2(field)
        if own_stage == "DERIVED":
            continue
        if own_stage == "LLM_DRAFT" and classify_wave_v2(field, by_name) == "B":
            continue

        deps = _collect_dependency_values(field, all_resolved)
        result = await WizardResolver.dispatch(
            field=field,
            toolset=toolset,
            parent_context=parent_context,
            by_name={rv.template_variable: rv for rv in all_resolved},
            case_context=case_context,
            dependency_values=deps,
        )
        _record_dispatch_result(field, result, all_resolved, pending_inputs)

    # ─── Pass 2: early auto-derive (LLM_DRAFT / SYSTEM roots) ────────
    # Resolve derive children whose root parent is already in
    # `all_resolved` (LLM_DRAFT / SYSTEM). Children of USER_INPUT roots
    # defer to run_resume_stages_v2's late pass.
    for field in spec.fields:
        if stage_of_v2(field) != "DERIVED":
            continue
        root = root_parent_stage_v2(field, by_name)
        if root == "USER_INPUT":
            continue
        # Only run if the parent's resolved row is in all_resolved.
        parent_name = field.params.dependent_variable if field.params else None
        if not parent_name:
            continue
        if parent_name not in {rv.template_variable for rv in all_resolved}:
            continue
        result = await WizardResolver.dispatch(
            field=field,
            toolset=toolset,
            parent_context=parent_context,
            by_name={rv.template_variable: rv for rv in all_resolved},
            case_context=case_context,
        )
        _record_dispatch_result(field, result, all_resolved, pending_inputs)

    # If anything paused, return without trying to derive deeper.
    if pending_inputs:
        return InitialStagesResultV2(
            all_resolved=_dedupe_last_wins(all_resolved),
            pending_inputs=pending_inputs,
        )

    return InitialStagesResultV2(
        all_resolved=_dedupe_last_wins(all_resolved),
        pending_inputs=None,
    )


async def run_resume_stages_v2(
    *,
    spec: TemplateSpecV2,
    case: Any,
    resolved_values: list[ResolvedTemplateValueV2],
    user_picks: dict[str, UserSelectionV2],
    pending_inputs: dict[str, PendingUserInputV2] | None = None,
    parent_context: ParentBundleContextV2 | None = None,
    toolset: list[Any] | None = None,
) -> list[ResolvedTemplateValueV2]:
    """Run the post-pause resolver sequence and return the complete
    `all_resolved` list ready for `finalize_run_v2`.

    `pending_inputs` is the BE's previous-call envelope map — the FE
    re-sends it (the server is stateless) so `expand_picks_v2` can
    look up per-option `raw_context` for derived children downstream.
    """
    by_name = {f.template_variable: f for f in spec.fields}

    if toolset is None:
        toolset = _build_default_toolset(case)

    case_context = _build_case_context(case)

    # Step 1: expand picks → resolved rows. case_id is forwarded so
    # SupportingDocsPickV2 picks can validate file_urls + download
    # supporting docs from the case's R2 prefix.
    expanded = await expand_picks_v2(
        template_fields=spec.fields,
        user_picks=user_picks,
        pending_inputs=pending_inputs,
        resource_key=case_resource_key(case) if case is not None else None,
    )
    base = _dedupe_last_wins(resolved_values + expanded)

    # Step 2: late auto-derive — children of USER_INPUT roots.
    for field in spec.fields:
        if stage_of_v2(field) != "DERIVED":
            continue
        root = root_parent_stage_v2(field, by_name)
        if root != "USER_INPUT":
            continue
        parent_name = field.params.dependent_variable if field.params else None
        if not parent_name or parent_name not in {rv.template_variable for rv in base}:
            continue
        # Skip if already in base (idempotent).
        if field.template_variable in {rv.template_variable for rv in base}:
            continue
        result = await WizardResolver.dispatch(
            field=field,
            toolset=toolset,
            parent_context=parent_context,
            by_name={rv.template_variable: rv for rv in base},
            case_context=case_context,
        )
        if isinstance(result, ResolvedTemplateValueV2):
            base.append(result)
            base = _dedupe_last_wins(base)

    # Step 3: wave-B pass — extractors that were deferred because their
    # query_dependencies reached USER_INPUT.
    for field in spec.fields:
        if classify_wave_v2(field, by_name) != "B":
            continue
        if field.template_variable in {rv.template_variable for rv in base}:
            continue  # already resolved (shouldn't happen but safe)
        deps = _collect_dependency_values(field, base)
        result = await WizardResolver.dispatch(
            field=field,
            toolset=toolset,
            parent_context=parent_context,
            by_name={rv.template_variable: rv for rv in base},
            case_context=case_context,
            dependency_values=deps,
        )
        if isinstance(result, ResolvedTemplateValueV2):
            base.append(result)
            base = _dedupe_last_wins(base)
        else:
            logger.warning(
                "run_resume_stages_v2: wave-B field %s returned a pending "
                "envelope on resume — this shouldn't happen; ignoring.",
                field.template_variable,
            )

    # Step 4: final derivative pass — anything still derivable
    # (idempotent; covers chained derives that surfaced after step 2/3).
    changed = True
    while changed:
        changed = False
        for field in spec.fields:
            if stage_of_v2(field) != "DERIVED":
                continue
            if field.template_variable in {rv.template_variable for rv in base}:
                continue
            parent_name = field.params.dependent_variable if field.params else None
            if not parent_name or parent_name not in {rv.template_variable for rv in base}:
                continue
            result = await WizardResolver.dispatch(
                field=field,
                toolset=toolset,
                parent_context=parent_context,
                case_context=case_context,
                by_name={rv.template_variable: rv for rv in base},
            )
            if isinstance(result, ResolvedTemplateValueV2):
                base.append(result)
                base = _dedupe_last_wins(base)
                changed = True

    return base


# ─── helpers ─────────────────────────────────────────────────────────


def _build_case_context(case: Any) -> dict[str, str] | None:
    """Read the active case's identity off the ORM row + format it as
    a flat map for the extractor agents' `<case_context>` prompt block.

    LOAD-BEARING: this is how Gmail / Case File extractors know which
    case the dry-run / draft is scoped to. Without it the Gmail agent
    runs unscoped queries (e.g. `subject:proof of claim`) and pulls
    documents from every case in the firm inbox.
    """
    if case is None:
        return None
    out: dict[str, str] = {}
    for key in ("case_number", "case_name", "chapter", "court_district"):
        val = getattr(case, key, None)
        if val:
            out[key] = str(val)
    return out or None


def _collect_dependency_values(
    field: TemplateFieldV2,
    resolved_so_far: list[ResolvedTemplateValueV2],
) -> dict[str, str] | None:
    """Build the `dependency_values` map an extractor agent reads for
    `query_dependencies`. Returns `None` when the field has no
    dependencies (cleaner than empty dict for downstream `if values:`
    checks).
    """
    if field.params is None or not field.params.query_dependencies:
        return None
    by_name = {rv.template_variable: rv for rv in resolved_so_far}
    return {
        name: by_name[name].value
        for name in field.params.query_dependencies
        if name in by_name and by_name[name].value
    } or None


def _record_dispatch_result(
    field: TemplateFieldV2,
    result: ResolvedTemplateValueV2 | PendingUserInputV2,
    all_resolved: list[ResolvedTemplateValueV2],
    pending_inputs: dict[str, PendingUserInputV2],
) -> None:
    """Append the dispatch's result to the right bucket."""
    if isinstance(result, ResolvedTemplateValueV2):
        all_resolved.append(result)
    else:
        pending_inputs[field.template_variable] = result


def _dedupe_last_wins(
    values: list[ResolvedTemplateValueV2],
) -> list[ResolvedTemplateValueV2]:
    """Collapse duplicate template_variable entries keeping the LAST.

    Mirrors v1's `_dedupe_last_wins` from
    `src/core/agents/orchestration/pipeline.py`.
    """
    by_name: dict[str, ResolvedTemplateValueV2] = {}
    for rv in values:
        by_name[rv.template_variable] = rv
    return list(by_name.values())


def _build_default_toolset(case: Any) -> list[Any]:
    """Build the default toolset for an extractor agent from `case`.

    Loads the firm OAuth credentials once (shared across all gmail
    extractor invocations in this resolution), then constructs each
    tool. Returns only non-`None` tools — failed constructions
    (missing case_file_collection, missing petition_pdf_url) are
    silently filtered.
    """
    ctx = StudioV2ToolContext(
        case=case,
        firm_oauth=load_firm_gmail_credentials(),
    )
    raw_tools: list[Any] = [
        build_gmail_search_tool(ctx),
        build_case_vector_query_tool(ctx),
        build_vision_fallback_tool(ctx),
    ]
    return [t for t in raw_tools if t is not None]


# Re-export for parity with the v1 module shape — orchestrators outside
# this module sometimes need to recompute stage classifications.
_ = SourceKind  # silence unused-import linter for the type re-export
