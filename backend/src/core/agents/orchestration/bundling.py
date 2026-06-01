"""Bundling engine — schedules + resolves + finalizes a parent's child companions.

Called by the dry-run and draft services AFTER the parent has fully
resolved and finalized its docx. Walks the parent's `bundle_companions`,
resolves each scheduled child against the same case (slot variables fill
from `ParentBundleContext`, non-slot variables resolve normally), and
returns a list of `BundleChildRun` results — one per produced child docx.

Phase 2 constraint (enforced by `assert_child_only_has_no_user_input` at
save time): child templates may not contain user-input variables. The
bundling engine relies on this — children resolve straight-through, no
nested AwaitingInputResponse pause across N children. If a child does
surface a pending input here it indicates the validator was bypassed,
and we surface the situation as a hard error rather than silently
returning a partially-resolved child.
"""

import logging
import uuid

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict

from src.core.agents.types.bundling import (
    BranchBundleCompanion,
    BundleCompanion,
    FixedBundleCompanion,
    ParentBundleContext,
    SlotConfig,
)
from src.core.agents.types.resolution import ResolvedTemplateValue
from src.core.agents.types.spec import AgentConfig, TemplateVariable
from src.core.common.documents.docx_template import DocxTemplateService
from src.core.common.storage.database import DraftTemplateRepository
from src.core.common.storage.r2 import r2_service

from .finalizer import FinalizedRun, finalize_run
from .pipeline import run_initial_stages

logger = logging.getLogger(__name__)


class BundleChildRun(BaseModel):
    """One scheduled child's finalized output, returned to the caller."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    template_id: str
    template_name: str
    companion_label: str
    finalized: FinalizedRun


class _PlannedChild(BaseModel):
    """Internal — one scheduled child with everything needed to run it."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    template_id: str
    companion_label: str
    slot_configurations: dict[str, SlotConfig]


def plan_bundle(
    bundle_companions: list[BundleCompanion],
    bundle_picks: dict[str, str] | None,
) -> list[_PlannedChild]:
    """Walk the parent's companions and resolve each one to a scheduled child.

    Fixed companions always schedule. Branch companions look up the
    user's pre-flight pick (by stringified companion index) and schedule
    the matching `BranchOption`.

    Raises HTTPException(400) when:
      - a branch companion has no matching pick in `bundle_picks`,
      - the pick references a label not present in the companion's options.
    """
    picks = bundle_picks or {}
    planned: list[_PlannedChild] = []

    for idx, companion in enumerate(bundle_companions):
        if isinstance(companion, FixedBundleCompanion):
            planned.append(_PlannedChild(
                template_id=companion.child_template_id,
                companion_label=companion.label,
                slot_configurations=companion.slot_configurations,
            ))
            continue

        if isinstance(companion, BranchBundleCompanion):
            pick_label = picks.get(str(idx))
            if pick_label is None:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Branch companion '{companion.label}' (index {idx}) "
                        f"requires a bundle pick — supply bundle_picks['{idx}'] "
                        f"with one of: {[o.label for o in companion.options]}"
                    ),
                )
            chosen = next((o for o in companion.options if o.label == pick_label), None)
            if chosen is None:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Branch companion '{companion.label}' (index {idx}) "
                        f"has no option labelled '{pick_label}'. Valid options: "
                        f"{[o.label for o in companion.options]}"
                    ),
                )
            planned.append(_PlannedChild(
                template_id=chosen.child_template_id,
                companion_label=f"{companion.label} — {chosen.label}",
                slot_configurations=chosen.slot_configurations,
            ))
            continue

    return planned


async def run_bundle(
    case_id: str,
    parent_resolved_values: list[ResolvedTemplateValue],
    parent_filled_bytes: bytes,
    bundle_companions: list[BundleCompanion],
    bundle_picks: dict[str, str] | None,
    output_prefix: str,
) -> list[BundleChildRun]:
    """Resolve and finalize every scheduled child for a parent's bundle.

    The parent must have already finalized — `parent_resolved_values` and
    `parent_filled_bytes` are the outputs of its `finalize_run` call.
    For each scheduled child:

      1. Load the child's persisted DraftTemplate row.
      2. Compose an in-memory AgentConfig from its persisted template_spec
         (children persist template_spec; agent_config is parent-only).
      3. Build a ParentBundleContext carrying the parent's resolved
         values + draft text + the companion's slot_configurations.
      4. Run the child's pipeline against the same case_id.
      5. Hard-fail if the child surfaces pending_inputs (Phase 2
         constraint violation; the save-time validator should have
         caught it).
      6. Finalize the child's docx under `<output_prefix>/children/`
         and append the result.

    Returns the list of `BundleChildRun` in companion order.
    """
    if not bundle_companions:
        return []

    parent_resolved_map = {
        rv.property_name: rv.value
        for rv in parent_resolved_values
        if rv.value
    }
    parent_draft_text = DocxTemplateService.extract_all_text(parent_filled_bytes)

    planned = plan_bundle(bundle_companions, bundle_picks)
    if not planned:
        return []

    children: list[BundleChildRun] = []
    for child_plan in planned:
        children.append(
            await _resolve_and_finalize_child(
                case_id=case_id,
                child_plan=child_plan,
                parent_resolved_map=parent_resolved_map,
                parent_draft_text=parent_draft_text,
                output_prefix=output_prefix,
            )
        )
    return children


async def _resolve_and_finalize_child(
    case_id: str,
    child_plan: _PlannedChild,
    parent_resolved_map: dict[str, str],
    parent_draft_text: str,
    output_prefix: str,
) -> BundleChildRun:
    child_row = await DraftTemplateRepository.get(child_plan.template_id)
    if not child_row:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Child template '{child_plan.template_id}' referenced by "
                f"companion '{child_plan.companion_label}' was not found."
            ),
        )
    if child_row.bundle_role != "child_only":
        raise HTTPException(
            status_code=400,
            detail=(
                f"Template '{child_plan.template_id}' referenced by companion "
                f"'{child_plan.companion_label}' has bundle_role="
                f"'{child_row.bundle_role}'; only 'child_only' templates may "
                "be bundled."
            ),
        )
    if not child_row.template_spec:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Child template '{child_plan.template_id}' has no template_spec; "
                "complete its variable configuration before bundling."
            ),
        )

    child_template_spec = [TemplateVariable(**v) for v in child_row.template_spec]

    # Local import — avoids a circular dependency between orchestration
    # (this module) and components.engines.template.composer (which
    # imports from agents.orchestration).
    from src.core.components.engines.template.composer import build_agent_config

    child_agent_config: AgentConfig = await build_agent_config(
        child_plan.template_id,
        child_template_spec,
    )

    parent_context = ParentBundleContext(
        resolved_values=parent_resolved_map,
        draft_text=parent_draft_text,
        slot_configurations=child_plan.slot_configurations,
    )

    child_template_bytes = await r2_service.download_file(
        template_id=child_plan.template_id,
        filename="template.docx",
        prefix="template",
    )

    stages = await run_initial_stages(
        agent_config=child_agent_config,
        case_id=case_id,
        template_bytes=child_template_bytes,
        parent_context=parent_context,
    )
    if stages.pending_inputs:
        # Phase 2 constraint guarantees children have no user-input
        # variables. Hitting this branch means the save-time validator
        # was bypassed somehow — surface as a clear error so the user
        # knows where to fix it.
        raise HTTPException(
            status_code=500,
            detail=(
                f"Child template '{child_plan.template_id}' surfaced "
                "user-input pauses during a bundling run. Phase 2 forbids "
                "user-input variables on child_only templates — re-author "
                "the child without user-input fields."
            ),
        )

    child_output_prefix = f"{output_prefix}/children/{child_plan.template_id}/{uuid.uuid4()}"
    finalized = await finalize_run(
        template_id=child_plan.template_id,
        case_id=case_id,
        agent_config=child_agent_config,
        all_resolved=stages.all_resolved,
        output_prefix=child_output_prefix,
        template_bytes=child_template_bytes,
    )

    return BundleChildRun(
        template_id=child_plan.template_id,
        template_name=child_row.name,
        companion_label=child_plan.companion_label,
        finalized=finalized,
    )
