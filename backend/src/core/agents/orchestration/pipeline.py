"""Shared pre-finalize resolver pipeline for draft and dry-run.

Draft (`execute_draft_for_case` / `resume_draft`) and dry-run
(`execute_dry_run` / `resume_dry_run`) differ only in how they obtain
the AgentConfig (persisted vs. in-memory from a template_spec) and in
what response type they wrap around the final result. The resolver
sequence between those two boundaries is identical, and this module owns
it so reordering or inserting a stage is a one-place edit.

Two public entry points:

    run_initial_stages(agent_config, case_id) -> InitialStagesResult
        Runs the full pre-pause resolver sequence: DraftContextService
        fetch, DraftAgent, DateHealingResolver, SystemValueResolver,
        UserInputResolver.apply, and — only when no user-input fields
        are pending — DerivativeResolver. Returns a result carrying
        either `pending_inputs` (caller must pause with
        AwaitingInputResponse) or the complete pre-finalize
        `all_resolved` list (caller calls finalize_run).

    run_resume_stages(agent_config, case_id, resolved_values, user_picks)
        -> list[ResolvedTemplateValue]
        Runs the post-pause resolver sequence: expand_picks then
        DerivativeResolver. Caller passes the return list to finalize_run.

The auto_derive + heal + fill sequence that runs AFTER this pipeline
lives in `finalizer.finalize_run`; the invariant "auto_derive must run
before heal" is owned there.
"""

from dataclasses import dataclass

from src.core.agents.context import DraftContextService
from src.core.agents.llm.draft import DraftAgent
from src.core.agents.resolvers.auto_derived_resolver import AutoDerivedResolver
from src.core.agents.resolvers.case_vector_vision_resolver import (
    CaseVectorVisionResolver,
)
from src.core.agents.resolvers.date_healing_resolver import DateHealingResolver
from src.core.agents.resolvers.derivative_resolver import DerivativeResolver
from src.core.agents.resolvers.inherit_from_parent_resolver import (
    InheritFromParentResolver,
)
from src.core.agents.resolvers.system_value_resolver import SystemValueResolver
from src.core.agents.resolvers.user_input_resolver import (
    PendingUserInput,
    UserInputResolver,
    UserSelection,
)
from src.core.common.storage.database import CaseRepository
from src.core.components.cases.identity import case_resource_key
from src.core.agents.resolvers.web_search_enhance_resolver import (
    WebSearchEnhanceResolver,
)
from src.core.agents.types.bundling import ParentBundleContext
from src.core.agents.types.resolution import ResolvedTemplateValue, ResolverStage
from src.core.agents.types.spec import _STAGE_BY_SOURCE, AgentConfig
from src.core.agents.utils.query_template import classify_wave


def _dedupe_last_wins(values: list[ResolvedTemplateValue]) -> list[ResolvedTemplateValue]:
    """Collapse duplicate property_name entries keeping the LAST one.

    Pass 1 emits a low-confidence empty placeholder for fields whose
    `{{var}}` queries can't substitute yet; Pass 2 re-extracts those
    fields with the substitution resolved and produces the real value.
    The pipeline appends Pass 2 onto Pass 1 (so internal `resolved_by_name`
    dict-builds pick the right one), but the flat list shipped to callers
    must collapse duplicates or the FE sees both placeholder and result.
    Insertion order is preserved — overwriting an existing key keeps
    its original slot, matching Python's dict semantics.
    """
    by_name: dict[str, ResolvedTemplateValue] = {}
    for rv in values:
        by_name[rv.property_name] = rv
    return list(by_name.values())


@dataclass(frozen=True)
class InitialStagesResult:
    """Outcome of `run_initial_stages`.

    When `pending_inputs` is set, the pipeline paused before the
    derivative stage — `all_resolved` contains the pre-input values
    (DraftAgent + DateHealing + SystemValue) and the caller should
    return an AwaitingInputResponse to the FE.

    When `pending_inputs` is None, `all_resolved` contains every pre-
    finalize resolved value (through the DERIVATIVE stage) and the
    caller should pass it directly to finalize_run.
    """
    all_resolved: list[ResolvedTemplateValue]
    pending_inputs: dict[str, PendingUserInput] | None


async def run_initial_stages(
    agent_config: AgentConfig,
    case_id: str,
    template_bytes: bytes | None = None,
    parent_context: ParentBundleContext | None = None,
) -> InitialStagesResult:
    """Run the pre-pause resolver sequence for a fresh draft or dry-run.

    Two-pass topological fetch — sources whose query strings reference
    `{{var}}` (or whose `dependent_variables` list reads other variables)
    can't fetch until those variables resolve, so the fetch is split
    around the LLM_DRAFT + SYSTEM_GENERATED resolvers.

    The sequence is:
      1. DraftContextService.build — assemble per-case context.
      2. DraftContextService.fetch_static — Pass 1: fetch every source
         that doesn't depend on a resolved value.
      3. DraftAgent.run — resolve every LLM_DRAFT-stage field in a
         single multi-field call against Pass 1's context.
      4. DateHealingResolver.apply — heal date values on the draft
         output.
      5. SystemValueResolver.apply — produce deterministic
         system-generated values (current_date, etc.).
      5b. InheritFromParentResolver.apply — produce deterministic values
         for INHERIT_FROM_PARENT-stage fields. Phase 1B returns each
         slot's fallback_value (or a `[parent.slot.<name>]` marker)
         since no parent context is threaded yet; Phase 2 dispatches on
         the parent's per-companion slot_configurations.
      6. Populate `draft_context.resolved_by_name` with all values
         resolved so far (Pass 1 + heal + system + inherit).
      7. DraftContextService.fetch_with_substitution — Pass 2: fetch
         deferred sources, substituting `{{var}}` refs from
         `resolved_by_name` and feeding the chip composer the same map.
      8. DraftAgent.run AGAIN over Pass 2's context if it surfaced any
         LLM_DRAFT-stage fields (rare but cheap — chip composer fields
         are USER_INPUT-stage and skip this).
      9. UserInputResolver.apply — generate pending-input envelopes for
         every USER_INPUT-stage field, consuming Pass 1 + Pass 2 context.
     10. DerivativeResolver.apply — derive values whose parent is already
         resolved. Skipped when step 9 returned any pending inputs;
         the caller is expected to pause and resume later.
    """
    draft_context = await DraftContextService.build(
        agent_config=agent_config,
        case_id=case_id,
        parent_context=parent_context,
    )
    static_context = await DraftContextService.fetch_static(draft_context)
    draft_result = await DraftAgent.run(
        agent_config,
        static_context,
        case_details=draft_context.case_details,
    )

    healed_resolved_values = DateHealingResolver.apply(draft_result.resolved_values)

    # Vision fallback: if any Pass 1 case_vector field came back at low
    # confidence, re-extract those values directly from the petition PDF
    # via claude-opus-4-6. Vision-corrected values flow downstream so
    # Pass 2 substitution (e.g. {{prior_case_number}}) sees the right
    # value even when pgvector chunks missed the form-layout signal.
    healed_resolved_values = await CaseVectorVisionResolver.apply(
        agent_config=agent_config,
        case_details=draft_context.case_details,
        petition_pdf_url=draft_context.petition_pdf_url,
        resolved_values=healed_resolved_values,
    )

    # Web-search enhancement: opt-in per case_vector field. Runs after
    # vision so the anchor (current_value) is the most accurate the
    # upstream pipeline can produce, and BEFORE Pass 2 substitution so
    # any {{var}} reference to an enhanced field sees the new value.
    healed_resolved_values = await WebSearchEnhanceResolver.apply(
        agent_config=agent_config,
        case_details=draft_context.case_details,
        template_bytes=template_bytes,
        resolved_values=healed_resolved_values,
    )

    system_values = SystemValueResolver.apply(agent_config.template_fields)
    inherit_values = await InheritFromParentResolver.apply(
        agent_config.template_fields,
        parent_context=parent_context,
    )
    pre_input = healed_resolved_values + system_values + inherit_values

    # Early auto-derive pass — resolve children whose root parent already
    # resolved in LLM_DRAFT or SYSTEM_GENERATED, so their values are
    # available for `{{var}}` substitution in Pass 2 case_vector / gmail /
    # court_drive text_queries. Children of USER_INPUT parents are skipped
    # here and resolved later by the finalizer's late call (idempotent).
    early_auto_derived = await AutoDerivedResolver.apply(
        agent_config.template_fields,
        pre_input,
        only_root_stages=frozenset({
            ResolverStage.LLM_DRAFT,
            ResolverStage.SYSTEM_GENERATED,
        }),
    )
    pre_input = pre_input + early_auto_derived

    draft_context.resolved_by_name = {rv.property_name: rv for rv in pre_input}
    substituted_context = await DraftContextService.fetch_with_substitution(draft_context)
    full_context = static_context + substituted_context

    # Wave-B classification — LLM_DRAFT fields whose {{var}} refs reach a
    # USER_INPUT-rooted target must wait for the user pick + late auto-derive
    # before their context fetch can produce a real value. They're deferred
    # to Pass 3 in `run_resume_stages`; here we exclude them from the Pass 2
    # DraftAgent re-run so we don't extract from garbage (empty-substituted)
    # fetched context.
    by_name_fields = {f.property_name: f for f in agent_config.template_fields}
    wave_b_property_names = {
        f.property_name for f in agent_config.template_fields
        if classify_wave(f, by_name_fields) == "B"
    }

    # Pass 2 may have surfaced LLM_DRAFT-stage fields whose queries only
    # became valid after Pass 1 resolved their refs. Re-run DraftAgent
    # against JUST those — filter by stage (USER_INPUT-stage Pass 2
    # entries like reco_chips_from_dependent_variables ride through to
    # UserInputResolver unchanged), and scope template_fields to the
    # Pass 2 property_names so the second prompt doesn't re-extract
    # already-resolved Pass 1 fields against the wrong source material.
    # Wave-B fields are excluded — they'll fetch + draft in Pass 3 post-pause.
    pass_2_llm_draft_contexts = [
        c for c in substituted_context
        if _STAGE_BY_SOURCE.get(c.source) == ResolverStage.LLM_DRAFT
        and c.property_name not in wave_b_property_names
    ]
    if pass_2_llm_draft_contexts:
        pass_2_property_names = {c.property_name for c in pass_2_llm_draft_contexts}
        scoped_agent_config = agent_config.model_copy(update={
            "template_fields": [
                f for f in agent_config.template_fields
                if f.property_name in pass_2_property_names
            ],
        })
        draft_result_pass_2 = await DraftAgent.run(
            scoped_agent_config,
            pass_2_llm_draft_contexts,
            case_details=draft_context.case_details,
        )
        pass_2_resolved = DateHealingResolver.apply(draft_result_pass_2.resolved_values)
        pre_input = _dedupe_last_wins(pre_input + pass_2_resolved)
        draft_context.resolved_by_name = {rv.property_name: rv for rv in pre_input}

    pending = await UserInputResolver.apply(
        agent_config.template_fields,
        full_context,
        resolved_by_name=draft_context.resolved_by_name,
        case_file_collection=draft_context.case_file_collection,
        petition_pdf_url=draft_context.petition_pdf_url,
    )
    if pending:
        return InitialStagesResult(all_resolved=_dedupe_last_wins(pre_input), pending_inputs=pending)

    derivative_values = DerivativeResolver.apply(
        agent_config.template_fields,
        pre_input,
    )
    return InitialStagesResult(
        all_resolved=_dedupe_last_wins(pre_input + derivative_values),
        pending_inputs=None,
    )


async def run_resume_stages(
    agent_config: AgentConfig,
    case_id: str,
    resolved_values: list[ResolvedTemplateValue],
    user_picks: dict[str, UserSelection],
    resource_key: str | None = None,
) -> list[ResolvedTemplateValue]:
    """Run the post-pause resolver sequence for a resumed draft or dry-run.

    The sequence is:
      1. UserInputResolver.expand_picks — validate and expand each
         user_pick into ResolvedTemplateValue(s). For
         user_input_with_supporting_docs fields this also downloads
         uploaded files from R2 and runs ExplanationEnhanceAgent.
      2. AutoDerivedResolver.apply (USER_INPUT roots) — derive children
         whose root parent was a USER_INPUT-stage field (e.g. car_model
         from a vehicle_record dropdown pick). Their values must land in
         `resolved_by_name` before Pass 3 runs so `{{car_model}}` refs
         in deferred case_vector queries can substitute.
      3. Pass 3 — fetch + DraftAgent for wave-B LLM_DRAFT fields, the
         ones whose `{{var}}` refs reach USER_INPUT-rooted targets and
         were therefore skipped in Pass 2. Re-runs `fetch_with_substitution`
         with the post-pause `resolved_by_name` so substitutions resolve
         to real values, then DraftAgent extracts from the fresh context.
      4. DerivativeResolver.apply — derive values whose parent is now
         resolved (e.g. dates offset from a user-picked petition date).

    Returns every resolved value (`resolved_values` + expanded user
    picks + late auto-derived + Pass 3 results + derivatives). Caller
    passes the return list to finalize_run.
    """
    # Lazily resolve resource_key from the case row if the caller didn't
    # pass it. Resource_key drives R2 path construction for supporting-doc
    # download — URLs saved before the Phase 1 UUID migration encode the
    # case's old sanitized slug, which now lives on `case.legacy_id`.
    if resource_key is None:
        case_row = await CaseRepository.get(case_id)
        if case_row is not None:
            resource_key = case_resource_key(case_row)

    user_input_values = await UserInputResolver.expand_picks(
        agent_config.template_fields,
        resolved_values,
        user_picks,
        case_id=case_id,
        resource_key=resource_key,
    )
    base = _dedupe_last_wins(resolved_values + user_input_values)

    # Late auto-derive — children of USER_INPUT roots become resolvable
    # now that expand_picks populated their parents. Resolved values land
    # in `base` so Pass 3 substitutions see them.
    late_auto_derived = await AutoDerivedResolver.apply(
        agent_config.template_fields,
        base,
        only_root_stages=frozenset({ResolverStage.USER_INPUT}),
    )
    base = _dedupe_last_wins(base + late_auto_derived)

    # Pass 3 — fetch + draft wave-B fields with the now-complete resolved_by_name.
    by_name_fields = {f.property_name: f for f in agent_config.template_fields}
    wave_b_fields = [
        f for f in agent_config.template_fields
        if classify_wave(f, by_name_fields) == "B"
    ]
    if wave_b_fields:
        draft_context = await DraftContextService.build(
            agent_config=agent_config,
            case_id=case_id,
        )
        draft_context.resolved_by_name = {rv.property_name: rv for rv in base}
        wave_b_config = agent_config.model_copy(update={"template_fields": wave_b_fields})
        scoped_draft_context = draft_context.model_copy(update={"agent_config": wave_b_config})
        pass_3_context = await DraftContextService.fetch_with_substitution(scoped_draft_context)
        if pass_3_context:
            pass_3_result = await DraftAgent.run(
                wave_b_config,
                pass_3_context,
                case_details=draft_context.case_details,
            )
            pass_3_resolved = DateHealingResolver.apply(pass_3_result.resolved_values)
            base = _dedupe_last_wins(base + pass_3_resolved)

    derivative_values = DerivativeResolver.apply(agent_config.template_fields, base)
    return _dedupe_last_wins(base + derivative_values)
