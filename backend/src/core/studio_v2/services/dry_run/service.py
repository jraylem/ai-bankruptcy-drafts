"""v2 dry-run service — runs the full pipeline against a candidate
spec without persisting anything.

Mirrors v1's `execute_dry_run` / `resume_dry_run` shape but uses the
v2 namespace end-to-end:
- `TemplateSpecV2` (NOT v1's TemplateVariable list)
- `run_initial_stages_v2` / `run_resume_stages_v2` / `finalize_run_v2`
- `run_bundle_v2` for companion fanout
- `BundleChildRunV2` carried on the DryRunResponseV2

Stateless: every call validates inputs, loads the case + downloads
the template.docx fresh, runs the pipeline, and returns. No session
table, no Redis row, no run_id-keyed state.

Bundling iteration model (matches v1 + the plan): when the FE sends
candidate `bundle_role` / `bundle_companions`, the dry-run uses those
instead of the persisted `TemplateConfigV2`. Lets the paralegal test
bundling changes without first publishing.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import HTTPException
from pydantic import TypeAdapter, ValidationError

from src.core.common.storage.database import CaseRepository
from src.core.common.storage.r2 import r2_service

from ...orchestration import (
    finalize_run_v2,
    plan_bundle_v2,  # noqa: F401  (re-exported via __init__ for tests)
    run_bundle_v2,
    run_initial_stages_v2,
    run_resume_stages_v2,
)
from ...repositories import TemplatesV2Repository
from ...types.bundling import (
    BundleCompanion,
    TemplateConfigV2,
    TemplateRole,
)
from ...types.fields import TemplateSpecV2
from ...types.orchestration import (
    AwaitingInputResponseV2,
    BundleChildRunV2,
    DryRunResponseV2,
    FinalizedRunV2,
)
from ...types.pending import PendingUserInputV2
from ...types.picks import UserSelectionV2
from ...types.resolution import ResolvedTemplateValueV2

logger = logging.getLogger(__name__)


# R2 layout: cases/{case_id}/dry_run/{uuid}.docx (per plan).
_DRY_RUN_OUTPUT_PREFIX = "dry_run"


async def execute_dry_run_v2(
    *,
    template_id: str,
    template_spec: TemplateSpecV2,
    case_id: str,
    bundle_picks: dict[str, str] | None = None,
    candidate_bundle_role: str | None = None,
    candidate_bundle_companions: list[dict[str, Any]] | None = None,
) -> DryRunResponseV2 | AwaitingInputResponseV2:
    """Run the v2 pipeline against `template_spec` and finalize a
    dry-run docx — or pause with `AwaitingInputResponseV2` when any
    user-input field needs a pick.

    Args:
        template_id: persisted templates_v2.id (used for R2 paths +
            persisted bundling fallback).
        template_spec: candidate spec from the FE (NOT loaded from DB).
        case_id: cases.id to resolve against.
        bundle_picks: pre-flight branch picks keyed by companion.id.
        candidate_bundle_role: candidate role override (else persisted).
        candidate_bundle_companions: candidate companions override
            (else persisted).
    """
    _require(template_id, "template_id is required")
    _require(case_id, "case_id is required")

    persisted = await _load_template(template_id)
    case = await _load_case(case_id)
    template_bytes = await _download_template_bytes(template_id)

    stages = await run_initial_stages_v2(
        spec=template_spec,
        case=case,
    )

    if stages.pending_inputs:
        return AwaitingInputResponseV2(
            run_id=str(uuid.uuid4()),
            template_id=template_id,
            case_id=case_id,
            template_spec=template_spec,
            resolved_values=stages.all_resolved,
            pending_inputs=stages.pending_inputs,
            bundle_picks=bundle_picks,
        )

    return await _finalize_and_bundle(
        template_id=template_id,
        case=case,
        case_id=case_id,
        spec=template_spec,
        all_resolved=stages.all_resolved,
        template_bytes=template_bytes,
        persisted_config=_persisted_config(persisted),
        candidate_role=candidate_bundle_role,
        candidate_companions=candidate_bundle_companions,
        bundle_picks=bundle_picks,
    )


async def resume_dry_run_v2(
    *,
    template_id: str,
    template_spec: TemplateSpecV2,
    case_id: str,
    resolved_values: list[ResolvedTemplateValueV2],
    user_picks: dict[str, UserSelectionV2],
    pending_inputs: dict[str, PendingUserInputV2] | None = None,
    bundle_picks: dict[str, str] | None = None,
    candidate_bundle_role: str | None = None,
    candidate_bundle_companions: list[dict[str, Any]] | None = None,
) -> DryRunResponseV2:
    """Resume a paused dry-run with the paralegal's picks and finalize.

    The server is stateless — every input here comes from the FE's
    prior call response.
    """
    _require(template_id, "template_id is required")
    _require(case_id, "case_id is required")

    persisted = await _load_template(template_id)
    case = await _load_case(case_id)
    template_bytes = await _download_template_bytes(template_id)

    all_resolved = await run_resume_stages_v2(
        spec=template_spec,
        case=case,
        resolved_values=resolved_values,
        user_picks=user_picks,
        pending_inputs=pending_inputs,
    )

    return await _finalize_and_bundle(
        template_id=template_id,
        case=case,
        case_id=case_id,
        spec=template_spec,
        all_resolved=all_resolved,
        template_bytes=template_bytes,
        persisted_config=_persisted_config(persisted),
        candidate_role=candidate_bundle_role,
        candidate_companions=candidate_bundle_companions,
        bundle_picks=bundle_picks,
    )


# ─── helpers ─────────────────────────────────────────────────────────


def _require(value: str | None, msg: str) -> None:
    if not value:
        raise HTTPException(status_code=400, detail=msg)


async def _load_template(template_id: str) -> Any:
    """Load the persisted templates_v2 row — needed even though the
    spec comes from the body because the DB row carries the persisted
    `config` (role + companions) that the bundling-iteration model
    falls back to when the FE doesn't supply overrides."""
    row = await TemplatesV2Repository.get(template_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Template {template_id} not found (or soft-deleted)",
        )
    return row


async def _load_case(case_id: str) -> Any:
    """Load the cases row — required for the orchestrator's toolset
    construction (Gmail OAuth context, case_file_collection,
    petition_pdf_url, etc.)."""
    case = await CaseRepository.get(case_id)
    if case is None:
        raise HTTPException(
            status_code=404,
            detail=f"Case {case_id} not found",
        )
    return case


async def _download_template_bytes(template_id: str) -> bytes:
    """Download the placeholder-marked template.docx once so initial
    stages + finalize_run_v2 + bundling share it."""
    return await r2_service.download_file(
        template_id=template_id,
        filename="template.docx",
        prefix="template_v2",
    )


def _persisted_config(row: Any) -> TemplateConfigV2:
    """Parse the persisted `config` JSON into a `TemplateConfigV2`.

    Defaults to `role=SINGLE` when the column is empty (legacy rows
    or freshly-uploaded templates that never hit the bundling-config
    save endpoint).
    """
    raw = getattr(row, "config", None) or {}
    try:
        return TemplateConfigV2.model_validate(raw)
    except ValidationError as err:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Template {getattr(row, 'id', '?')} has invalid persisted "
                f"config: {err.errors()}"
            ),
        )


def _resolve_bundling_config(
    *,
    persisted_config: TemplateConfigV2,
    candidate_role: str | None,
    candidate_companions: list[dict[str, Any]] | None,
) -> TemplateConfigV2:
    """Same iteration model as v1: candidate overrides win; persisted
    is the fallback.

    Validation: `candidate_companions` is parsed via Pydantic's
    `TypeAdapter` so a malformed candidate fails with a clear 400
    instead of bombing inside the bundling engine.
    """
    role_value = candidate_role if candidate_role is not None else persisted_config.role
    try:
        role = TemplateRole(role_value) if not isinstance(role_value, TemplateRole) else role_value
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid bundle_role: {candidate_role!r}",
        )

    if role != TemplateRole.MASTER:
        return TemplateConfigV2(role=role, companions=[])

    raw_companions = (
        candidate_companions
        if candidate_companions is not None
        else [c.model_dump(mode="json") for c in persisted_config.companions]
    )
    if not raw_companions:
        return TemplateConfigV2(role=role, companions=[])

    try:
        companions = TypeAdapter(list[BundleCompanion]).validate_python(raw_companions)
    except ValidationError as err:
        source = "candidate" if candidate_companions is not None else "persisted"
        raise HTTPException(
            status_code=400,
            detail=(
                f"{source.capitalize()} bundle_companions failed to load: "
                f"{err.errors()}"
            ),
        )
    return TemplateConfigV2(role=role, companions=companions)


async def _finalize_and_bundle(
    *,
    template_id: str,
    case: Any,
    case_id: str,
    spec: TemplateSpecV2,
    all_resolved: list[ResolvedTemplateValueV2],
    template_bytes: bytes,
    persisted_config: TemplateConfigV2,
    candidate_role: str | None,
    candidate_companions: list[dict[str, Any]] | None,
    bundle_picks: dict[str, str] | None,
) -> DryRunResponseV2:
    """Finalize the parent docx, then run the bundling engine for any
    companions on the effective config, and assemble the
    `DryRunResponseV2`."""
    finalized: FinalizedRunV2 = await finalize_run_v2(
        template_id=template_id,
        case_id=case_id,
        spec=spec,
        all_resolved=all_resolved,
        template_bytes=template_bytes,
        output_prefix=_DRY_RUN_OUTPUT_PREFIX,
    )

    effective_config = _resolve_bundling_config(
        persisted_config=persisted_config,
        candidate_role=candidate_role,
        candidate_companions=candidate_companions,
    )

    children: list[BundleChildRunV2] = []
    if (
        effective_config.role == TemplateRole.MASTER
        and effective_config.companions
        and finalized.filled_bytes
    ):
        children = await run_bundle_v2(
            case=case,
            parent_resolved_values=finalized.resolved_values,
            parent_filled_bytes=finalized.filled_bytes,
            parent_config=effective_config,
            bundle_picks=bundle_picks,
            output_prefix=_DRY_RUN_OUTPUT_PREFIX,
        )

    return DryRunResponseV2(
        run_id=str(uuid.uuid4()),
        template_id=template_id,
        case_id=case_id,
        resolved_values=finalized.resolved_values,
        generated_doc_url=finalized.generated_doc_url,
        r2_object_key=finalized.r2_object_key,
        unresolved=finalized.unresolved,
        warnings=finalized.warnings,
        grammar_repairs=finalized.grammar_repairs,
        children=children,
    )
