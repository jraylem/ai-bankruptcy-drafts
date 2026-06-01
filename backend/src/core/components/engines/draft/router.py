"""HTTP routes for the /draft endpoints — run a committed template against a case, resume on user input."""

from fastapi import APIRouter

from src.core.agents.resolvers.user_input_resolver import AwaitingInputResponse

from .schemas import DraftRequest, DraftResponse, DraftResumeRequest
from .service import execute_draft_for_case, resume_draft

router = APIRouter(prefix="/draft")


# ─── Routes ───


@router.post("", response_model=DraftResponse | AwaitingInputResponse)
async def draft(request: DraftRequest):
    """Draft a document using a committed template agent config against a case.

    Uses the persisted agent_config from the DraftTemplate row (committed via
    compose-agent-config) and runs the full draft pipeline against the given
    case_id. Returns DraftResponse on completion, or AwaitingInputResponse when
    one or more group-dropdown composites need the user to pick. On pending,
    FE should POST to /draft/resume with resolved_values + user_picks.
    """
    return await execute_draft_for_case(
        template_id=request.template_id,
        case_id=request.case_id,
        bundle_picks=request.bundle_picks,
    )


@router.post("/resume", response_model=DraftResponse)
async def draft_resume(request: DraftResumeRequest):
    """Resume a draft that returned AwaitingInputResponse.

    Server is stateless — no template_spec in the request because the
    committed agent_config lives on the DraftTemplate row. FE sends
    resolved_values + one pick per pending field; server expands each pick
    into ResolvedTemplateValue(s), runs derivative resolvers, fills the
    docx, and returns DraftResponse.
    """
    return await resume_draft(
        template_id=request.template_id,
        case_id=request.case_id,
        resolved_values=request.resolved_values,
        user_picks=request.user_picks,
        bundle_picks=request.bundle_picks,
    )
