"""HTTP routes for the /template endpoints — composer flow (parse / generate / regenerate / compose-agent-config), dry-run, and connector registry."""

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile

from src.auth.auth import get_current_user_optional
from src.auth.models import User
from src.core.agents.resolvers.user_input_resolver import AwaitingInputResponse
from src.core.agents.types.spec import AgentConfig, TemplateVariable
from src.core.common.connectors import CONNECTORS, Connector
from src.core.common.cost_tracking import cost_attribution

from ...reference_data.router import router as reference_data_router
from .schemas import (
    BundlingConfigUpdateRequest,
    DeleteTemplateResponse,
    DocumentParseResponse,
    DraftTemplateResponse,
    DraftTemplateUpdateRequest,
    DryRunRequest,
    DryRunResponse,
    DryRunResumeRequest,
    TemplateGenerateResponse,
    TemplateRegenerateRequest,
)
from .composer import compose_agent_config, generate_template, parse_document, regenerate_template
from .crud import (
    delete_template_by_id,
    list_template_responses,
    update_template_bundling_config,
    update_template_name,
)
from .dry_run import execute_dry_run, resume_dry_run

router = APIRouter(prefix="/template")
router.include_router(reference_data_router)


# ─── Template CRUD ───


@router.get("", response_model=list[DraftTemplateResponse])
async def list_templates():
    """List all active draft templates with fresh pre-signed URLs."""
    return await list_template_responses()


@router.put("/{template_id}", response_model=DraftTemplateResponse)
async def update_template(template_id: str, data: DraftTemplateUpdateRequest):
    """Update a draft template's name."""
    return await update_template_name(template_id, data.name)


@router.put("/{template_id}/bundling-config", response_model=DraftTemplateResponse)
async def update_template_bundling(
    template_id: str,
    data: BundlingConfigUpdateRequest,
):
    """Update a template's bundle_role + bundle_companions (the bundling tab)."""
    return await update_template_bundling_config(
        template_id,
        data.bundle_role,
        data.bundle_companions,
    )


@router.delete("/{template_id}", response_model=DeleteTemplateResponse)
async def delete_template(
    template_id: str,
    force: bool = Query(
        False,
        description=(
            "When false (default), the endpoint scans for other active "
            "parent templates whose bundle_companions reference this "
            "template; if any are found, returns 409 with the list. When "
            "true, those parents' bundle_companions are cascade-cleaned "
            "before this template is soft-deleted."
        ),
    ),
):
    """Soft-delete a draft template by ID. See `force` for the cascade behavior."""
    return await delete_template_by_id(template_id, force=force)


# ─── Connectors ───


@router.get(
    "/connectors",
    response_model=list[Connector],
    response_model_exclude_none=True,
    response_model_by_alias=True,
)
async def get_connectors():
    """Return list of available source connectors and their parameter requirements."""
    return CONNECTORS


# ─── Composer ───


@router.post("/composer/parse", response_model=DocumentParseResponse)
async def composer_parse_document(document: UploadFile = File(...)):
    """Step 1: Parse a docx document and extract its content.

    Returns the parsed content that can be used for analysis.
    """
    file_content = await document.read()
    return await parse_document(document.filename or "uploaded_doc", file_content)


@router.post("/composer/generate-template", response_model=TemplateGenerateResponse)
async def composer_generate_template(
    template_name: str,
    document: UploadFile = File(...),
    current_user: Annotated[Optional[User], Depends(get_current_user_optional)] = None,
):
    """Step 2: Upload a docx document and generate template specification.

    1. Parses the uploaded document
    2. Feeds parsed content to LLM
    3. LLM analyzes and outputs template variables
    4. Uploads original document to R2: {template_id}/original.docx
    5. Creates and uploads template document to R2: {template_id}/template.docx

    The actual template_id is generated INSIDE `generate_template` (it
    needs it to compute R2 keys before the row exists), so the scope here
    uses a synthetic per-request UUID. The real template_id won't match
    in llm_cost_logs for these rows, but `semantic_id_kind='template'` is
    what the future Template-authoring workflow card filters on — so the
    rows roll up correctly even if per-template breakdown lags.
    """
    file_content = await document.read()
    parsed_document = await parse_document(document.filename or "uploaded_doc", file_content)
    with cost_attribution(
        firm_id=getattr(current_user, "firm_id", None) if current_user else None,
        user_id=getattr(current_user, "id", None) if current_user else None,
        semantic_id=str(uuid.uuid4()),
        semantic_id_kind="template",
    ):
        return await generate_template(template_name, parsed_document, file_content)


@router.put(
    "/composer/regenerate-template/{template_id}",
    response_model=TemplateGenerateResponse,
)
async def composer_regenerate_template(
    template_id: str,
    request: TemplateRegenerateRequest,
    current_user: Annotated[Optional[User], Depends(get_current_user_optional)] = None,
):
    """Regenerate a template_spec on an already-uploaded docx with author-specified ignored text fragments.

    Used when the initial generate pass over-extracted boilerplate paragraphs
    that should stay static. The underlying original.docx on R2 is unchanged;
    only the template_spec and template.docx are overwritten. agent_config
    (if previously composed) is cleared because the variable set has changed
    — the author must re-run compose-agent-config.
    """
    with cost_attribution(
        firm_id=getattr(current_user, "firm_id", None) if current_user else None,
        user_id=getattr(current_user, "id", None) if current_user else None,
        semantic_id=template_id,
        semantic_id_kind="template",
    ):
        return await regenerate_template(
            template_id=template_id,
            ignored_texts=request.ignored_texts,
            merges=request.merges,
            regeneration_instruction=request.regeneration_instruction,
        )


@router.post("/composer/compose-agent-config", response_model=AgentConfig)
async def composer_compose_agent_config(
    template_id: str,
    template_spec: list[TemplateVariable],
    current_user: Annotated[Optional[User], Depends(get_current_user_optional)] = None,
):
    """Step 3: Compose agent config from user-provided template spec.

    User provides for each template variable:
    - source: where to get the data (gmail, court_drive, case_vector, law_practice_vector, etc.)
    - source_params: search queries matching the source type
    """
    with cost_attribution(
        firm_id=getattr(current_user, "firm_id", None) if current_user else None,
        user_id=getattr(current_user, "id", None) if current_user else None,
        semantic_id=template_id,
        semantic_id_kind="template",
    ):
        return await compose_agent_config(template_id, template_spec)


# ─── Dry run ───


@router.post("/dry-run", response_model=DryRunResponse | AwaitingInputResponse)
async def dry_run(
    request: DryRunRequest,
    current_user: Annotated[Optional[User], Depends(get_current_user_optional)] = None,
):
    """Verify a candidate template spec end-to-end before committing it via compose-agent-config.

    Returns DryRunResponse on completion, OR AwaitingInputResponse when one or
    more group-dropdown composites need the user to pick an option. In the
    pending case, FE should present the dropdowns and then POST to
    /template/dry-run/resume with the original inputs + resolved_values +
    user_picks to finish rendering.

    Wrapped in cost_attribution so the resolver agents fired by the
    pipeline (draft, template, auto_derive, dropdown, reco_chips, vision,
    user_input_heal, etc.) write llm_cost_logs rows that the cost-center
    Pleadings card can aggregate. The Pleadings card filters by
    `semantic_id_kind = 'pleading_run'` ([llm_cost_log_repository.py:227](bkdrafts-be/src/core/common/storage/database/repositories/llm_cost_log_repository.py#L227)),
    so dry-runs must use the same discriminator. A synthetic per-request
    UUID becomes the `semantic_id` so `COUNT(DISTINCT semantic_id)`
    correctly counts each dry-run as one "run" in the avg-per-run breakdown.
    """
    dry_run_id = str(uuid.uuid4())
    with cost_attribution(
        firm_id=getattr(current_user, "firm_id", None) if current_user else None,
        user_id=getattr(current_user, "id", None) if current_user else None,
        case_id=request.case_id,
        semantic_id=dry_run_id,
        semantic_id_kind="pleading_run",
    ):
        return await execute_dry_run(
            template_id=request.template_id,
            template_spec=request.template_spec,
            case_id=request.case_id,
            bundle_picks=request.bundle_picks,
            candidate_bundle_role=request.bundle_role,
            candidate_bundle_companions=request.bundle_companions,
        )


@router.post("/dry-run/resume", response_model=DryRunResponse)
async def dry_run_resume(
    request: DryRunResumeRequest,
    current_user: Annotated[Optional[User], Depends(get_current_user_optional)] = None,
):
    """Resume a dry-run that returned AwaitingInputResponse.

    Server is stateless — the FE re-sends the original template_spec + the
    resolved_values it received + one pick per pending field. Server
    expands each pick into ResolvedTemplateValue(s), runs derivative
    resolvers, fills the docx, and returns DryRunResponse.

    Same cost_attribution shape as the initial /dry-run so resume costs
    roll into the Pleadings card under the same semantic_id_kind bucket.
    """
    dry_run_id = str(uuid.uuid4())
    with cost_attribution(
        firm_id=getattr(current_user, "firm_id", None) if current_user else None,
        user_id=getattr(current_user, "id", None) if current_user else None,
        case_id=request.case_id,
        semantic_id=dry_run_id,
        semantic_id_kind="pleading_run",
    ):
        return await resume_dry_run(
            template_id=request.template_id,
            template_spec=request.template_spec,
            case_id=request.case_id,
            resolved_values=request.resolved_values,
            user_picks=request.user_picks,
            bundle_picks=request.bundle_picks,
            candidate_bundle_role=request.bundle_role,
            candidate_bundle_companions=request.bundle_companions,
        )
