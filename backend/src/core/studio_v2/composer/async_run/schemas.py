"""Pydantic schemas for the v2 composer-async pipeline.

Mirrors `src/core/components/pleading/schemas.py` shape but for a
simpler 5-state machine — composer tasks have no AWAITING_INPUT
pause, no EXISTING_FOUND dedup, no bundle picks, no resume.

Three layers:
- **Records** persisted on Redis (`V2ComposerTaskRecord`)
- **Requests** the FE POSTs (`StartGenerateRequest`, `StartRegenerateRequest`)
- **Responses** returned to the FE (`V2ComposerTaskResponse`,
  `StartComposerTaskResponse`)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.core.studio_v2.services.composer.schemas import (
    MergeOperationV2,
    TemplateGenerateResponseV2,
    TemplateRegenerateDiffV2,
)


V2ComposerTaskKind = Literal["generate", "regenerate"]

V2ComposerTaskStatus = Literal[
    "QUEUED",
    "PENDING",
    "RUNNING",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
]

ACTIVE_STATES: frozenset[str] = frozenset({"QUEUED", "PENDING", "RUNNING"})
TERMINAL_STATES: frozenset[str] = frozenset({"COMPLETED", "FAILED", "CANCELLED"})


# ─── Persisted record ────────────────────────────────────────────────


class V2ComposerTaskRecord(BaseModel):
    """The full composer task record persisted on Redis
    (`core:composer:task:{task_id}`).

    `kind` discriminates between fresh template upload (generate) and
    re-extraction of an existing template (regenerate). FE renders the
    card the same way regardless; the workers diverge by `kind`.
    """

    task_id: str
    user_id: str
    firm_id: str | None = None
    kind: V2ComposerTaskKind

    # Display state — what the FE card shows
    template_name: str = ""
    template_id: str | None = None  # set when COMPLETED (or known at start for regenerate)

    status: V2ComposerTaskStatus

    # Input payloads carried through the pipeline so the worker can
    # re-fetch them after a Taskiq dispatch (we DON'T pass docx bytes
    # through Taskiq — they live in Redis or R2; this carries the
    # control fields).
    template_role: str = "single"
    original_filename: str = ""

    # Regenerate-only inputs (kind == "regenerate")
    ignored_texts: list[str] | None = None
    merges: list[MergeOperationV2] | None = None
    regeneration_instruction: str | None = None

    # Generate-only — pointer into Redis where uploaded docx bytes are
    # staged for the worker to fetch. Generated once at /start,
    # consumed once by the worker. Hex-encoded SHA-256 of the bytes
    # to keep the key short.
    upload_blob_key: str | None = None

    # Completion payload — the response shape mirrors the existing
    # sync endpoints so FE rendering code can reuse the types.
    generate_result: TemplateGenerateResponseV2 | None = None
    regenerate_result: TemplateRegenerateDiffV2 | None = None

    # Failure detail
    error: str | None = None

    created_at: datetime
    updated_at: datetime


# ─── Requests ────────────────────────────────────────────────────────


class StartGenerateMetadata(BaseModel):
    """JSON body the FE includes alongside the docx upload (multipart).

    Pure metadata — the bytes ride as the `file` part."""

    template_name: str
    template_role: str = Field(default="single", pattern=r"^(single|master|part_of_packet)$")


class StartRegenerateRequest(BaseModel):
    """JSON body for re-extracting an existing template."""

    template_id: str
    ignored_texts: list[str] | None = None
    merges: list[MergeOperationV2] | None = None
    regeneration_instruction: str | None = None
    parent_template_id: str | None = None  # for part_of_packet re-extract


# ─── Responses ───────────────────────────────────────────────────────


class V2ComposerTaskResponse(BaseModel):
    """FE-facing projection of `V2ComposerTaskRecord`. Identical shape
    minus internal-only fields (`upload_blob_key`).

    Built via `V2ComposerTaskResponse.from_record(record)`.
    """

    task_id: str
    user_id: str
    kind: V2ComposerTaskKind

    template_name: str
    template_id: str | None = None

    status: V2ComposerTaskStatus

    template_role: str = "single"
    original_filename: str = ""

    generate_result: TemplateGenerateResponseV2 | None = None
    regenerate_result: TemplateRegenerateDiffV2 | None = None

    error: str | None = None

    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record: V2ComposerTaskRecord) -> "V2ComposerTaskResponse":
        return cls(
            task_id=record.task_id,
            user_id=record.user_id,
            kind=record.kind,
            template_name=record.template_name,
            template_id=record.template_id,
            status=record.status,
            template_role=record.template_role,
            original_filename=record.original_filename,
            generate_result=record.generate_result,
            regenerate_result=record.regenerate_result,
            error=record.error,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


class StartComposerTaskResponse(BaseModel):
    """Returned from POST /generate and POST /regenerate. Mirrors v1
    pleading's `StartTemplateDraftResponse` shape so the FE store can
    reuse logic."""

    task_id: str
    status: V2ComposerTaskStatus
