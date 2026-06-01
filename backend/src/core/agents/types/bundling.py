"""Bundling types — parent/child template relationships at draft time.

A template can take one of three bundling roles:
  - STANDALONE — runs on its own, no children. Default for most templates.
  - PARENT — runs on its own; carries a list of `BundleCompanion` entries
    declaring which child templates ship alongside it at draft time.
  - CHILD_ONLY — cannot be drafted directly. Only invoked when a parent
    template's bundle resolution scheduler picks it. Variables on a
    child_only template marked `inherit_from_parent` declare slots that
    each parent fills via per-companion `slot_configurations`.

A companion can be FIXED (always include this child) or BRANCH (a yes/no
question routes to one of N child templates at draft time).

Phase 1B persists these types on the parent template's
`bundle_companions` JSONB column. Phase 2 wires up the runtime engine
that pauses for branch resolution and threads parent context into child
slot resolution.
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TemplateBundleRole(str, Enum):
    """Per-template role in the bundling system."""
    STANDALONE = "standalone"
    PARENT = "parent"
    CHILD_ONLY = "child_only"


# ─── Slot configuration (parent's per-slot filling strategy) ──────────


class ParentVariableSlotConfig(BaseModel):
    """Pull the slot's value from a resolved variable on the parent.

    No LLM extraction — direct value handoff. Used for inheriting
    case-derived values the parent already has (case_number, chapter,
    debtor_name, etc.).
    """
    model_config = ConfigDict(extra="forbid")
    kind: Literal["parent_variable"] = "parent_variable"
    parent_variable: str = Field(
        description="Name of the parent's variable to inherit from.",
    )


class ExtractFromDraftSlotConfig(BaseModel):
    """Extract the slot's value from the parent's produced draft text via LLM.

    Used for values that exist as words IN the rendered draft but aren't
    named parent variables — e.g. docket_title (the actual filed title,
    which can differ from the parent template's authoring name).

    Phase 1B: source_params accepted at save time, but the resolver
    returns a placeholder until Phase 2 threads parent draft text into
    the child's resolution context.
    """
    model_config = ConfigDict(extra="forbid")
    kind: Literal["extract_from_draft"] = "extract_from_draft"
    extract_instruction: str = Field(
        description=(
            "Tells the extraction LLM what to pull from the parent's "
            "produced draft text. Should describe both location (e.g. "
            "'the bold heading after the case caption') and shape."
        ),
    )


class LiteralSlotConfig(BaseModel):
    """Hardcoded string for this slot — same value every time this
    companion runs. Used for static values bound to a specific bundling
    configuration (e.g. court division code, role labels)."""
    model_config = ConfigDict(extra="forbid")
    kind: Literal["literal"] = "literal"
    literal_value: str


SlotConfig = (
    ParentVariableSlotConfig
    | ExtractFromDraftSlotConfig
    | LiteralSlotConfig
)


# ─── Companion entry on a parent's bundling spec ──────────────────────


class BranchOption(BaseModel):
    """One option inside a branch companion's question.

    Pairs an answer label (e.g. 'Yes' / 'No') with the child template
    that gets attached when the user picks it, plus how to fill that
    child's slots.
    """
    model_config = ConfigDict(extra="forbid")
    label: str = Field(description='User-facing answer label, e.g. "Yes" / "No".')
    child_template_id: str = Field(
        description=(
            "ID of the child template to include when this option is "
            "picked. Must reference a template whose bundle_role == 'child_only'."
        ),
    )
    slot_configurations: dict[str, SlotConfig] = Field(
        default_factory=dict,
        description=(
            "Map from this child's slot variable name to its filling "
            "config. Every inherit_from_parent variable on the child must "
            "appear as a key here."
        ),
    )


class FixedBundleCompanion(BaseModel):
    """Always include this child when the parent runs."""
    model_config = ConfigDict(extra="forbid")
    kind: Literal["fixed"] = "fixed"
    label: str = Field(
        description='Author-facing label, e.g. "Cover Sheet". Not surfaced at draft time.',
    )
    child_template_id: str = Field(
        description=(
            "ID of the child template to always attach. Must reference a "
            "template whose bundle_role == 'child_only'."
        ),
    )
    slot_configurations: dict[str, SlotConfig] = Field(default_factory=dict)


class BranchBundleCompanion(BaseModel):
    """Yes/no (or N-way) question routes to one of multiple child templates.

    At draft time the engine pauses and asks the question; the user's
    answer selects which option's child gets attached.
    """
    model_config = ConfigDict(extra="forbid")
    kind: Literal["branch"] = "branch"
    label: str = Field(
        description='Author-facing label, e.g. "Certificate of Service".',
    )
    question: str = Field(
        description='Asked at draft time as a small modal, e.g. "Includes a Notice of Hearing?".',
    )
    options: list[BranchOption] = Field(
        min_length=2,
        description="At least two options — typically Yes and No.",
    )


BundleCompanion = FixedBundleCompanion | BranchBundleCompanion


# ─── Runtime: per-companion context threaded into a child's pipeline ──


class ParentBundleContext(BaseModel):
    """Runtime context the bundling engine threads into a child's pipeline.

    Built once per scheduled child (per companion) by `run_bundle` after
    the parent fully resolves and finalizes. The child's
    InheritFromParentResolver reads this object to dispatch each slot's
    fill strategy from `slot_configurations`:

      - `parent_variable` → look up by name in `resolved_values`.
      - `extract_from_draft` → LLM call against `draft_text`.
      - `literal` → use the companion's hardcoded string.

    Fields:
        resolved_values: Map from the parent's variable name to its
            resolved string value. Sourced from the parent's
            ResolvedTemplateValue list at finalize time.
        draft_text: Plain-text rendering of the parent's filled docx.
            Used as the source material for `extract_from_draft` slots
            so the LLM sees the actual filed prose (the FILED title,
            real case numbers, real names) rather than the template
            authoring markers.
        slot_configurations: The parent companion's per-slot config —
            one entry per `inherit_from_parent` variable on the child.
    """
    model_config = ConfigDict(extra="forbid")
    resolved_values: dict[str, str] = Field(default_factory=dict)
    draft_text: str = Field(default="")
    slot_configurations: dict[str, SlotConfig] = Field(default_factory=dict)


# ─── Runtime: caller-supplied branch picks (FE → BE on draft / dry-run) ──


class BundlePicks(BaseModel):
    """Caller-supplied picks for every branch companion on a parent template.

    Sent in the dry-run / draft request body so the engine knows which
    `BranchOption` to schedule for each `BranchBundleCompanion`. Fixed
    companions don't appear here — they always run.

    `picks` is keyed by the companion's index in the parent's
    `bundle_companions` list (stringified — JSON keys must be strings),
    and the value is the `BranchOption.label` chosen by the user (e.g.
    "Yes" / "No"). The engine matches the label back to its option to
    locate the child template and slot configurations.
    """
    model_config = ConfigDict(extra="forbid")
    picks: dict[str, str] = Field(default_factory=dict)
