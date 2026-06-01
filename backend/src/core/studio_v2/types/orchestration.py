"""Orchestration result types — what `run_initial_stages_v2`,
`run_resume_stages_v2`, and `finalize_run_v2` return.

These three together drive the dry-run / draft pipeline. The shapes
mirror v1's `InitialStagesResult` + `FinalizedRun` + the awaiting-input
envelope, but are brand-new v2 types so the dry-run/draft routers can
type-check against them without importing anything from v1.

Stateless-resume invariant (Critical invariant from the plan):
- `AwaitingInputResponseV2` is what the BE returns when the pipeline
  pauses. The FE owns ALL partial state — `resolved_values`,
  `template_spec` (for dry-run only), `bundle_picks`, etc. — and
  re-sends them on the resume call.
- `run_id` is decorative (used for logging only). Server does NOT
  look up state by run_id; every resume call is a fresh execution
  that picks up from whatever the FE re-supplies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .fields import TemplateSpecV2
from .pending import PendingUserInputV2
from .resolution import ResolvedTemplateValueV2


@dataclass(frozen=True)
class InitialStagesResultV2:
    """Return value of `run_initial_stages_v2`.

    Either:
    - `pending_inputs is None` and `all_resolved` holds every field's
      resolved value → caller advances to `finalize_run_v2`.
    - `pending_inputs` is non-empty → caller PAUSES, builds an
      `AwaitingInputResponseV2`, returns it to the FE.
    """

    all_resolved: list[ResolvedTemplateValueV2]
    pending_inputs: dict[str, PendingUserInputV2] | None = None


class GrammarRepairV2(BaseModel):
    """One agreement-word swap applied by the Tier 2 grammar fixer.

    Surfaced on `FinalizedRunV2.grammar_repairs` + the dry-run /
    draft response so the FE Resolution Log can display per-fix
    forensic detail ("at paragraph 7 we changed 'Debtors' → 'Debtor'
    because the case has a single debtor"). Empty list when the
    fixer found nothing to repair OR the env flag is off.
    """

    model_config = ConfigDict(extra="forbid")

    paragraph_index: int
    original_word: str
    replacement_word: str
    occurrences: int  # how many tokens were replaced in this paragraph for this swap
    paragraph_preview: str  # first ~120 chars of the post-fix paragraph for context
    reason: str = ""


class FinalizedRunV2(BaseModel):
    """Return value of `finalize_run_v2`.

    The full post-pause / no-pause tail: heal → fill docx → upload R2 →
    presigned download URL. `filled_bytes` is carried for the
    parent-side of bundling so children's `extract_from_draft` slots
    can read the parent's draft text without re-downloading from R2.
    """

    model_config = ConfigDict(extra="forbid")

    resolved_values: list[ResolvedTemplateValueV2]
    generated_doc_url: str
    r2_object_key: str
    unresolved: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    grammar_repairs: list[GrammarRepairV2] = Field(default_factory=list)
    # `filled_bytes` is INTERNAL — it carries the rendered docx in
    # memory so bundling can hand it to companion children without a
    # second R2 round-trip. It MUST NOT serialize over the wire:
    # docx files are ZIP archives whose bytes are NOT valid UTF-8,
    # and pydantic's default `bytes → str` coercion on serialization
    # crashes the FastAPI response (UnicodeDecodeError at the first
    # non-ASCII byte in the docx central-directory header). The
    # `exclude=True` flag drops it from `model_dump()` /
    # response_model serialization but keeps it accessible on the
    # in-memory instance for the bundling engine.
    filled_bytes: bytes | None = Field(default=None, exclude=True)


class AwaitingInputResponseV2(BaseModel):
    """Sent to the FE when the pipeline pauses on USER_INPUT.

    `template_spec` is ECHOED for dry-run (so the FE keeps the spec for
    the resume payload — the server is stateless and re-loads nothing).
    For drafting it's OMITTED — the worker re-loads from
    `drafts_v2.template_snapshot` on resume (Phase 3).
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["awaiting_input"] = "awaiting_input"
    run_id: str
    template_id: str
    case_id: str
    template_spec: TemplateSpecV2 | None = None
    resolved_values: list[ResolvedTemplateValueV2] = Field(default_factory=list)
    pending_inputs: dict[str, PendingUserInputV2] = Field(default_factory=dict)
    bundle_picks: dict[str, str] | None = None


class DryRunResponseV2(BaseModel):
    """Successful (non-pending) dry-run / draft response.

    Returned when the pipeline completed end-to-end without needing
    user input. Wraps the finalizer output + a flat `status` discriminator
    so the FE can branch on `awaiting_input` vs `completed` at the
    top level.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["completed"] = "completed"
    run_id: str
    template_id: str
    case_id: str
    resolved_values: list[ResolvedTemplateValueV2] = Field(default_factory=list)
    generated_doc_url: str
    r2_object_key: str
    unresolved: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    grammar_repairs: list[GrammarRepairV2] = Field(default_factory=list)
    children: list["BundleChildRunV2"] = Field(default_factory=list)


class BundleChildRunV2(BaseModel):
    """One companion's rendered output from `run_bundle_v2`.

    Emitted as `children[*]` on a parent's `DryRunResponseV2` /
    `FinalizedRunV2`. The FE renders each child with its own download
    button + resolution traces, same as the parent.
    """

    model_config = ConfigDict(extra="forbid")

    template_id: str
    template_name: str
    companion_label: str
    finalized: FinalizedRunV2


# Pydantic forward-ref fix-up so `DryRunResponseV2.children: list["BundleChildRunV2"]`
# resolves to the concrete class above.
DryRunResponseV2.model_rebuild()


@dataclass
class ParentBundleContextV2:
    """Threaded into `run_initial_stages_v2(parent_context=...)` when
    resolving a companion template. Consumed by
    `inherit_from_parent_v2.resolve` to materialize the child's
    `value_from_parent_bundle` fields from the parent's resolved
    values, draft text, or slot configs.

    Mutable (regular `@dataclass`, not `frozen`) so the bundling engine
    can swap `slot_configurations` per companion without rebuilding
    the rest of the context.
    """

    resolved_values: dict[str, str] = field(default_factory=dict)
    draft_text: str = ""
    slot_configurations: dict[str, object] = field(default_factory=dict)
