"""Template dry-run service — runs the full draft pipeline without persisting anything so the caller can iterate.

Two public operations, both returning either a fully-resolved DryRunResponse
or an AwaitingInputResponse when one or more user-input fields need picks:

    execute_dry_run(template_id, template_spec, case_id, bundle_picks)
        Build an in-memory AgentConfig from the candidate template_spec,
        run the shared initial-stages pipeline, and either pause (on
        user-input fields) or finalize the docx. When the parent
        template carries `bundle_companions`, also run the bundling
        engine after finalize to produce one filled docx per scheduled
        child.

    resume_dry_run(template_id, template_spec, case_id, resolved_values, user_picks, bundle_picks)
        Re-entered after a pause. Run the shared resume-stages pipeline
        (expand_picks + derivative), finalize the parent docx, then run
        the bundling engine for any companions on this template.

The resolver sequence + docx fill/upload tail for both flows lives in
`agents.orchestration` (pipeline + finalizer + bundling).
"""

import uuid

from fastapi import HTTPException
from pydantic import TypeAdapter, ValidationError

from src.core.agents.orchestration import (
    BundleChildRun,
    finalize_run,
    run_bundle,
    run_initial_stages,
    run_resume_stages,
)
from src.core.agents.resolvers.user_input_resolver import (
    AwaitingInputResponse,
    UserSelection,
)
from src.core.agents.types.bundling import BundleCompanion
from src.core.agents.types.resolution import ResolvedTemplateValue
from src.core.agents.types.spec import AgentConfig, TemplateVariable
from src.core.common.storage.database import DraftTemplateRepository
from src.core.common.storage.r2 import r2_service

from .composer import build_agent_config
from .schemas import BundleChildResult, DryRunResponse, DryRunValidation
from .validators import assert_child_only_has_no_user_input


async def execute_dry_run(
    template_id: str,
    template_spec: list[TemplateVariable],
    case_id: str,
    bundle_picks: dict[str, str] | None = None,
    candidate_bundle_role: str | None = None,
    candidate_bundle_companions: list | None = None,
) -> DryRunResponse | AwaitingInputResponse:
    """Run the full draft pipeline against a candidate template_spec without persisting; pause on USER_INPUT fields."""
    if not template_id:
        raise HTTPException(status_code=400, detail="template_id is required")

    persisted = await _load_and_assert_draftable(template_id)
    effective_role = candidate_bundle_role if candidate_bundle_role is not None else persisted.bundle_role
    if effective_role == "child_only":
        assert_child_only_has_no_user_input(template_id, template_spec)

    agent_config = await build_agent_config(template_id, template_spec)
    template_bytes = await _download_template_bytes(template_id)
    stages = await run_initial_stages(agent_config, case_id, template_bytes=template_bytes)

    if stages.pending_inputs:
        return AwaitingInputResponse(
            run_id=str(uuid.uuid4()),
            template_id=template_id,
            case_id=case_id,
            template_spec=template_spec,
            resolved_values=stages.all_resolved,
            pending_inputs=stages.pending_inputs,
            bundle_picks=bundle_picks,
        )

    bundle_companions = _resolve_bundle_companions(
        persisted=persisted,
        candidate_role=candidate_bundle_role,
        candidate_companions=candidate_bundle_companions,
    )
    return await _finalize_dry_run(
        template_id=template_id,
        case_id=case_id,
        agent_config=agent_config,
        all_resolved=stages.all_resolved,
        bundle_companions=bundle_companions,
        bundle_picks=bundle_picks,
        template_bytes=template_bytes,
    )


async def resume_dry_run(
    template_id: str,
    template_spec: list[TemplateVariable],
    case_id: str,
    resolved_values: list[ResolvedTemplateValue],
    user_picks: dict[str, UserSelection],
    bundle_picks: dict[str, str] | None = None,
    candidate_bundle_role: str | None = None,
    candidate_bundle_companions: list | None = None,
) -> DryRunResponse:
    """Resume a paused dry-run with the user's picks; finalize the docx and return the DryRunResponse."""
    if not template_id:
        raise HTTPException(status_code=400, detail="template_id is required")
    persisted = await _load_and_assert_draftable(template_id)
    effective_role = candidate_bundle_role if candidate_bundle_role is not None else persisted.bundle_role
    if effective_role == "child_only":
        assert_child_only_has_no_user_input(template_id, template_spec)

    agent_config = await build_agent_config(template_id, template_spec)
    all_resolved = await run_resume_stages(
        agent_config=agent_config,
        case_id=case_id,
        resolved_values=resolved_values,
        user_picks=user_picks,
    )

    bundle_companions = _resolve_bundle_companions(
        persisted=persisted,
        candidate_role=candidate_bundle_role,
        candidate_companions=candidate_bundle_companions,
    )
    return await _finalize_dry_run(
        template_id=template_id,
        case_id=case_id,
        agent_config=agent_config,
        all_resolved=all_resolved,
        bundle_companions=bundle_companions,
        bundle_picks=bundle_picks,
    )


async def _load_and_assert_draftable(template_id: str):
    """Load the template and validate it for dry-run; return the row.

    Existence-only check — child-only templates ARE allowed to dry-run
    against a case. Their `inherit_from_parent` slots resolve to fallback
    placeholders (or `[parent.slot.<name>]` markers), but the non-slot
    variables (court_drive lookups, system_generated, etc.) still
    resolve normally so the author can verify the rest of the template
    works without standing up a parent template + bundling. Production
    Run Draft remains blocked for child-only templates — see the
    `_load_committed_agent_config` guardrail in
    `components/engines/draft/service.py`.

    Returns the loaded DraftTemplate row so callers can inspect
    `bundle_role` for downstream constraint checks (e.g. the Phase 2
    "child_only templates may not contain user-input variables" rule).
    """
    draft_template = await DraftTemplateRepository.get(template_id)
    if not draft_template:
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found")
    return draft_template


def _resolve_bundle_companions(
    persisted,
    candidate_role: str | None,
    candidate_companions: list | None,
) -> list[BundleCompanion]:
    """Resolve the bundle_companions to use for this dry-run.

    Dry-run is supposed to validate the studio's IN-PROGRESS config —
    same iteration model as `template_spec`. When the FE supplies
    candidate values, we use them; otherwise fall back to whatever is
    persisted on the row. This lets authors test bundling changes
    without first hitting Save Configuration.

    Validation: candidate role must be 'parent' for bundling to apply
    (any other role yields an empty list); candidate_companions is
    parsed via TypeAdapter so a malformed candidate fails fast.
    """
    role = candidate_role if candidate_role is not None else persisted.bundle_role
    if role != "parent":
        return []

    raw = (
        candidate_companions
        if candidate_companions is not None
        else (persisted.bundle_companions or [])
    )
    if not raw:
        return []

    adapter = TypeAdapter(list[BundleCompanion])
    try:
        return adapter.validate_python(raw)
    except ValidationError as e:
        source = "candidate" if candidate_companions is not None else "persisted"
        raise HTTPException(
            status_code=400,
            detail=(
                f"{source.capitalize()} bundle_companions on template "
                f"'{persisted.id}' failed to load: {e.errors()}"
            ),
        )


async def _download_template_bytes(template_id: str) -> bytes:
    """Download the committed template.docx once so both run_initial_stages
    (web-search-enhance resolver) and finalize_run can share it."""
    return await r2_service.download_file(
        template_id=template_id,
        filename="template.docx",
        prefix="template",
    )


async def _finalize_dry_run(
    template_id: str,
    case_id: str,
    agent_config: AgentConfig,
    all_resolved: list[ResolvedTemplateValue],
    bundle_companions: list[BundleCompanion],
    bundle_picks: dict[str, str] | None,
    template_bytes: bytes | None = None,
) -> DryRunResponse:
    result = await finalize_run(
        template_id=template_id,
        case_id=case_id,
        agent_config=agent_config,
        all_resolved=all_resolved,
        output_prefix="dry_run",
        template_bytes=template_bytes,
    )

    children: list[BundleChildRun] = []
    if bundle_companions and result.filled_bytes:
        children = await run_bundle(
            case_id=case_id,
            parent_resolved_values=result.resolved_values,
            parent_filled_bytes=result.filled_bytes,
            bundle_companions=bundle_companions,
            bundle_picks=bundle_picks,
            output_prefix="dry_run",
        )

    return DryRunResponse(
        template_id=template_id,
        resolved_values=result.resolved_values,
        generated_doc_url=result.generated_doc_url,
        validation=DryRunValidation(valid=True, errors=[], warnings=result.warnings),
        can_generate=len(result.unresolved) == 0,
        children=[
            BundleChildResult(
                template_id=c.template_id,
                template_name=c.template_name,
                companion_label=c.companion_label,
                generated_doc_url=c.finalized.generated_doc_url,
                resolved_values=c.finalized.resolved_values,
                warnings=c.finalized.warnings,
            )
            for c in children
        ],
    )
