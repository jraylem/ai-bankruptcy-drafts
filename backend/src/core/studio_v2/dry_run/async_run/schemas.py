"""Pydantic schemas for the v2 dry-run-async pipeline.

Three layers:
- **Records** persisted on Redis (`V2DryRunTaskRecord`)
- **Requests** the FE POSTs (`StartDryRunRequest`, `SubmitInputRequest`)
- **Responses** returned to the FE (`V2DryRunTaskResponse`,
  `StartDryRunResponse`)

Mirrors `studio_v2/composer/async_run/schemas.py` shape but with a
larger state machine (7 states) to model the pause/resume protocol
that composer doesn't have.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ...types.fields import TemplateSpecV2
from ...types.orchestration import DryRunResponseV2
from ...types.pending import PendingUserInputV2
from ...types.picks import UserSelectionV2
from ...types.resolution import ResolvedTemplateValueV2


V2DryRunStatus = Literal[
    "QUEUED",
    "PENDING",
    "RUNNING",
    "AWAITING_INPUT",
    "RESUMING",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
]

ACTIVE_STATES: frozenset[str] = frozenset(
    {"QUEUED", "PENDING", "RUNNING", "AWAITING_INPUT", "RESUMING"},
)
TERMINAL_STATES: frozenset[str] = frozenset({"COMPLETED", "FAILED", "CANCELLED"})


# ─── Persisted record ────────────────────────────────────────────────


class V2DryRunTaskRecord(BaseModel):
    """The full dry-run task record persisted on Redis
    (`core:dry_run:task:{task_id}`).

    Carries the full pipeline context (spec + case + bundle config)
    so the worker can resume after AWAITING_INPUT without the FE
    re-sending everything (composer-async has no pause; that's the
    main shape delta).
    """

    task_id: str
    user_id: str
    firm_id: str | None = None

    # Always known at /start
    template_id: str
    case_id: str
    template_name: str = ""
    case_label: str = ""  # e.g. "26-10700" — cached for FE card display

    status: V2DryRunStatus

    # Frozen at /start — the candidate spec the paralegal is iterating.
    # Immutable for the task's lifetime so resume reads the same shape
    # the initial run saw.
    template_spec: TemplateSpecV2

    # Bundling iteration overrides (echoed across resume)
    bundle_picks: dict[str, str] | None = None
    bundle_role: str | None = None
    bundle_companions: list[dict[str, Any]] | None = None

    # Set when RUNNING → AWAITING_INPUT — what the FE renders in the
    # pending-input modal.
    resolved_values: list[ResolvedTemplateValueV2] | None = None
    pending_inputs: dict[str, PendingUserInputV2] | None = None

    # Set when /submit-input fires — the paralegal's picks the resume
    # worker will consume.
    user_picks: dict[str, UserSelectionV2] | None = None

    # Completion payload — the same shape `execute_dry_run_v2` returns.
    result: DryRunResponseV2 | None = None

    # Failure detail
    error: str | None = None

    created_at: datetime
    updated_at: datetime


# ─── Requests ────────────────────────────────────────────────────────


class StartDryRunRequest(BaseModel):
    """JSON body for POST /api/v3/studio/dry-run-async/start.

    Same shape as the sync `DryRunRequestV2` — paralegal iterates
    against the wizard's working draft (`template_spec`) without
    needing to publish.
    """

    model_config = ConfigDict(extra="forbid")

    template_id: str
    case_id: str
    template_spec: TemplateSpecV2
    bundle_picks: dict[str, str] | None = None
    bundle_role: str | None = None
    bundle_companions: list[dict[str, Any]] | None = None


class SubmitInputRequest(BaseModel):
    """JSON body for POST /api/v3/studio/dry-run-async/{task_id}/submit-input.

    Stateless-resume contract still holds at the WORKER level (the
    pipeline functions don't carry session state) — but the TASK
    record holds the template_spec + pending_inputs + resolved_values
    persisted at the pause point, so the FE only needs to re-send the
    paralegal's picks. bundle_picks may be re-supplied if the
    paralegal wants to amend pre-flight branch choices.
    """

    model_config = ConfigDict(extra="forbid")

    user_picks: dict[str, UserSelectionV2] = Field(default_factory=dict)
    bundle_picks: dict[str, str] | None = None


# ─── Responses ───────────────────────────────────────────────────────


class V2DryRunTaskResponse(BaseModel):
    """FE-facing projection of `V2DryRunTaskRecord`. Identical shape
    minus internal-only fields (currently none — the record IS the
    FE projection because we want the full pending_inputs + result
    payloads visible to the FE).
    """

    task_id: str
    user_id: str

    template_id: str
    case_id: str
    template_name: str = ""
    case_label: str = ""

    status: V2DryRunStatus

    template_spec: TemplateSpecV2

    bundle_picks: dict[str, str] | None = None
    bundle_role: str | None = None
    bundle_companions: list[dict[str, Any]] | None = None

    resolved_values: list[ResolvedTemplateValueV2] | None = None
    pending_inputs: dict[str, PendingUserInputV2] | None = None
    user_picks: dict[str, UserSelectionV2] | None = None

    result: DryRunResponseV2 | None = None

    error: str | None = None

    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record: V2DryRunTaskRecord) -> "V2DryRunTaskResponse":
        return cls(
            task_id=record.task_id,
            user_id=record.user_id,
            template_id=record.template_id,
            case_id=record.case_id,
            template_name=record.template_name,
            case_label=record.case_label,
            status=record.status,
            template_spec=record.template_spec,
            bundle_picks=record.bundle_picks,
            bundle_role=record.bundle_role,
            bundle_companions=record.bundle_companions,
            resolved_values=record.resolved_values,
            pending_inputs=record.pending_inputs,
            user_picks=record.user_picks,
            result=record.result,
            error=record.error,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


class StartDryRunResponse(BaseModel):
    """Returned from POST /start and POST /{task_id}/submit-input."""

    task_id: str
    status: V2DryRunStatus
