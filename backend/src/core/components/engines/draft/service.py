"""Draft-flow service — loads the committed AgentConfig and runs the shared pipeline.

Exposes two entry points: `execute_draft_for_case` kicks off a new run (may
pause on USER_INPUT-stage fields), and `resume_draft` finishes a paused run
using the user's picks. Both delegate the resolver sequence + fill/upload
tail to `agents.orchestration` (pipeline + finalizer + bundling).

Parents that carry `bundle_companions` also run the bundling engine
after their parent docx finalizes — produces one filled docx per
scheduled child, returned alongside the parent's docx URL.
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
from src.core.agents.types.spec import AgentConfig
from src.core.common.storage.database import DraftTemplateRepository
from src.core.common.storage.r2 import r2_service

from .schemas import DraftChildResult, DraftResponse, DraftValidation


async def execute_draft_for_case(
    template_id: str,
    case_id: str,
    bundle_picks: dict[str, str] | None = None,
) -> DraftResponse | AwaitingInputResponse:
    """Start a draft run for a committed template against a case; pause on USER_INPUT fields via AwaitingInputResponse."""
    if not template_id:
        raise HTTPException(status_code=400, detail="template_id is required")
    if not case_id:
        raise HTTPException(status_code=400, detail="case_id is required")

    persisted, agent_config = await _load_committed(template_id)
    template_bytes = await _download_template_bytes(template_id)
    stages = await run_initial_stages(agent_config, case_id, template_bytes=template_bytes)

    if stages.pending_inputs:
        return AwaitingInputResponse(
            run_id=str(uuid.uuid4()),
            template_id=template_id,
            case_id=case_id,
            template_spec=None,
            resolved_values=stages.all_resolved,
            pending_inputs=stages.pending_inputs,
            bundle_picks=bundle_picks,
        )

    bundle_companions = _load_bundle_companions(persisted)
    return await _finalize_draft(
        template_id=template_id,
        case_id=case_id,
        agent_config=agent_config,
        all_resolved=stages.all_resolved,
        bundle_companions=bundle_companions,
        bundle_picks=bundle_picks,
        template_bytes=template_bytes,
    )


async def resume_draft(
    template_id: str,
    case_id: str,
    resolved_values: list[ResolvedTemplateValue],
    user_picks: dict[str, UserSelection],
    bundle_picks: dict[str, str] | None = None,
) -> DraftResponse:
    """Resume a paused draft run with the user's picks; finalize the docx and return the DraftResponse."""
    if not template_id:
        raise HTTPException(status_code=400, detail="template_id is required")
    if not case_id:
        raise HTTPException(status_code=400, detail="case_id is required")

    persisted, agent_config = await _load_committed(template_id)
    all_resolved = await run_resume_stages(
        agent_config=agent_config,
        case_id=case_id,
        resolved_values=resolved_values,
        user_picks=user_picks,
    )

    bundle_companions = _load_bundle_companions(persisted)
    return await _finalize_draft(
        template_id=template_id,
        case_id=case_id,
        agent_config=agent_config,
        all_resolved=all_resolved,
        bundle_companions=bundle_companions,
        bundle_picks=bundle_picks,
    )


async def _load_committed(template_id: str) -> tuple[object, AgentConfig]:
    draft_template = await DraftTemplateRepository.get(template_id)
    if not draft_template:
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found")
    if draft_template.bundle_role == "child_only":
        raise HTTPException(
            status_code=400,
            detail=(
                f"Template '{template_id}' is child-only and cannot be drafted "
                "directly. Invoke it via a parent template's bundle companion."
            ),
        )
    if not draft_template.agent_config:
        raise HTTPException(
            status_code=400,
            detail=f"Template {template_id} has no committed agent config. Run compose-agent-config first.",
        )
    return draft_template, AgentConfig(**draft_template.agent_config)


def _load_bundle_companions(persisted) -> list[BundleCompanion]:
    """Coerce the persisted JSONB into typed BundleCompanion models. Empty
    list for non-parent templates or parents with no companions."""
    if persisted.bundle_role != "parent":
        return []
    raw = persisted.bundle_companions or []
    if not raw:
        return []
    try:
        adapter = TypeAdapter(list[BundleCompanion])
        return adapter.validate_python(raw)
    except ValidationError as e:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Persisted bundle_companions on template '{persisted.id}' "
                f"failed to load: {e.errors()}"
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


async def _finalize_draft(
    template_id: str,
    case_id: str,
    agent_config: AgentConfig,
    all_resolved: list[ResolvedTemplateValue],
    bundle_companions: list[BundleCompanion],
    bundle_picks: dict[str, str] | None,
    template_bytes: bytes | None = None,
) -> DraftResponse:
    result = await finalize_run(
        template_id=template_id,
        case_id=case_id,
        agent_config=agent_config,
        all_resolved=all_resolved,
        output_prefix="draft",
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
            output_prefix="draft",
        )

    return DraftResponse(
        template_id=template_id,
        case_id=case_id,
        resolved_values=result.resolved_values,
        generated_doc_url=result.generated_doc_url,
        r2_object_key=result.r2_object_key,
        validation=DraftValidation(valid=True, errors=[], warnings=result.warnings),
        children=[
            DraftChildResult(
                template_id=c.template_id,
                template_name=c.template_name,
                companion_label=c.companion_label,
                generated_doc_url=c.finalized.generated_doc_url,
                r2_object_key=c.finalized.r2_object_key,
                resolved_values=c.finalized.resolved_values,
                warnings=c.finalized.warnings,
            )
            for c in children
        ],
    )
