"""HTTP request / response schemas for the /draft endpoints."""

from typing import Literal

from pydantic import BaseModel, Field

from src.core.agents.resolvers.user_input_resolver import UserSelection
from src.core.agents.types.resolution import ResolvedTemplateValue


# ─── Requests ─────────────────────────────────────────────────────────


class DraftRequest(BaseModel):
    """Request body for POST /draft — identifies the committed template and the case to draft against.

    `bundle_picks` is required when the parent template has any branch
    companions: keyed by the companion's index (stringified), value is
    the picked BranchOption.label. Fixed companions always run, no pick
    needed.
    """

    template_id: str = Field(description="ID of the draft template with a committed agent config.")
    case_id: str = Field(description="Sanitized case_id (e.g. '26_10700') to draft against.")
    bundle_picks: dict[str, str] | None = Field(
        default=None,
        description=(
            "Optional pre-flight picks for the parent template's branch "
            "companions. Keyed by stringified companion index; value is the "
            "picked BranchOption label. Required only when the parent has "
            "branch companions."
        ),
    )


class DraftResumeRequest(BaseModel):
    """Request body for POST /draft/resume after the initial draft returned AwaitingInputResponse.

    No template_spec here — draft uses the persisted agent_config on the
    DraftTemplate row. Bundle picks decided pre-flight on the initial
    request are echoed back verbatim.
    """
    template_id: str
    case_id: str
    resolved_values: list[ResolvedTemplateValue]
    user_picks: dict[str, UserSelection]
    bundle_picks: dict[str, str] | None = None


# ─── Responses ────────────────────────────────────────────────────────


class DraftValidation(BaseModel):
    """Post-fill validation summary — whether every placeholder resolved + any surfaced low-confidence warnings."""

    valid: bool
    errors: list[str]
    warnings: list[str]


class DraftChildResult(BaseModel):
    """One child docx produced as part of a parent's bundle at draft time."""

    template_id: str
    template_name: str
    companion_label: str
    generated_doc_url: str
    r2_object_key: str
    resolved_values: list[ResolvedTemplateValue]
    warnings: list[str] = []


class DraftResponse(BaseModel):
    """Response body for POST /draft and /draft/resume when the draft completes without pausing."""

    status: Literal["completed"] = "completed"
    template_id: str
    case_id: str
    resolved_values: list[ResolvedTemplateValue]
    generated_doc_url: str
    r2_object_key: str
    validation: DraftValidation
    children: list[DraftChildResult] = []
