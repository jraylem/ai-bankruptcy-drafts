"""HTTP request / response schemas for the /template endpoints."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.core.agents.resolvers.user_input_resolver import UserSelection
from src.core.agents.types.bundling import BundleCompanion
from src.core.agents.types.resolution import ResolvedTemplateValue
from src.core.agents.types.spec import TemplateVariable


# ─── Requests ─────────────────────────────────────────────────────────


class DraftTemplateUpdateRequest(BaseModel):
    """Request body for PUT /template/{template_id} — renames a draft template."""

    name: str = Field(min_length=1, max_length=255, description="New template name")


class MergeOperation(BaseModel):
    """Collapse two or more existing template variables into one merged variable on regeneration.

    The author identifies variables by their names (as they appear in the
    current template_spec); the template agent figures out the exact merged
    marker by spanning the source variables' values IN DOCUMENT ORDER plus
    whatever text sits between them. The merged variable's
    template_property_marker is the derived span — later used by
    UserInputHealAgent as the preferred-format heal target for dropdown picks.

    The merged variable's name is always auto-derived as
    `"_".join(source_variables)` — e.g. `["ecf_number", "document_title"]`
    becomes `"ecf_number_document_title"`. No manual naming.
    """
    model_config = ConfigDict(extra="forbid")

    source_variables: list[str] = Field(
        min_length=2,
        description=(
            "Two or more existing template_variable names to merge. "
            "Order hints document order; the agent validates against the actual source."
        ),
    )
    description: str | None = Field(
        default=None,
        description="Optional description for the merged variable.",
    )

    def resolve_variable_name(self) -> str:
        """The merged variable's name, derived from source_variables."""
        return "_".join(self.source_variables)


class TemplateRegenerateRequest(BaseModel):
    """Body for PUT /template/composer/regenerate-template/{template_id}.

    Three optional post-generation transforms:

      - `ignored_texts`: text fragments the agent must NOT derive variables
        from (typically copied from an over-extracted variable's
        template_identifying_text_match).
      - `merges`: collapse two or more extracted variables into a single
        merged one whose marker spans them in document order.
      - `regeneration_instruction`: free-form prose the author wants the
        template agent to follow when re-extracting (e.g. "merge the
        claim_no and claim_no_title", "don't extract the clerk address").
    """
    ignored_texts: list[str] = Field(
        default_factory=list,
        description="Text fragments the agent must treat as static boilerplate — typically template_identifying_text_match of over-extracted variables",
    )
    merges: list[MergeOperation] = Field(
        default_factory=list,
        description="Merge operations applied during regeneration; each collapses 2+ variables into one.",
    )
    regeneration_instruction: str | None = Field(
        default=None,
        description="Optional free-form steering instruction surfaced to the template agent's extract prompt as a high-priority directive.",
    )


class DryRunRequest(BaseModel):
    """Request body for POST /template/dry-run.

    Mirrors the inputs to POST /template/composer/compose-agent-config
    (template_id + template_spec) plus the case_id to resolve against.
    The dry-run endpoint builds an in-memory AgentConfig from the same
    helper compose-agent-config uses, runs the full draft pipeline, and
    returns the verification result without persisting anything — so the
    caller can iterate on the spec before committing it.

    `bundle_picks` is required when the parent template has any branch
    companions — keyed by the companion's index (stringified), value is
    the picked option's label. Ignored for standalone / child_only
    templates and for parents whose companions are all fixed.
    """
    template_id: str = Field(description="ID of the draft template being verified.")
    template_spec: list[TemplateVariable] = Field(
        description="Candidate template spec with source / source_params / instruction populated per variable.",
    )
    case_id: str = Field(description="Sanitized case_id (e.g. '26_10700') the dry run should resolve against.")
    bundle_picks: dict[str, str] | None = Field(
        default=None,
        description=(
            "Optional pre-flight picks for the parent template's branch "
            "companions. Keyed by stringified companion index; value is the "
            "picked BranchOption label. Required only when the parent has "
            "branch companions; fixed companions always run."
        ),
    )
    bundle_role: str | None = Field(
        default=None,
        description=(
            "Optional candidate bundle_role for this dry-run. When supplied "
            "alongside bundle_companions, the dry-run uses these values "
            "INSTEAD of the persisted ones — same iteration model as "
            "template_spec. Lets the studio dry-run a parent's bundling "
            "config before committing it. Omit to fall through to whatever "
            "is persisted on the row."
        ),
    )
    bundle_companions: list | None = Field(
        default=None,
        description=(
            "Optional candidate bundle_companions list for this dry-run. "
            "Paired with bundle_role above; the dry-run service validates "
            "the shape via TypeAdapter before use. Children referenced by "
            "child_template_id still load from their persisted rows — only "
            "the parent's companion config is iterable here."
        ),
    )


class DryRunResumeRequest(BaseModel):
    """Request body for POST /template/dry-run/resume after the initial dry-run returned AwaitingInputResponse.

    The FE re-sends the original template_spec + the resolved_values it
    received + one pick per pending field; server is stateless. Bundle
    picks decided pre-flight on the initial request are echoed back
    verbatim so the resumed run schedules the same children.
    """
    template_id: str
    template_spec: list[TemplateVariable]
    case_id: str
    resolved_values: list[ResolvedTemplateValue]
    user_picks: dict[str, UserSelection]
    bundle_picks: dict[str, str] | None = None
    bundle_role: str | None = None
    bundle_companions: list | None = None


# ─── Responses ────────────────────────────────────────────────────────


class DocumentParseResponse(BaseModel):
    """Response body for POST /template/composer/parse — flattened text + metadata from an uploaded docx."""

    document_id: str
    parsed: bool
    content: str
    metadata: dict[str, Any]


class RemovedVariableReason(BaseModel):
    """One entry in `TemplateRegenerateDiff.removed`.

    Categorizes WHY a baseline variable is missing from the new spec so
    the FE can render the appropriate annotation:

      - `merged`     → variable appeared as a `source_variable` in a
        merge op; `merged_into` carries the new merged name.
      - `ignored`    → variable's identifying text overlapped an
        `ignored_texts` fragment.
      - `unexpected` → variable was in the baseline, no user signal
        asked for its removal, but the agent dropped it anyway. The FE
        surfaces this as a drift warning.
    """
    name: str
    reason: Literal["merged", "ignored", "unexpected"]
    merged_into: str | None = None


class TemplateRegenerateDiff(BaseModel):
    """Summary of structural changes between the previous baseline spec
    and the just-regenerated spec.

    `added` lists every variable name present in the new spec but not
    the baseline — all surfaces as "unrequested" drift in the FE UI.
    `removed` carries a reason tag per entry; user-requested removals
    (merged / ignored) render plainly while `unexpected` removals
    render as drift. `preserved` is the intersection.

    Only meaningful on the regenerate path. Initial generate has no
    baseline; the response carries `diff = None`.
    """
    added: list[str]
    removed: list[RemovedVariableReason]
    preserved: list[str]


class TemplateGenerateResponse(BaseModel):
    """Response body for POST /template/composer/generate-template and the regenerate endpoint."""

    template_id: str
    template_name: str
    template_spec: list[TemplateVariable]
    generated: bool
    original_doc_url: str
    template_doc_url: str
    diff: TemplateRegenerateDiff | None = None


class DryRunValidation(BaseModel):
    """Post-fill validation summary for a dry-run — unresolved placeholders, low-confidence warnings."""

    valid: bool
    errors: list[str]
    warnings: list[str]


class BundleChildResult(BaseModel):
    """One child docx produced as part of a parent's bundle.

    Returned alongside the parent's docx URL so the FE can offer a
    download for each — same shape for dry-run and draft.
    """
    template_id: str
    template_name: str
    companion_label: str
    generated_doc_url: str
    resolved_values: list[ResolvedTemplateValue]
    warnings: list[str] = []


class DryRunResponse(BaseModel):
    """Response body for POST /template/dry-run and /template/dry-run/resume when the run completes without pausing."""

    status: Literal["completed"] = "completed"
    template_id: str
    resolved_values: list[ResolvedTemplateValue]
    generated_doc_url: str
    validation: DryRunValidation
    can_generate: bool
    children: list[BundleChildResult] = []


class DraftTemplateResponse(BaseModel):
    """Response body for GET /template and PUT /template/{id} — mirrors the DraftTemplate ORM row with presigned URLs."""

    id: str
    name: str
    original_doc_url: str | None
    template_doc_url: str | None
    template_spec: list | None
    agent_config: dict | None
    bundle_role: str = "standalone"
    bundle_companions: list | None = None
    created_at: str | None
    is_active: bool


class BundlingConfigUpdateRequest(BaseModel):
    """Request body for PUT /template/{id}/bundling-config — updates the
    template's bundling role + companion list.

    bundle_role selects the template's role in the bundling system.
    bundle_companions is the parent's list of attached children (only
    meaningful when bundle_role == 'parent'); set to NULL or [] for
    standalone or child_only templates.
    """
    model_config = ConfigDict(extra="forbid")

    bundle_role: Literal["standalone", "parent", "child_only"]
    bundle_companions: list[BundleCompanion] | None = None


class CleanedParentEntry(BaseModel):
    """One parent template whose bundle_companions got cleaned during a
    force-delete of a child template. Surfaced in DeleteTemplateResponse
    so the caller can show the author which parents were edited."""

    template_id: str
    name: str
    removed_companion_labels: list[str] = Field(
        default_factory=list,
        description=(
            "Labels of the companions in this parent that referenced the "
            "deleted child. A FixedBundleCompanion shows up here when its "
            "child_template_id matched. A BranchBundleCompanion shows up "
            "when one of its options matched — the option is removed; the "
            "whole companion is dropped only if filtering would leave "
            "fewer than 2 options (BranchBundleCompanion requires >=2)."
        ),
    )


class DeleteTemplateResponse(BaseModel):
    """Response body for DELETE /template/{id} — confirms soft-deletion.

    `cleaned_parents` is populated only when the delete was called with
    `force=true` AND there were referencing parents to clean. Empty list
    in the no-references case (current behavior) keeps existing FE
    callers wire-compatible.
    """

    success: bool
    id: str
    cleaned_parents: list[CleanedParentEntry] = Field(default_factory=list)


class ReferencingParent(BaseModel):
    """One parent template that references the child being deleted.
    Embedded in DeleteTemplateConflictDetail (409 response body)."""

    template_id: str
    name: str
    companion_labels: list[str] = Field(
        description=(
            "Companion labels in this parent that reference the doomed "
            "child. See CleanedParentEntry for the matching shape on the "
            "force-delete response side."
        ),
    )


class DeleteTemplateConflictDetail(BaseModel):
    """409 response body for DELETE /template/{id} when other active
    parent templates reference the target in their bundle_companions.

    Author can either edit each parent first or retry the DELETE with
    `?force=true` to cascade-clean the parents."""

    message: str
    referencing_parents: list[ReferencingParent]
