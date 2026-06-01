"""Spec validators shared between the composer router (save-time
checks), the bundling engine (runtime checks), and the Phase 3
publish endpoint.

Two validator surfaces here:

1. `assert_part_of_packet_has_no_user_input_v2` — single-check that
   guards companion templates from accidentally including user-input
   fields. Used at the composer's "role save" CTA AND inside
   `run_bundle_v2` as a runtime safety net. Mirrors v1's
   `assert_child_only_has_no_user_input` 1:1.

2. `validate_for_publish` — full publish-gate suite that runs BEFORE
   the `POST /api/v3/studio/templates/{id}/publish` endpoint
   snapshots a spec to `published_spec`. Mirrors v1's
   `validate_template_spec_source_map` minus the v2-retired checks
   (group_dropdown / dropdown_format_includes_auto_derive_children /
   reco_chips_dependent — no equivalents in the v2 source taxonomy).
   Aggregates errors instead of raising per-check, so the FE gets a
   complete list to surface to the paralegal in one shot.
"""

from __future__ import annotations

from typing import Iterable, Mapping

from src.core.common.storage.database import (
    AttorneyRosterRepository,
    ReferenceDataRepository,
)

from ..types.fields import TemplateFieldV2
from ..types.wizard_sources import PresentationShape, SourceKind


_USER_INPUT_SOURCE_KIND = "author_input"
_PICKABLE_SOURCE_KINDS = frozenset({"gmail", "case_file", "attorney"})


def assert_part_of_packet_has_no_user_input_v2(
    fields: Iterable,
) -> list[str]:
    """Return the sorted list of variable names whose params put them in
    the user-input family. Empty list = OK to set role to `part_of_packet`
    or to enroll the template as a companion.

    Accepts BOTH:
    - `TemplateFieldV2` ORM rows (`row.template_variable`, `row.params`)
    - `TemplateFieldV2` Pydantic objects (`obj.template_variable`,
      `obj.params`)

    Treats `params` either as a Pydantic `WizardSourceParams` (with
    `.source` / `.presentation_shape`) or as a plain dict (the shape
    persisted in JSONB on `template_fields_v2.params`).

    User-input family:
    - `source == "author_input"` (any kind)
    - `source in {"gmail", "case_file", "attorney"}` AND
      `presentation_shape != "raw"`

    Other sources are safe in a companion (deterministic + LLM-extracted
    + derived + value_from_parent_bundle resolve without a paralegal
    pause).
    """
    offenders: list[str] = []
    for row in fields:
        variable = getattr(row, "template_variable", None)
        params = getattr(row, "params", None)
        if variable is None or params is None:
            continue

        source, shape = _params_source_and_shape(params)
        if source == _USER_INPUT_SOURCE_KIND:
            offenders.append(variable)
            continue
        if source in _PICKABLE_SOURCE_KINDS and shape != "raw":
            offenders.append(variable)
    return sorted(offenders)


def _params_source_and_shape(params) -> tuple[str | None, str]:
    """Read `(source, presentation_shape)` out of params regardless of
    whether it's a Pydantic model or a plain dict.

    Returns `(source, shape)` — `shape` defaults to `"raw"` when
    missing (matches `WizardSourceParams.presentation_shape`'s
    default).
    """
    if isinstance(params, Mapping):
        return params.get("source"), params.get("presentation_shape", "raw")
    source = getattr(params, "source", None)
    source_value = getattr(source, "value", source)
    shape = getattr(params, "presentation_shape", "raw")
    shape_value = getattr(shape, "value", shape)
    return source_value, shape_value or "raw"


# ─── publish-gate validator suite ────────────────────────────────────


async def validate_for_publish(
    fields: list[TemplateFieldV2],
    *,
    role: str | None = None,
) -> list[str]:
    """Run every publish-gate check and return the aggregated error list.

    Errors are human-readable strings the FE surfaces inline above the
    publish CTA. Empty list = OK to snapshot the spec into
    `templates_v2.published_spec` + set `published_at`.

    `role` is the template's `config.role` (`single` / `master` /
    `part_of_packet`). When `part_of_packet`, the companion safety
    net re-runs `assert_part_of_packet_has_no_user_input_v2` defensively
    so a paralegal can't publish a companion that drifted into
    user-input territory between role-save and publish. Other roles
    legitimately have user-input fields, so the check is skipped.

    Order is deliberate: cheap structural checks first, async DB
    lookups last, so a malformed spec fails fast without burning
    queries.
    """
    errors: list[str] = []
    _validate_dependent_variable_references_v2(fields, errors)
    _validate_query_dependencies_v2(fields, errors)
    _validate_no_resolution_cycles_v2(fields, errors)
    _validate_virtual_parents_have_children_v2(fields, errors)
    _validate_user_input_label_required_v2(fields, errors)
    await _validate_constants_short_codes_exist_v2(fields, errors)
    await _validate_attorney_ids_exist_v2(fields, errors)
    if role == "part_of_packet":
        offenders = assert_part_of_packet_has_no_user_input_v2(fields)
        if offenders:
            errors.append(
                f"Companion templates cannot include user-input fields. "
                f"Offending variables: {', '.join(offenders)}. "
                f"Push these up to the lead template instead."
            )
    return errors


def _validate_dependent_variable_references_v2(
    fields: list[TemplateFieldV2],
    errors: list[str],
) -> None:
    """Every `derived_from_variable` field's `dependent_variable` must
    reference an existing variable + cannot be self.

    Chained derives (parent is also derived_from_variable) ARE allowed —
    the resolver handles iterative passes. Cycles get caught by
    `_validate_no_resolution_cycles_v2`.
    """
    by_name = {f.template_variable: f for f in fields}
    for field in fields:
        if field.params is None:
            continue
        if field.params.source != SourceKind.DERIVED_FROM_VARIABLE:
            continue
        parent = (field.params.dependent_variable or "").strip()
        if not parent:
            errors.append(
                f"Variable '{field.template_variable}' is based on another field "
                f"but no parent field is selected — open the wizard's Find step "
                f"and pick one."
            )
            continue
        if parent == field.template_variable:
            errors.append(
                f"Variable '{field.template_variable}' cannot be based on itself."
            )
            continue
        if parent not in by_name:
            errors.append(
                f"Variable '{field.template_variable}' is based on '{parent}', "
                f"which does not exist in this template."
            )


def _validate_query_dependencies_v2(
    fields: list[TemplateFieldV2],
    errors: list[str],
) -> None:
    """Every entry in a field's `params.query_dependencies` must
    reference an existing variable + cannot be self.

    No stage gate here — Wave-B classification at runtime defers
    fields whose query_dependencies transitively reach a USER_INPUT
    root to Pass 3 (post-resume). All edges are legal; only existence
    + non-self is enforced at publish.
    """
    by_name = {f.template_variable: f for f in fields}
    for field in fields:
        if field.params is None:
            continue
        for dep in field.params.query_dependencies:
            dep = (dep or "").strip()
            if not dep:
                continue
            if dep == field.template_variable:
                errors.append(
                    f"Variable '{field.template_variable}' cannot reference "
                    f"itself in its query dependencies."
                )
                continue
            if dep not in by_name:
                errors.append(
                    f"Variable '{field.template_variable}' references "
                    f"'{dep}' as a query dependency, but '{dep}' does not "
                    f"exist in this template."
                )


def _validate_no_resolution_cycles_v2(
    fields: list[TemplateFieldV2],
    errors: list[str],
) -> None:
    """Kahn topological sort on the union of derived_from_variable +
    query_dependencies edges. Anything still in the graph after the
    queue drains is part of a cycle.

    Self-references and edges to non-existent variables are dropped
    here — those get cleaner error messages from the dedicated
    per-edge validators above.
    """
    by_name = {f.template_variable: f for f in fields}
    edges: dict[str, set[str]] = {name: set() for name in by_name}

    for field in fields:
        if field.params is None:
            continue
        name = field.template_variable
        if field.params.source == SourceKind.DERIVED_FROM_VARIABLE:
            parent = (field.params.dependent_variable or "").strip()
            if parent and parent != name and parent in by_name:
                edges[name].add(parent)
        for dep in field.params.query_dependencies:
            dep = (dep or "").strip()
            if dep and dep != name and dep in by_name:
                edges[name].add(dep)

    if not any(edges.values()):
        return

    in_count = {n: len(parents) for n, parents in edges.items()}
    children_of: dict[str, list[str]] = {n: [] for n in edges}
    for child, parents in edges.items():
        for parent in parents:
            children_of[parent].append(child)

    queue = [n for n, c in in_count.items() if c == 0]
    seen: set[str] = set(queue)
    while queue:
        node = queue.pop()
        for child in children_of[node]:
            if child in seen:
                continue
            in_count[child] -= 1
            if in_count[child] == 0:
                seen.add(child)
                queue.append(child)

    cycle_members = sorted(n for n in edges if n not in seen)
    if cycle_members:
        errors.append(
            f"Resolution cycle detected between: "
            f"{', '.join(cycle_members)}. Fields cannot reference each "
            f"other in a loop — break one of the dependencies."
        )


def _validate_virtual_parents_have_children_v2(
    fields: list[TemplateFieldV2],
    errors: list[str],
) -> None:
    """A virtual parent (`template_property_marker is None`) must have
    at least one `derived_from_variable` child referencing it. A
    virtual without children is dead data — it resolves at runtime
    but never reaches the docx, so it's always an authoring mistake.
    """
    derived_parents: set[str] = set()
    for field in fields:
        if field.params is None:
            continue
        if field.params.source == SourceKind.DERIVED_FROM_VARIABLE:
            parent = (field.params.dependent_variable or "").strip()
            if parent:
                derived_parents.add(parent)

    for field in fields:
        if field.template_property_marker is not None:
            continue
        if field.template_variable in derived_parents:
            continue
        errors.append(
            f"Variable '{field.template_variable}' is a virtual parent "
            f"(no value in the document) but no other field is based on "
            f"it. Either remove it or add a 'Based on another field' "
            f"child that references it."
        )


def _validate_user_input_label_required_v2(
    fields: list[TemplateFieldV2],
    errors: list[str],
) -> None:
    """Every user-input-family field MUST have a non-empty label
    (Behavior Contract #2 from the plan). The wizard validates this
    on the FE, but a paralegal can also reach this state by saving
    a field via direct PATCH; the publish gate catches it.
    """
    for field in fields:
        if field.params is None:
            continue
        source = field.params.source
        shape = field.params.presentation_shape
        needs_label = (
            source == SourceKind.AUTHOR_INPUT
            or (
                source in (SourceKind.GMAIL, SourceKind.CASE_FILE, SourceKind.ATTORNEY)
                and shape != PresentationShape.RAW
            )
        )
        if not needs_label:
            continue
        if not (field.params.label or "").strip():
            errors.append(
                f"Variable '{field.template_variable}' needs a question "
                f"prompt for the paralegal — open the wizard and fill in "
                f"the label."
            )


async def _validate_constants_short_codes_exist_v2(
    fields: list[TemplateFieldV2],
    errors: list[str],
) -> None:
    """For every `source == constants` field, the `constants_short_code`
    must resolve to a row in `reference_data`. One DB call total —
    we list all rows and check set membership in memory.
    """
    referenced: dict[str, list[str]] = {}
    for field in fields:
        if field.params is None:
            continue
        if field.params.source != SourceKind.CONSTANTS:
            continue
        code = (field.params.constants_short_code or "").strip()
        if not code:
            errors.append(
                f"Variable '{field.template_variable}' uses a firm "
                f"constant but no constant is picked. Open the wizard's "
                f"Fine-tune step and choose one."
            )
            continue
        referenced.setdefault(code, []).append(field.template_variable)

    if not referenced:
        return

    try:
        rows = await ReferenceDataRepository.list()
    except Exception as err:  # noqa: BLE001
        errors.append(
            f"Could not verify firm constants exist (DB lookup failed: {err}). "
            f"Try publishing again."
        )
        return
    existing = {r.short_code for r in rows}
    for code in sorted(set(referenced) - existing):
        consumers = ", ".join(f"'{n}'" for n in referenced[code])
        errors.append(
            f"Firm constant '{code}' does not exist (referenced by {consumers}). "
            f"Add it in firm settings or change the field's choice."
        )


async def _validate_attorney_ids_exist_v2(
    fields: list[TemplateFieldV2],
    errors: list[str],
) -> None:
    """For every `(source=attorney, shape=raw)` field with a pinned
    `attorney_id`, the id must resolve to an attorney in the firm's
    ATTORNEYS roster.

    Pickable shapes (dropdown / multi_select) leave `attorney_id`
    empty by design — paralegal picks at draft time. Only `raw` mode
    is validated here.
    """
    referenced: dict[str, list[str]] = {}
    for field in fields:
        if field.params is None:
            continue
        if field.params.source != SourceKind.ATTORNEY:
            continue
        if field.params.presentation_shape != PresentationShape.RAW:
            continue
        attorney_id = (field.params.attorney_id or "").strip()
        if not attorney_id:
            errors.append(
                f"Variable '{field.template_variable}' pins a specific "
                f"attorney but no attorney is picked. Open the wizard's "
                f"Fine-tune step and choose one — or switch to 'Pick at "
                f"draft time'."
            )
            continue
        referenced.setdefault(attorney_id, []).append(field.template_variable)

    if not referenced:
        return

    try:
        roster = await AttorneyRosterRepository.list()
    except Exception as err:  # noqa: BLE001
        errors.append(
            f"Could not verify attorney roster (DB lookup failed: {err}). "
            f"Try publishing again."
        )
        return
    existing = {att.id for att in roster}
    for attorney_id in sorted(set(referenced) - existing):
        consumers = ", ".join(f"'{n}'" for n in referenced[attorney_id])
        errors.append(
            f"Attorney id '{attorney_id}' is not in the firm's roster "
            f"(referenced by {consumers}). The attorney may have been "
            f"removed; re-pin via the wizard."
        )
