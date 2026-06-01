"""Dry-run endpoints — POST /api/v3/studio/templates/{id}/dry-run +
POST /api/v3/studio/templates/{id}/dry-run/resume.

Thin wrappers over `studio_v2.services.dry_run.service`:
- Validate the path `template_id` matches the body.
- Wrap the call in `cost_attribution(semantic_id_kind="pleading_run_v2")`
  so v2 dry-run LLM spend lands in its own bucket distinct from v1's
  `pleading_run`. A synthetic per-request UUID becomes the
  `semantic_id` so `COUNT(DISTINCT semantic_id)` correctly counts each
  dry-run as one "run" in the Costs dashboard's avg-per-run breakdown.
- Both pre-pause and resume share the SAME bucket — total cost rolls
  up per dry-run regardless of how many user-input rounds.

Server is stateless: every input comes from the FE on every call.
The pipeline orchestrator owns the partial-state shuttling between
pause and resume.
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException

from src.auth.auth import get_current_user_optional
from src.auth.models import User
from src.core.common.cost_tracking import cost_attribution

from ..services.dry_run import execute_dry_run_v2, resume_dry_run_v2
from ..services.dry_run.schemas import DryRunRequestV2, DryRunResumeRequestV2
from ..types.orchestration import (
    AwaitingInputResponseV2,
    DryRunResponseV2,
)

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/studio", tags=["Studio V2 - Dry-run"])


# Cost-attribution bucket for v2 dry-run. The Costs dashboard's
# Pleadings card filters v1 spend on `semantic_id_kind = 'pleading_run'`;
# v2 uses this distinct label so the dashboard can break out v2 spend
# independently (and so v1's panel isn't polluted by v2 LLM cost rows).
_COST_KIND_V2 = "pleading_run_v2"


@router.post(
    "/templates/{template_id}/dry-run",
    response_model=DryRunResponseV2 | AwaitingInputResponseV2,
)
async def dry_run(
    template_id: str,
    request: DryRunRequestV2,
    current_user: Annotated[Optional[User], Depends(get_current_user_optional)] = None,
):
    """Verify a candidate template spec end-to-end against a real case
    without persisting anything.

    Returns `DryRunResponseV2` on completion OR
    `AwaitingInputResponseV2` when one or more user-input fields need
    a paralegal pick. In the pending case the FE presents the
    envelopes (dropdown / chip / multi-select / author-text /
    author-date / author-docs / attorney-pick) and POSTs to
    /dry-run/resume with the original inputs + resolved_values +
    pending_inputs + user_picks to finish.

    The body's `template_spec` overrides any persisted spec — same
    iteration model as the wizard's working draft. Candidate
    `bundle_role` / `bundle_companions` likewise override persisted
    values so authors can test bundling changes without first publishing.
    """
    _assert_template_id_matches(template_id, request.template_id)

    dry_run_id = str(uuid.uuid4())
    with cost_attribution(
        firm_id=getattr(current_user, "firm_id", None) if current_user else None,
        user_id=getattr(current_user, "id", None) if current_user else None,
        case_id=request.case_id,
        semantic_id=dry_run_id,
        semantic_id_kind=_COST_KIND_V2,
    ):
        return await execute_dry_run_v2(
            template_id=request.template_id,
            template_spec=request.template_spec,
            case_id=request.case_id,
            bundle_picks=request.bundle_picks,
            candidate_bundle_role=request.bundle_role,
            candidate_bundle_companions=request.bundle_companions,
        )


@router.post(
    "/templates/{template_id}/dry-run/resume",
    response_model=DryRunResponseV2,
)
async def dry_run_resume(
    template_id: str,
    request: DryRunResumeRequestV2,
    current_user: Annotated[Optional[User], Depends(get_current_user_optional)] = None,
):
    """Resume a dry-run that returned `AwaitingInputResponseV2`.

    The server is stateless — the FE re-sends:
    - `template_spec` (verbatim from the prior call)
    - `resolved_values` (verbatim from the prior `AwaitingInputResponseV2`)
    - `pending_inputs` (verbatim — `expand_picks_v2` reads each
      envelope to look up per-option `raw_context` for derived children)
    - `user_picks` (the paralegal's selections)
    - `bundle_picks` / `bundle_role` / `bundle_companions` (echoed)

    `expand_picks_v2` validates the picks, the wave-B + late
    auto-derive passes run, finalize fills the docx, and bundling fans
    out the companions if the template is a lead.

    Resume costs roll into the SAME `pleading_run_v2` semantic_id_kind
    bucket as the initial /dry-run — a new run_id is minted so the
    Costs panel counts the resume call as part of the same dry-run
    invocation for COUNT(DISTINCT semantic_id) aggregations.
    """
    _assert_template_id_matches(template_id, request.template_id)

    dry_run_id = str(uuid.uuid4())
    with cost_attribution(
        firm_id=getattr(current_user, "firm_id", None) if current_user else None,
        user_id=getattr(current_user, "id", None) if current_user else None,
        case_id=request.case_id,
        semantic_id=dry_run_id,
        semantic_id_kind=_COST_KIND_V2,
    ):
        # The dry-run service typed-validates pending_inputs as
        # PendingUserInputV2 instances; we pass the raw dict through
        # and let Pydantic discriminate by `kind`.
        return await resume_dry_run_v2(
            template_id=request.template_id,
            template_spec=request.template_spec,
            case_id=request.case_id,
            resolved_values=request.resolved_values,
            user_picks=request.user_picks,
            pending_inputs=_validate_pending_inputs(request.pending_inputs),
            bundle_picks=request.bundle_picks,
            candidate_bundle_role=request.bundle_role,
            candidate_bundle_companions=request.bundle_companions,
        )


def _assert_template_id_matches(path_id: str, body_id: str) -> None:
    """Reject the request when the URL path and body disagree on
    `template_id`. Catches FE bugs early — both are required and they
    must match."""
    if not body_id:
        raise HTTPException(
            status_code=400,
            detail="request body is missing template_id",
        )
    if path_id != body_id:
        raise HTTPException(
            status_code=400,
            detail=(
                f"template_id mismatch: path={path_id!r}, body={body_id!r}"
            ),
        )


def _validate_pending_inputs(raw):
    """Convert the resume request's pending_inputs dict (raw JSON) into
    the discriminated-union Pydantic shape the orchestrator expects.

    Returns `None` when `raw` is None — the orchestrator treats absent
    pending_inputs as "no raw_context info available; fall back to
    pick value for derived children".
    """
    if raw is None:
        return None
    # Local import keeps the module import surface lean.
    from pydantic import TypeAdapter
    from ..types.pending import PendingUserInputV2

    adapter = TypeAdapter(dict[str, PendingUserInputV2])
    try:
        return adapter.validate_python(raw)
    except Exception as err:  # noqa: BLE001
        raise HTTPException(
            status_code=400,
            detail=f"pending_inputs failed to validate: {err}",
        )
