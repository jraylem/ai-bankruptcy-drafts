"""Request schemas for the v2 dry-run endpoints.

Response shapes (`DryRunResponseV2`, `AwaitingInputResponseV2`) live
in `studio_v2.types.orchestration` — they're shared between dry-run
and the future Phase 3 draft endpoints.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ...types.fields import TemplateSpecV2
from ...types.picks import UserSelectionV2
from ...types.resolution import ResolvedTemplateValueV2


class DryRunRequestV2(BaseModel):
    """POST /api/v3/studio/templates/{id}/dry-run body.

    Server uses the body's `template_spec` (NOT the persisted one) —
    paralegal iterates against the wizard's working draft without
    needing to publish first. Candidate `bundle_role` /
    `bundle_companions` override persisted values for the same reason.
    """

    model_config = ConfigDict(extra="forbid")

    template_id: str
    case_id: str
    template_spec: TemplateSpecV2
    bundle_picks: dict[str, str] | None = None
    bundle_role: str | None = None
    bundle_companions: list[dict[str, Any]] | None = None


class DryRunResumeRequestV2(BaseModel):
    """POST /api/v3/studio/templates/{id}/dry-run/resume body.

    Stateless server — FE re-sends:
    - `template_spec` (same one it sent to /dry-run)
    - `resolved_values` (from the prior AwaitingInputResponseV2)
    - `pending_inputs` (so expand_picks_v2 can match raw_context per option)
    - `user_picks` (the paralegal's selections)
    - `bundle_picks` / `bundle_role` / `bundle_companions` (echoed)
    """

    model_config = ConfigDict(extra="forbid")

    template_id: str
    case_id: str
    template_spec: TemplateSpecV2
    resolved_values: list[ResolvedTemplateValueV2] = Field(default_factory=list)
    pending_inputs: dict[str, Any] | None = None
    user_picks: dict[str, UserSelectionV2] = Field(default_factory=dict)
    bundle_picks: dict[str, str] | None = None
    bundle_role: str | None = None
    bundle_companions: list[dict[str, Any]] | None = None
