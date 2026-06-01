"""Template-spec validation.

Cross-field validators for the author-facing template_spec. Called once
when an AgentConfig is being composed (see compose_agent_config /
build_agent_config in service.py) to enforce invariants that can't be
expressed at the per-variable schema level — e.g. source_params must
match the FieldSource, group-dropdown partners must resolve to real
siblings with no conflicting source, dependents must not chain, and
constants must reference existing reference_data rows.

validate_template_spec_source_map is the entry point; the three
_validate_* helpers below are its internal per-concern passes.
"""

from fastapi import HTTPException

from src.core.agents.utils import extract_var_refs_from_source_params
from src.core.agents.types.resolution import ResolverStage
from src.core.agents.types.sources import (
    AutoDerivedRuleEffect,
    AutoDerivedSourceParams,
    CaseVectorSourceParams,
    ConstantsSourceParams,
    CourtDriveSourceParams,
    DependentOnVariableSourceParams,
    DropdownCaseVectorSourceParams,
    DropdownEmailSourceParams,
    DropdownFromConstantsSourceParams,
    FieldSource,
    GmailSourceParams,
    GroupDropdownSourceParams,
    InheritFromParentSourceParams,
    MultiSelectFromCaseVectorSourceParams,
    MultiSelectFromGmailSourceParams,
    RecoChipsCaseVectorSourceParams,
    RecoChipsEmailSourceParams,
    RecoChipsFromDependentVariablesSourceParams,
    SystemGeneratedSourceParams,
    UserInputDateSourceParams,
    UserInputPlainTextSourceParams,
    UserInputWithSupportingDocsSourceParams,
    VectorSourceParams,
)
from src.core.agents.types.spec import (
    _STAGE_BY_SOURCE,
    TemplateVariable,
    root_parent_is_unbound,
    root_parent_stage,
)
from src.core.common.storage.database import ReferenceDataRepository


# Variables in these stages resolve BEFORE the user-input pause, so they
# can be referenced via {{var}} or `dependent_variables` from ANY
# referencer regardless of stage.
_REFERENCEABLE_STAGES: set[ResolverStage] = {
    ResolverStage.LLM_DRAFT,
    ResolverStage.SYSTEM_GENERATED,
}

# LLM_DRAFT-stage referencers may ALSO reach USER_INPUT-rooted targets,
# because the pipeline defers those LLM_DRAFT fetches to Pass 3 in
# `run_resume_stages` (after `expand_picks` + late auto-derive populate
# the user's pick and its auto_derived descendants). See pipeline.py.
_LLM_DRAFT_ALLOWED_TARGET_STAGES: set[ResolverStage] = {
    ResolverStage.LLM_DRAFT,
    ResolverStage.SYSTEM_GENERATED,
    ResolverStage.USER_INPUT,
}


def _allowed_target_stages_for(referencer: TemplateVariable) -> set[ResolverStage]:
    """Stage allowlist for `{{var}}` / `dependent_variables` refs from `referencer`.

    The allowed effective-stage set depends on WHEN the referencer
    itself resolves. LLM_DRAFT-stage referencers benefit from Path B's
    deferred Pass 3 — they may reference USER_INPUT-rooted targets.
    USER_INPUT-stage referencers cannot reference other USER_INPUT
    targets (same-pause, circular). DERIVATIVE / AUTO_DERIVED-stage
    referencers fall back to the conservative set; they typically
    don't carry query templates and aren't subject to substitution.
    """
    if referencer.source is None:
        return _REFERENCEABLE_STAGES
    stage = _STAGE_BY_SOURCE.get(referencer.source)
    if stage == ResolverStage.LLM_DRAFT:
        return _LLM_DRAFT_ALLOWED_TARGET_STAGES
    return _REFERENCEABLE_STAGES


def _is_llm_draft_referencer(referencer: TemplateVariable) -> bool:
    """True iff `referencer.source` maps to LLM_DRAFT stage (the non-USER_INPUT
    family of sources allowed to carry placeholder refs to unbound-root
    auto_derived targets)."""
    if referencer.source is None:
        return False
    return _STAGE_BY_SOURCE.get(referencer.source) == ResolverStage.LLM_DRAFT


GROUP_DROPDOWN_ANCHOR_SOURCES = {
    FieldSource.GROUP_DROPDOWN_FROM_GMAIL,
    FieldSource.GROUP_DROPDOWN_FROM_COURT_DRIVE,
}


# Sources whose resolution requires the user to pick (or type) a value
# at draft time — the USER_INPUT-stage family. Phase 2 forbids these on
# child_only templates because a child resolves straight-through after
# the parent in the bundling engine, and chaining USER_INPUT pauses
# across N children isn't supported in the v1 protocol. Authors should
# push the choice up to a parent variable and inherit the resolved
# value via a `parent_variable` slot configuration.
_USER_INPUT_FAMILY_SOURCES: set[FieldSource] = {
    FieldSource.GROUP_DROPDOWN_FROM_GMAIL,
    FieldSource.GROUP_DROPDOWN_FROM_COURT_DRIVE,
    FieldSource.RECO_CHIPS_FROM_GMAIL,
    FieldSource.RECO_CHIPS_FROM_COURT_DRIVE,
    FieldSource.RECO_CHIPS_FROM_CASE_VECTOR,
    FieldSource.RECO_CHIPS_FROM_DEPENDENT_VARIABLES,
    FieldSource.DROPDOWN_FROM_GMAIL,
    FieldSource.DROPDOWN_FROM_COURT_DRIVE,
    FieldSource.DROPDOWN_FROM_CASE_VECTOR,
    FieldSource.DROPDOWN_FROM_CONSTANTS,
    FieldSource.USER_INPUT_WITH_SUPPORTING_DOCS,
    FieldSource.USER_INPUT_PLAIN_TEXT,
    FieldSource.USER_INPUT_DATE,
    FieldSource.MULTI_SELECT_FROM_CASE_VECTOR,
    FieldSource.MULTI_SELECT_FROM_GMAIL,
}


def assert_child_only_has_no_user_input(
    template_id: str,
    template_spec: list[TemplateVariable],
) -> None:
    """Phase 2 constraint: child_only templates may not contain user-input variables.

    Raises HTTPException(400) listing the offending variable names so the
    author knows what to fix. The constraint exists because the bundling
    engine resolves children straight-through after the parent finishes —
    no nested pause/resume protocol for chained user-input fields. If the
    child needs a user-picked value, the author should add the variable
    to the PARENT, then reference it from the child via a `parent_variable`
    slot configuration on the parent's bundle companion.
    """
    offenders = sorted(
        v.template_variable
        for v in template_spec
        if v.source in _USER_INPUT_FAMILY_SOURCES
    )
    if not offenders:
        return
    raise HTTPException(
        status_code=400,
        detail={
            "child_only_user_input_variables": offenders,
            "message": (
                f"Template '{template_id}' is child-only and cannot contain "
                f"user-input variables. Offending variables: "
                f"{', '.join(offenders)}. Push the user-input variable up to "
                "a parent template and inherit its resolved value into this "
                "child via a `parent_variable` slot configuration on the "
                "parent's bundle companion."
            ),
        },
    )


def partner_variable_names(template_spec: list[TemplateVariable]) -> set[str]:
    """Collect every variable name referenced as right_partner_variable by some group-dropdown anchor.

    Used by validation to carve-out the 'missing source' error for
    legitimate partners.
    """
    partners: set[str] = set()
    for var in template_spec:
        if var.source not in GROUP_DROPDOWN_ANCHOR_SOURCES:
            continue
        params = var.source_params
        if isinstance(params, GroupDropdownSourceParams):
            partners.add(params.right_partner_variable)
    return partners


def auto_derive_parent_names(template_spec: list[TemplateVariable]) -> set[str]:
    """Collect every variable name referenced as `dependent_variable` by
    some auto_derived_from_variable child.

    Used by validation to carve-out the 'missing source' error for
    virtual parents that aren't bound yet — the author can wire references
    to their auto_derived children at compose time before deciding on a
    source. Symmetric with `partner_variable_names` for the group_dropdown
    carve-out.
    """
    parents: set[str] = set()
    for var in template_spec:
        if var.source != FieldSource.AUTO_DERIVED_FROM_VARIABLE:
            continue
        params = var.source_params
        if isinstance(params, AutoDerivedSourceParams):
            parents.add(params.dependent_variable)
    return parents


async def validate_template_spec_source_map(template_spec: list[TemplateVariable]) -> None:
    """Validate every cross-field invariant on the template_spec; raise HTTPException(400) with aggregated errors on failure."""
    errors = []
    expected_params = {
        FieldSource.GMAIL: GmailSourceParams,
        FieldSource.COURT_DRIVE: CourtDriveSourceParams,
        FieldSource.CASE_VECTOR: CaseVectorSourceParams,
        FieldSource.LAW_PRACTICE_VECTOR: VectorSourceParams,
        FieldSource.CONSTANTS: ConstantsSourceParams,
        FieldSource.DEPENDENT_ON_VARIABLE: DependentOnVariableSourceParams,
        FieldSource.SYSTEM_GENERATED: SystemGeneratedSourceParams,
        FieldSource.GROUP_DROPDOWN_FROM_GMAIL: GroupDropdownSourceParams,
        FieldSource.GROUP_DROPDOWN_FROM_COURT_DRIVE: GroupDropdownSourceParams,
        FieldSource.RECO_CHIPS_FROM_GMAIL: RecoChipsEmailSourceParams,
        FieldSource.RECO_CHIPS_FROM_COURT_DRIVE: RecoChipsEmailSourceParams,
        FieldSource.RECO_CHIPS_FROM_CASE_VECTOR: RecoChipsCaseVectorSourceParams,
        FieldSource.RECO_CHIPS_FROM_DEPENDENT_VARIABLES: RecoChipsFromDependentVariablesSourceParams,
        FieldSource.DROPDOWN_FROM_GMAIL: DropdownEmailSourceParams,
        FieldSource.DROPDOWN_FROM_COURT_DRIVE: DropdownEmailSourceParams,
        FieldSource.DROPDOWN_FROM_CASE_VECTOR: DropdownCaseVectorSourceParams,
        FieldSource.DROPDOWN_FROM_CONSTANTS: DropdownFromConstantsSourceParams,
        FieldSource.USER_INPUT_WITH_SUPPORTING_DOCS: UserInputWithSupportingDocsSourceParams,
        FieldSource.USER_INPUT_PLAIN_TEXT: UserInputPlainTextSourceParams,
        FieldSource.USER_INPUT_DATE: UserInputDateSourceParams,
        FieldSource.AUTO_DERIVED_FROM_VARIABLE: AutoDerivedSourceParams,
        FieldSource.MULTI_SELECT_FROM_CASE_VECTOR: MultiSelectFromCaseVectorSourceParams,
        FieldSource.MULTI_SELECT_FROM_GMAIL: MultiSelectFromGmailSourceParams,
        FieldSource.INHERIT_FROM_PARENT: InheritFromParentSourceParams,
    }

    partners = partner_variable_names(template_spec)
    auto_derive_parents = auto_derive_parent_names(template_spec)

    for var in template_spec:
        if not var.source:
            if var.template_variable in partners:
                continue  # legitimate group-dropdown partner — source is filled by its anchor's pick
            if var.kind == "virtual" and var.template_variable in auto_derive_parents:
                # Virtual parent of auto_derived children, awaiting source
                # binding. Allowed during compose so the author can wire
                # references to children before deciding on a source for
                # the parent. The dropdown-format / draft-time invariants
                # will fail later if the author tries to draft without
                # binding it.
                continue
            errors.append(f"Variable '{var.template_variable}' is missing source")
            continue

        if not var.source_params:
            # CASE_VECTOR is the one source where source_params is optional —
            # no params means "BE auto-derives the query from the variable name".
            # Setting CaseVectorSourceParams.text_query is opt-in for explicit control.
            if var.source == FieldSource.CASE_VECTOR:
                continue
            # INHERIT_FROM_PARENT's only param (fallback_value) is optional —
            # missing source_params is a valid "no fallback" state.
            if var.source == FieldSource.INHERIT_FROM_PARENT:
                continue
            errors.append(f"Variable '{var.template_variable}' is missing source_params")
            continue

        expected_type = expected_params.get(var.source)
        # CASE_VECTOR accepts both CaseVectorSourceParams (the new optional-
        # text_query class) and VectorSourceParams (the legacy required-
        # text_query class). Pydantic v2's union resolution prefers
        # VectorSourceParams when both can parse `{"text_query": "..."}`,
        # which would otherwise reject existing case_vector specs at compose.
        # Accepting either is duck-typed-correct since the case_vector
        # handler reads via `getattr(p, "text_query", None)`.
        if var.source == FieldSource.CASE_VECTOR:
            if not isinstance(var.source_params, (CaseVectorSourceParams, VectorSourceParams)):
                errors.append(
                    f"Variable '{var.template_variable}' has source 'case_vector' "
                    f"but source_params is {type(var.source_params).__name__}, "
                    f"expected CaseVectorSourceParams (text_query optional)."
                )
                continue
        # GMAIL and COURT_DRIVE share identical source_params shapes
        # (subject_query, body_query, scope_to_current_case, optional date_range).
        # Pydantic v2's union resolution picks the first matching variant
        # (GmailSourceParams), so a court_drive payload deserializes as
        # GmailSourceParams and trips the type check. Accepting either is
        # duck-typed-correct since the runtime handlers dispatch on
        # FieldSource and read params via getattr.
        elif var.source in (FieldSource.GMAIL, FieldSource.COURT_DRIVE):
            if not isinstance(var.source_params, (GmailSourceParams, CourtDriveSourceParams)):
                errors.append(
                    f"Variable '{var.template_variable}' has source '{var.source.value}' "
                    f"but source_params is {type(var.source_params).__name__}, "
                    f"expected GmailSourceParams or CourtDriveSourceParams."
                )
                continue
        elif not isinstance(var.source_params, expected_type):
            errors.append(
                f"Variable '{var.template_variable}' has source '{var.source.value}' "
                f"but source_params is {type(var.source_params).__name__}, "
                f"expected {expected_type.__name__}"
            )
            continue

        if var.source == FieldSource.CONSTANTS:
            params = var.source_params
            if isinstance(params, ConstantsSourceParams) and not params.short_code:
                errors.append(
                    f"Variable '{var.template_variable}' with source 'constants' "
                    "requires short_code in source_params"
                )

    _validate_dependent_variable_references(template_spec, errors)
    _validate_group_dropdown_references(template_spec, errors)
    _validate_auto_derived_references(template_spec, errors)
    _validate_query_template_refs(template_spec, errors)
    _validate_reco_chips_dependent_variables(template_spec, errors)
    _validate_no_resolution_cycles(template_spec, errors)
    _validate_read_only_consistency(template_spec, errors)
    _validate_virtual_variables_have_dependents(template_spec, errors)
    _validate_dropdown_format_includes_auto_derive_children(template_spec, errors)
    await _validate_constants_short_codes_exist(template_spec, errors)

    if errors:
        raise HTTPException(status_code=400, detail={"validation_errors": errors})


def _validate_group_dropdown_references(
    template_spec: list[TemplateVariable],
    errors: list[str],
) -> None:
    by_name = {var.template_variable: var for var in template_spec}
    partner_claimed_by: dict[str, list[str]] = {}

    for var in template_spec:
        if var.source not in GROUP_DROPDOWN_ANCHOR_SOURCES:
            continue
        params = var.source_params
        if not isinstance(params, GroupDropdownSourceParams):
            continue

        partner_name = params.right_partner_variable

        if partner_name == var.template_variable:
            errors.append(
                f"Variable '{var.template_variable}' cannot be its own right_partner_variable"
            )
            continue

        partner_var = by_name.get(partner_name)
        if partner_var is None:
            errors.append(
                f"Variable '{var.template_variable}' names right_partner_variable "
                f"'{partner_name}' which does not exist in template_spec"
            )
            continue

        if partner_var.source is not None:
            errors.append(
                f"Variable '{var.template_variable}' names right_partner_variable "
                f"'{partner_name}', but '{partner_name}' already has a source "
                f"('{partner_var.source.value}'); partner must have source unset"
            )
            continue

        partner_claimed_by.setdefault(partner_name, []).append(var.template_variable)

    for partner_name, anchors in partner_claimed_by.items():
        if len(anchors) > 1:
            anchor_list = ", ".join(f"'{n}'" for n in anchors)
            errors.append(
                f"Partner variable '{partner_name}' is claimed by multiple anchors "
                f"({anchor_list}); each partner must be claimed by exactly one anchor"
            )


async def _validate_constants_short_codes_exist(
    template_spec: list[TemplateVariable],
    errors: list[str],
) -> None:
    """Check that every reference_data short_code referenced by constants OR
    dropdown_from_constants fields actually exists. Aggregates references
    across both source types so we issue one DB query, not one per field."""
    referenced: dict[str, list[str]] = {}
    for var in template_spec:
        code: str | None = None
        if var.source == FieldSource.CONSTANTS:
            params = var.source_params
            if isinstance(params, ConstantsSourceParams) and params.short_code:
                code = params.short_code
        elif var.source == FieldSource.DROPDOWN_FROM_CONSTANTS:
            params = var.source_params
            if isinstance(params, DropdownFromConstantsSourceParams) and params.reference_short_code:
                code = params.reference_short_code
        if code is None:
            continue
        referenced.setdefault(code, []).append(var.template_variable)

    if not referenced:
        return

    existing_codes = {ref.short_code for ref in await ReferenceDataRepository.list()}
    missing = sorted(code for code in referenced if code not in existing_codes)
    for code in missing:
        consumer_list = ", ".join(f"'{name}'" for name in referenced[code])
        errors.append(
            f"reference_data short_code '{code}' does not exist "
            f"(referenced by {consumer_list})"
        )


def _validate_dependent_variable_references(
    template_spec: list[TemplateVariable],
    errors: list[str],
) -> None:
    by_name = {var.template_variable: var for var in template_spec}

    for var in template_spec:
        if var.source != FieldSource.DEPENDENT_ON_VARIABLE:
            continue
        params = var.source_params
        if not isinstance(params, DependentOnVariableSourceParams):
            continue

        parent_name = params.dependent_variable
        if parent_name == var.template_variable:
            errors.append(
                f"Variable '{var.template_variable}' cannot depend on itself"
            )
            continue

        parent = by_name.get(parent_name)
        if parent is None:
            errors.append(
                f"Variable '{var.template_variable}' depends on "
                f"'{parent_name}' which does not exist in template_spec"
            )
            continue

        if parent.source == FieldSource.DEPENDENT_ON_VARIABLE:
            errors.append(
                f"Variable '{var.template_variable}' depends on '{parent_name}' "
                "which is itself a dependent_on_variable; chained dependents are not supported"
            )


def _validate_auto_derived_references(
    template_spec: list[TemplateVariable],
    errors: list[str],
) -> None:
    """Validate author-readonly auto-derived variables: parent must exist and must not be self.

    Chained auto-derivation (parent is itself auto_derived) IS supported —
    the runtime resolver handles it via iterative topological passes. Cycles
    are caught separately by `_validate_no_resolution_cycles` so the error
    message can name the full cycle (across the whole resolution graph,
    not just auto_derive parents).
    """
    by_name = {var.template_variable: var for var in template_spec}

    for var in template_spec:
        if var.source != FieldSource.AUTO_DERIVED_FROM_VARIABLE:
            continue
        params = var.source_params
        if not isinstance(params, AutoDerivedSourceParams):
            continue

        parent_name = params.dependent_variable
        if parent_name == var.template_variable:
            errors.append(
                f"Variable '{var.template_variable}' cannot auto-derive from itself"
            )
            continue

        if by_name.get(parent_name) is None:
            errors.append(
                f"Variable '{var.template_variable}' auto-derives from "
                f"'{parent_name}' which does not exist in template_spec"
            )


def _collect_resolution_edges(
    template_spec: list[TemplateVariable],
) -> dict[str, set[str]]:
    """Build a child → {parent, ...} dependency graph across every resolution-time edge.

    Edges include:
      - `auto_derived_from_variable` parent edges (existing).
      - `{{var}}` references in any source_params query field (subject_query,
        body_query, text_query) — substituted at fetch time, so the
        referencing variable depends on the referenced one resolving first.
      - `dependent_variables` lists on `reco_chips_from_dependent_variables`
        sources — the chip composer reads each declared variable's resolved
        value before generation runs.
      - `dependent_chip_variables` lists on `reco_chips_from_dependent_variables`
        sources — chip-to-chip alignment dependencies. The dependent's chips
        only generate after the target's chips, so a cycle through these
        edges is unfixable at runtime.
      - `case_vector_queries[*].text_query` `{{var}}` refs (covered by the
        generic walker above).

    Self-references and edges to non-existent variables are dropped — those
    are reported by their respective per-edge validators with friendlier
    error messages.
    """
    by_name = {v.template_variable: v for v in template_spec}
    edges: dict[str, set[str]] = {v.template_variable: set() for v in template_spec}

    for var in template_spec:
        params = var.source_params
        if isinstance(params, AutoDerivedSourceParams):
            parent = params.dependent_variable
            if parent and parent != var.template_variable and parent in by_name:
                edges[var.template_variable].add(parent)
        if isinstance(params, RecoChipsFromDependentVariablesSourceParams):
            for parent in params.dependent_variables:
                if parent and parent != var.template_variable and parent in by_name:
                    edges[var.template_variable].add(parent)
            for parent in params.dependent_chip_variables:
                if parent and parent != var.template_variable and parent in by_name:
                    edges[var.template_variable].add(parent)
        for ref in extract_var_refs_from_source_params(params):
            if ref != var.template_variable and ref in by_name:
                edges[var.template_variable].add(ref)

    return edges


def _validate_no_resolution_cycles(
    template_spec: list[TemplateVariable],
    errors: list[str],
) -> None:
    """Detect any cycle across the full resolution-time dependency graph.

    Replaces the older auto_derive-only cycle check. Builds the unified
    graph (auto_derive parents + `{{var}}` refs + `dependent_variables`)
    and runs Kahn's algorithm. Anything still in the graph after the
    queue drains is part of a cycle.

    A chain like `prior_case_number → prior_dismissal_row → claim_number`
    is acyclic and passes. A loop `A → B → A` (or longer) errors with
    every cycle member named.
    """
    edges = _collect_resolution_edges(template_spec)
    if not edges:
        return

    out_count: dict[str, int] = {n: len(parents) for n, parents in edges.items()}
    children_of: dict[str, list[str]] = {n: [] for n in edges}
    for child, parents in edges.items():
        for parent in parents:
            children_of.setdefault(parent, []).append(child)

    queue: list[str] = [n for n, c in out_count.items() if c == 0]
    seen: set[str] = set(queue)
    while queue:
        node = queue.pop()
        for child in children_of.get(node, []):
            if child in seen:
                continue
            out_count[child] -= 1
            if out_count[child] == 0:
                seen.add(child)
                queue.append(child)

    cycle_members = sorted(n for n in edges if n not in seen)
    if cycle_members:
        errors.append(
            f"Resolution cycle detected involving: {', '.join(cycle_members)} "
            "— auto_derive parents, {{var}} references, and dependent_variables "
            "lists collectively cannot form a loop."
        )


def _validate_query_template_refs(
    template_spec: list[TemplateVariable],
    errors: list[str],
) -> None:
    """Validate every `{{var}}` reference in source-params query fields.

    Two checks per ref:
      1. Existence — the referenced variable must be in the spec.
      2. Effective stage — the referenced variable's EFFECTIVE stage
         must be in `_REFERENCEABLE_STAGES`. For auto_derived targets,
         "effective stage" walks the parent chain to the root and uses
         the root's stage (so a `vehicle_name` whose root parent is a
         case_vector-bound `vehicle_record` resolves at LLM_DRAFT and
         IS referenceable, while a child of a `dropdown_from_gmail`
         parent is NOT). See `root_parent_stage` for chain semantics.
         Pass-2 fetch substitutes from values resolved before the
         user-input pause; refs to anything else would always substitute
         empty strings.
    """
    by_name = {v.template_variable: v for v in template_spec}
    for var in template_spec:
        params = var.source_params
        refs = extract_var_refs_from_source_params(params)
        for ref in sorted(refs):
            target = by_name.get(ref)
            if target is None:
                errors.append(
                    f"Variable '{var.template_variable}' references unknown "
                    f"variable '{{{{{ref}}}}}' in its query string"
                )
                continue
            if (
                target.source == FieldSource.AUTO_DERIVED_FROM_VARIABLE
                and root_parent_is_unbound(target, by_name)
                and _is_llm_draft_referencer(var)
            ):
                # Placeholder reference — target is auto_derived from a
                # parent whose source isn't bound yet. Accept at compose
                # time so the author can wire references before binding
                # sources; once the parent is bound, the existing
                # stage-based rules apply on the next save.
                continue
            if target.source is None:
                # Group-dropdown partner OR genuinely unbound — its
                # effective stage cannot be determined until the author
                # binds a source, so substitution would silently fail.
                errors.append(
                    f"Variable '{var.template_variable}' references "
                    f"'{{{{{ref}}}}}' but its target has no source — "
                    "only LLM_DRAFT and SYSTEM_GENERATED variables can be referenced."
                )
                continue
            stage = root_parent_stage(target, by_name)
            allowed = _allowed_target_stages_for(var)
            if stage not in allowed:
                stage_label = stage.value if stage else "unknown"
                errors.append(
                    f"Variable '{var.template_variable}' references "
                    f"'{{{{{ref}}}}}' (stage={stage_label}) in its query string, "
                    "but its referencer-stage only permits "
                    f"{{{', '.join(sorted(s.value for s in allowed))}}} effective stages."
                )


def _validate_reco_chips_dependent_variables(
    template_spec: list[TemplateVariable],
    errors: list[str],
) -> None:
    """Validate context-source lists on reco_chips_from_dependent_variables sources.

    `dependent_variables` rules:
      - Must reference an existing variable.
      - Target's stage must be LLM_DRAFT or SYSTEM_GENERATED (resolves
        before chip generation runs).
      - No self-reference.

    `dependent_chip_variables` rules:
      - Must reference an existing variable.
      - Target's source must be `RECO_CHIPS_FROM_DEPENDENT_VARIABLES` —
        the alignment dependency reads the target's *generated chip array*,
        which only exists for that source type.
      - No self-reference.

    `case_vector_queries` rules:
      - `{{var}}` refs inside text_query are validated by
        `_validate_query_template_refs` (same `_REFERENCEABLE_STAGES` rule).

    At least ONE of {dependent_variables, case_vector_queries,
    dependent_chip_variables} must be non-empty — the chip generator
    has nothing to compose without context.
    """
    by_name = {v.template_variable: v for v in template_spec}
    for var in template_spec:
        params = var.source_params
        if not isinstance(params, RecoChipsFromDependentVariablesSourceParams):
            continue
        if (
            not params.dependent_variables
            and not params.case_vector_queries
            and not params.dependent_chip_variables
        ):
            errors.append(
                f"Variable '{var.template_variable}' is reco_chips_from_dependent_variables "
                "but has no dependent_variables, case_vector_queries, or "
                "dependent_chip_variables — the chip generator needs at least one "
                "context source to compose from."
            )
            continue
        for ref in params.dependent_variables:
            if ref == var.template_variable:
                errors.append(
                    f"Variable '{var.template_variable}' cannot reference itself "
                    "in dependent_variables"
                )
                continue
            target = by_name.get(ref)
            if target is None:
                errors.append(
                    f"Variable '{var.template_variable}' has dependent_variable "
                    f"'{ref}' which does not exist in template_spec"
                )
                continue
            if (
                target.source == FieldSource.AUTO_DERIVED_FROM_VARIABLE
                and root_parent_is_unbound(target, by_name)
                and _is_llm_draft_referencer(var)
            ):
                # Placeholder reference — see _validate_query_template_refs.
                continue
            if target.source is None:
                errors.append(
                    f"Variable '{var.template_variable}' has dependent_variable "
                    f"'{ref}' but its target has no source — only LLM_DRAFT and "
                    "SYSTEM_GENERATED variables can be referenced."
                )
                continue
            stage = root_parent_stage(target, by_name)
            allowed = _allowed_target_stages_for(var)
            if stage not in allowed:
                stage_label = stage.value if stage else "unknown"
                errors.append(
                    f"Variable '{var.template_variable}' has dependent_variable "
                    f"'{ref}' (stage={stage_label}), but its referencer-stage "
                    f"only permits {{{', '.join(sorted(s.value for s in allowed))}}} "
                    "effective stages."
                )
        for ref in params.dependent_chip_variables:
            if ref == var.template_variable:
                errors.append(
                    f"Variable '{var.template_variable}' cannot reference itself "
                    "in dependent_chip_variables"
                )
                continue
            target = by_name.get(ref)
            if target is None:
                errors.append(
                    f"Variable '{var.template_variable}' has dependent_chip_variable "
                    f"'{ref}' which does not exist in template_spec"
                )
                continue
            if target.source != FieldSource.RECO_CHIPS_FROM_DEPENDENT_VARIABLES:
                source_label = target.source.value if target.source else "null"
                errors.append(
                    f"Variable '{var.template_variable}' has dependent_chip_variable "
                    f"'{ref}' but its source is '{source_label}', not "
                    "'reco_chips_from_dependent_variables' — chip-to-chip alignment "
                    "only works between sibling chip generators."
                )


def _validate_read_only_consistency(
    template_spec: list[TemplateVariable],
    errors: list[str],
) -> None:
    """`read_only=true` is reserved for auto_derived_from_variable today.
    Pairing it with any other source type is a contract violation."""
    for var in template_spec:
        if not var.read_only:
            continue
        if var.source != FieldSource.AUTO_DERIVED_FROM_VARIABLE:
            source_label = var.source.value if var.source else "null"
            errors.append(
                f"Variable '{var.template_variable}' has read_only=true with source "
                f"'{source_label}'; read_only is only valid for auto_derived_from_variable"
            )


_DROPDOWN_PARENT_SOURCES = {
    FieldSource.DROPDOWN_FROM_GMAIL,
    FieldSource.DROPDOWN_FROM_COURT_DRIVE,
    FieldSource.DROPDOWN_FROM_CASE_VECTOR,
}


def _validate_dropdown_format_includes_auto_derive_children(
    template_spec: list[TemplateVariable],
    errors: list[str],
) -> None:
    """Every auto_derive child of a `dropdown_from_*` parent must have its
    `template_property_marker` (the example value pulled from the docx)
    appear as a substring in the parent's `example_format`.

    Why: the dropdown extractor agent transcribes options verbatim from
    source material, shaped to match `example_format`. If the format
    omits a child's data, the picked row's resolved value won't carry
    that data either, AutoDeriveAgent returns empty for the child, and
    the placeholder leaks through to the rendered docx.

    Children with empty `template_property_marker` are skipped — without
    a concrete example value, the validator has nothing to look for; any
    coverage gap there will only surface at runtime.
    """
    by_name = {var.template_variable: var for var in template_spec}

    children_by_parent: dict[str, list[TemplateVariable]] = {}
    for var in template_spec:
        if var.source != FieldSource.AUTO_DERIVED_FROM_VARIABLE:
            continue
        params = var.source_params
        if not isinstance(params, AutoDerivedSourceParams):
            continue
        # Only EXTRACT_SUBSTRING children read from the parent's row format.
        # PLURALIZE_BY_COUNT children just need the parent's pick count, not
        # any column data — so the example_format coverage check doesn't apply.
        if params.rule_effect != AutoDerivedRuleEffect.EXTRACT_SUBSTRING:
            continue
        children_by_parent.setdefault(params.dependent_variable, []).append(var)

    for parent_name, children in children_by_parent.items():
        parent = by_name.get(parent_name)
        if parent is None or parent.source not in _DROPDOWN_PARENT_SOURCES:
            continue
        params = parent.source_params
        if not isinstance(params, (DropdownEmailSourceParams, DropdownCaseVectorSourceParams)):
            continue
        example_format = params.example_format or ""
        for child in children:
            marker = child.template_property_marker or ""
            if not marker:
                continue
            if marker in example_format:
                continue
            errors.append(
                f"Variable '{parent_name}' is a dropdown source with auto-derive child "
                f"'{child.template_variable}' but its example_format does not include "
                f"'{marker}'. Add the child's example value to example_format so the "
                f"picked row carries enough data to derive '{child.template_variable}'."
            )


def _validate_virtual_variables_have_dependents(
    template_spec: list[TemplateVariable],
    errors: list[str],
) -> None:
    """Every `virtual` variable (no `template_variable_string`) must be
    referenced by at least one `auto_derived_from_variable` child as
    `dependent_variable`. Otherwise the virtual is dead data — it gets
    resolved at runtime but never reaches the docx, since it has no
    placeholder of its own and nothing downstream consumes it.

    The tabular row pattern intentionally produces virtuals (one per
    row source) so that N child cells can derive from a single atomic
    pick. A virtual without children is always a mistake.
    """
    auto_derive_parents: set[str] = set()
    for var in template_spec:
        if var.source != FieldSource.AUTO_DERIVED_FROM_VARIABLE:
            continue
        params = var.source_params
        if isinstance(params, AutoDerivedSourceParams):
            auto_derive_parents.add(params.dependent_variable)

    for var in template_spec:
        if var.kind != "virtual":
            continue
        if var.template_variable in auto_derive_parents:
            continue
        errors.append(
            f"Variable '{var.template_variable}' is virtual (no template_variable_string) "
            f"but no auto_derived_from_variable child references it as dependent_variable "
            f"— remove it or add at least one auto_derive dependent."
        )
