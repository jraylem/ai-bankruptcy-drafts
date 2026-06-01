"""v2 bundling engine — schedules + resolves + finalizes a parent's
companions.

Called by the dry-run / draft router AFTER the parent has fully
resolved and finalized its docx. Walks the parent's
`TemplateConfigV2.companions`, resolves each scheduled child against
the same case + parent context, and returns a list of
`BundleChildRunV2` results — one per produced child docx.

Phase 2 invariant (enforced by the save-time validator
`assert_part_of_packet_has_no_user_input_v2` + a runtime check here):
companion templates may NOT contain user-input fields. The bundling
engine relies on children resolving straight-through — there is NO
nested AwaitingInputResponse pause across N children. If a child does
surface a pending input here it indicates the save-time validator was
bypassed and we hard-fail.

v2 differences from v1:
- `bundle_picks` key is `companion.id` (stable Phase 0 type field),
  not v1's stringified companion index. Same for `BranchOption.id`
  as the pick value.
- Children run in PARALLEL via `asyncio.gather`. v1 ran them
  sequentially.
- Children are fetched from `templates_v2` (v1 used draft_templates).
- The full v2 pipeline + finalizer chain is invoked — no v1 imports.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict

from src.core.common.documents.docx_template import DocxTemplateService
from src.core.common.storage.r2 import r2_service

from ..repositories import TemplatesV2Repository
from ..types.bundling import (
    BranchCompanion,
    BundleCompanion,
    FixedCompanion,
    SlotConfig,
    TemplateConfigV2,
    TemplateRole,
)
from ..types.fields import TemplateFieldV2, TemplateSpecV2
from ..types.orchestration import (
    BundleChildRunV2,
    ParentBundleContextV2,
)
from ..types.resolution import ResolvedTemplateValueV2
from ..types.wizard_sources import WizardSourceParams
from .finalizer import finalize_run_v2
from .pipeline import run_initial_stages_v2
from .validators import assert_part_of_packet_has_no_user_input_v2

logger = logging.getLogger(__name__)


class _PlannedChildV2(BaseModel):
    """Internal — one scheduled child with everything needed to run it."""

    model_config = ConfigDict(extra="forbid")

    template_id: str
    companion_label: str
    slot_configurations: dict[str, SlotConfig]


def plan_bundle_v2(
    bundle_companions: list[BundleCompanion],
    bundle_picks: dict[str, str] | None,
) -> list[_PlannedChildV2]:
    """Walk the parent's companions and resolve each one to a scheduled
    child.

    Fixed companions always schedule. Branch companions look up the
    user's pre-flight pick by `companion.id` and schedule the matching
    `BranchOption` by its `id`.

    Raises `HTTPException(400)` when:
    - a Fixed companion has no `child_template_id` (incomplete config)
    - a Branch companion has no matching pick in `bundle_picks`
    - the pick references an option_id not present in the companion's
      options list
    - the matched BranchOption has no `child_template_id` (incomplete
      config)
    """
    picks = bundle_picks or {}
    planned: list[_PlannedChildV2] = []

    for companion in bundle_companions:
        if isinstance(companion, FixedCompanion):
            if not companion.child_template_id:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Fixed companion '{companion.label}' "
                        f"(id={companion.id}) has no child_template_id — "
                        "finish configuring it in the Companions modal "
                        "before drafting."
                    ),
                )
            planned.append(_PlannedChildV2(
                template_id=companion.child_template_id,
                companion_label=companion.label,
                slot_configurations=companion.slot_configurations,
            ))
            continue

        if isinstance(companion, BranchCompanion):
            pick_option_id = picks.get(companion.id)
            if pick_option_id is None:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Branch companion '{companion.label}' (id={companion.id}) "
                        f"requires a bundle pick — supply bundle_picks['{companion.id}'] "
                        f"with one of the option ids: "
                        f"{[o.id for o in companion.options]}"
                    ),
                )
            chosen = next(
                (o for o in companion.options if o.id == pick_option_id),
                None,
            )
            if chosen is None:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Branch companion '{companion.label}' (id={companion.id}) "
                        f"has no option with id '{pick_option_id}'. Valid option "
                        f"ids: {[o.id for o in companion.options]}"
                    ),
                )
            if not chosen.child_template_id:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Branch companion '{companion.label}' option "
                        f"'{chosen.option_label}' (id={chosen.id}) has no "
                        "child_template_id — finish configuring it in the "
                        "Companions modal before drafting."
                    ),
                )
            planned.append(_PlannedChildV2(
                template_id=chosen.child_template_id,
                companion_label=f"{companion.label} — {chosen.option_label}",
                slot_configurations=chosen.slot_configurations,
            ))
            continue

    return planned


async def run_bundle_v2(
    *,
    case: Any,
    parent_resolved_values: list[ResolvedTemplateValueV2],
    parent_filled_bytes: bytes,
    parent_config: TemplateConfigV2,
    bundle_picks: dict[str, str] | None,
    output_prefix: str,
) -> list[BundleChildRunV2]:
    """Resolve and finalize every scheduled child for a parent's bundle.

    The parent must have already finalized — `parent_resolved_values`
    and `parent_filled_bytes` are the outputs of its `finalize_run_v2`
    call. For each scheduled child:

    1. Load the child's `templates_v2` row. Hard-fail if missing /
       soft-deleted / not role=part_of_packet / has no fields
       configured.
    2. Re-validate the child's spec via
       `assert_part_of_packet_has_no_user_input_v2` (defense in depth
       — the save-time validator should have caught violators).
    3. Build a `ParentBundleContextV2` carrying the parent's resolved
       values + draft text + the companion's `slot_configurations`.
    4. Download the child's `template.docx` from R2.
    5. Run the child's pipeline against the same case (always
       `run_initial_stages_v2`, never resume — children can't pause).
    6. Hard-fail if the child surfaces `pending_inputs` (Phase 2
       invariant).
    7. Finalize the child's docx under `{output_prefix}/children/{template_id}/`.

    Returns the list of `BundleChildRunV2` in companion order.

    Children run in PARALLEL via `asyncio.gather` — they share no
    state, so concurrent extractor runs are safe.
    """
    if parent_config.role != TemplateRole.MASTER:
        return []
    if not parent_config.companions:
        return []

    planned = plan_bundle_v2(parent_config.companions, bundle_picks)
    if not planned:
        return []

    parent_resolved_map = {
        rv.template_variable: rv.value
        for rv in parent_resolved_values
        if rv.value
    }
    parent_draft_text = DocxTemplateService.extract_all_text(parent_filled_bytes)

    # All children run concurrently. asyncio.gather preserves input
    # order on the result list, so `children` ends up in the same
    # order as `planned` (and therefore as `parent_config.companions`).
    return await asyncio.gather(
        *(
            _resolve_and_finalize_child_v2(
                case=case,
                child_plan=child_plan,
                parent_resolved_map=parent_resolved_map,
                parent_draft_text=parent_draft_text,
                output_prefix=output_prefix,
            )
            for child_plan in planned
        )
    )


async def _resolve_and_finalize_child_v2(
    *,
    case: Any,
    child_plan: _PlannedChildV2,
    parent_resolved_map: dict[str, str],
    parent_draft_text: str,
    output_prefix: str,
) -> BundleChildRunV2:
    """Run one scheduled child end-to-end and return its
    `BundleChildRunV2`.

    Imports `TemplateFieldsV2Repository` locally to keep this module's
    import surface stable for tests that exercise the orchestration
    layer without DB access.
    """
    # Local import to avoid pulling DB models into orchestration
    # module-level imports (tests run faster when only the planning
    # path is exercised).
    from ..repositories import TemplateFieldsV2Repository

    child_row = await TemplatesV2Repository.get(child_plan.template_id)
    if child_row is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Child template '{child_plan.template_id}' referenced by "
                f"companion '{child_plan.companion_label}' was not found "
                "(or was soft-deleted)."
            ),
        )

    # Defense in depth — the save-time bundling-config validator and
    # the wizard's role-change flow should both have caught this, but
    # bundling is the load-bearing path so re-check.
    child_config = TemplateConfigV2.model_validate(child_row.config or {})
    if child_config.role != TemplateRole.PART_OF_PACKET:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Template '{child_plan.template_id}' referenced by companion "
                f"'{child_plan.companion_label}' has role='{child_config.role.value}'; "
                "only role='part_of_packet' templates may be bundled."
            ),
        )

    child_field_rows = await TemplateFieldsV2Repository.list_for_template(
        child_plan.template_id,
    )
    if not child_field_rows:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Child template '{child_plan.template_id}' has no fields "
                "configured; finish setup before bundling."
            ),
        )

    user_input_offenders = assert_part_of_packet_has_no_user_input_v2(
        child_field_rows,
    )
    if user_input_offenders:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "COMPANION_HAS_USER_INPUT",
                "child_template_id": child_plan.template_id,
                "offending_variables": user_input_offenders,
                "message": (
                    f"Companion template '{child_plan.template_id}' "
                    f"({child_plan.companion_label}) contains user-input "
                    f"variables: {', '.join(user_input_offenders)}. Phase 2 "
                    "invariant forbids user-input on companions — push the "
                    "variable up to the lead and inherit via a slot config."
                ),
            },
        )

    child_spec = _to_template_spec_v2(child_plan.template_id, child_field_rows)

    parent_context = ParentBundleContextV2(
        resolved_values=parent_resolved_map,
        draft_text=parent_draft_text,
        slot_configurations=dict(child_plan.slot_configurations),
    )

    child_template_bytes = await r2_service.download_file(
        template_id=child_plan.template_id,
        filename="template.docx",
        prefix="template_v2",
    )

    stages = await run_initial_stages_v2(
        spec=child_spec,
        case=case,
        parent_context=parent_context,
    )
    if stages.pending_inputs:
        # Phase 2 invariant violated — the save-time validator missed
        # something. Surface as a 500 with the offending variables so
        # the user knows where to fix it.
        raise HTTPException(
            status_code=500,
            detail={
                "code": "COMPANION_SURFACED_PENDING_INPUTS",
                "child_template_id": child_plan.template_id,
                "pending_variables": sorted(stages.pending_inputs.keys()),
                "message": (
                    f"Companion template '{child_plan.template_id}' "
                    f"({child_plan.companion_label}) surfaced user-input "
                    "pauses during a bundling run. Phase 2 forbids user-input "
                    "variables on companions — re-author the companion "
                    "without those fields."
                ),
            },
        )

    child_output_prefix = (
        f"{output_prefix}/children/{child_plan.template_id}/{uuid.uuid4()}"
    )
    finalized = await finalize_run_v2(
        template_id=child_plan.template_id,
        case_id=getattr(case, "id", ""),
        spec=child_spec,
        all_resolved=stages.all_resolved,
        template_bytes=child_template_bytes,
        output_prefix=child_output_prefix,
    )

    return BundleChildRunV2(
        template_id=str(child_plan.template_id),
        template_name=child_row.name,
        companion_label=child_plan.companion_label,
        finalized=finalized,
    )


def _to_template_spec_v2(
    template_id: str,
    field_rows: list[Any],
) -> TemplateSpecV2:
    """Build a `TemplateSpecV2` from `template_fields_v2` ORM rows.

    `field_rows[i].params` is JSONB (a dict) — re-validate through
    `WizardSourceParams.model_validate` so the pipeline sees the
    proper discriminated-union Pydantic shape, not a raw dict.
    """
    fields: list[TemplateFieldV2] = []
    for row in field_rows:
        raw_params = row.params
        params: WizardSourceParams | None
        if raw_params is None:
            params = None
        elif isinstance(raw_params, WizardSourceParams):
            params = raw_params
        else:
            try:
                params = WizardSourceParams.model_validate(raw_params)
            except Exception as err:  # noqa: BLE001
                logger.warning(
                    "_to_template_spec_v2: invalid params for variable %s "
                    "on template %s (%s); leaving params=None",
                    row.template_variable, template_id, err,
                )
                params = None
        fields.append(TemplateFieldV2(
            id=row.id,
            template_id=row.template_id,
            template_variable=row.template_variable,
            template_property_marker=row.template_property_marker,
            template_property_marker_aliases=(
                row.template_property_marker_aliases or []
            ),
            template_identifying_text_match=row.template_identifying_text_match,
            description=row.description,
            template_index=row.template_index or 0,
            params=params,
        ))
    return TemplateSpecV2(template_id=template_id, fields=fields)
