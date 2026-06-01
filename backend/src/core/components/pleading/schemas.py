"""Pydantic schemas for the v2 template-draft pipeline.

Three layers of types:
- **Records** persisted on Redis (`V2TemplateDraftTaskRecord`) + persisted
  inside the `case_generation_logs.children` JSONB column (`BundleChildLog`)
- **Requests** posted by the FE (`StartTemplateDraftRequest`, etc.)
- **Responses** returned to the FE (`V2TemplateDraftTaskResponse`,
  `CompletedDocumentEnvelope`)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.core.agents.resolvers.user_input_resolver import UserSelection
from src.core.agents.types.resolution import ResolvedTemplateValue
from src.core.components.engines.draft.schemas import DraftResponse


V2TaskStatus = Literal[
    "QUEUED",
    "PENDING",
    "CHECKING_EXISTING",
    "EXISTING_FOUND",
    "DRAFTING",
    "AWAITING_INPUT",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
]

ACTIVE_STATES: frozenset[str] = frozenset({
    "QUEUED",
    "PENDING",
    "CHECKING_EXISTING",
    "EXISTING_FOUND",
    "DRAFTING",
    "AWAITING_INPUT",
})

TERMINAL_STATES: frozenset[str] = frozenset({"COMPLETED", "FAILED", "CANCELLED"})


# ─── Persistence-side types ───────────────────────────────────────────


class BundleChildLog(BaseModel):
    """One row inside CaseGenerationLog.children JSONB.

    Mirrors DraftChildResult but durable (raw R2 key instead of a presigned
    URL — the router re-signs on every read).
    """

    template_id: str
    template_name: str
    companion_label: str
    r2_object_key: str


class V2TemplateDraftTaskRecord(BaseModel):
    """The full task record persisted on Redis (`core:pleading:task:{task_id}`).

    `template_id` is the only identifier used for drafting; `template_name`
    is a metadata-only snapshot for audit + fallback display.
    """

    task_id: str
    user_id: str
    case_id: str
    template_id: str
    template_name: str = ""

    status: V2TaskStatus

    bundle_picks: dict[str, str] | None = None

    # Populated when the task pauses on USER_INPUT
    resolved_values: list[ResolvedTemplateValue] | None = None
    pending_inputs: dict[str, Any] | None = None

    # Cross-references to case_generation_logs
    log_id: str | None = None
    existing_log_id: str | None = None

    # Completed-state payload (the FE reads this to drive the popover)
    result: DraftResponse | None = None

    # Failure detail
    error: str | None = None

    created_at: datetime
    updated_at: datetime


# ─── Requests ────────────────────────────────────────────────────────


class StartTemplateDraftRequest(BaseModel):
    """Body for POST /api/v2/core/pleading/start."""

    template_id: str = Field(description="ID of a production-ready (agent_config committed) template.")
    case_id: str = Field(description="Sanitized case_id to draft against.")
    bundle_picks: dict[str, str] | None = Field(
        default=None,
        description=(
            "Optional pre-flight picks for the parent template's branch "
            "companions (same shape as the studio's /draft endpoint)."
        ),
    )
    skip_existing_check: bool = Field(
        default=False,
        description=(
            "If True, skip the EXISTING_FOUND lookup and go straight to "
            "DRAFTING. Used by /regenerate."
        ),
    )


class SubmitInputRequest(BaseModel):
    """Body for POST /api/v2/core/pleading/{task_id}/submit-input."""

    user_picks: dict[str, UserSelection]


# ─── Responses ───────────────────────────────────────────────────────


class V2TemplateDraftTaskResponse(BaseModel):
    """The task as the FE sees it. Mirrors V2TemplateDraftTaskRecord."""

    task_id: str
    user_id: str
    case_id: str
    template_id: str
    template_name: str = ""

    status: V2TaskStatus

    bundle_picks: dict[str, str] | None = None
    resolved_values: list[ResolvedTemplateValue] | None = None
    pending_inputs: dict[str, Any] | None = None

    log_id: str | None = None
    existing_log_id: str | None = None

    result: DraftResponse | None = None
    error: str | None = None

    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record: V2TemplateDraftTaskRecord) -> "V2TemplateDraftTaskResponse":
        return cls(**record.model_dump())


class StartTemplateDraftResponse(BaseModel):
    """Body returned by POST /start — the freshly-created (or queued) task."""

    task: V2TemplateDraftTaskResponse


class CaseGenerationLogResponse(BaseModel):
    """Body returned by GET /case-generation-logs?case_id=... — history view."""

    id: str
    user_id: str
    case_id: str
    draft_template_id: str
    template_name: str | None
    status: str
    task_id: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime | None


class ChildPresignedEntry(BaseModel):
    """One bundle child's freshly-presigned URL."""

    template_id: str
    template_name: str
    companion_label: str
    url: str


class CompletedDocumentEnvelope(BaseModel):
    """Body returned by GET /case-generation-logs/{log_id}/download-url.

    Re-signed on every read so the FE always gets a fresh ~1h presigned URL.
    """

    log_id: str
    parent_template_id: str
    parent_url: str
    children: list[ChildPresignedEntry] = []


# ─── SSE event envelope ───────────────────────────────────────────────


class V2TemplateDraftEvent(BaseModel):
    """Envelope written to the Redis Stream by `events.emit()`.

    The SSE generator decodes one of these per stream entry and forwards
    the inner `task` payload to the FE.
    """

    type: Literal[
        "snapshot",
        "status_changed",
        "awaiting_input",
        "existing_found",
        "completed",
        "failed",
        "cancelled",
        "removed",
    ]
    task: V2TemplateDraftTaskResponse | None = None
    tasks: list[V2TemplateDraftTaskResponse] | None = None  # populated for `snapshot`
