"""TemplateConfigV2 + companion bundling shapes.

Mirrors v1's bundling.ts shape 1:1 (FE plan reaffirmed this — we did
NOT invent `packet_name` or `parent_template_name`; the lead's name
IS the packet identifier, and companion ownership is derived from the
lead's `companions[]` list).

Three companion roles:
  - SINGLE         — standalone filing.
  - MASTER         — lead filing; the only role with a non-empty
                     companions list.
  - PART_OF_PACKET — companion filing; companions don't store a back
                     reference, the parent's array is the source of
                     truth for ownership.

Two companion kinds:
  - FixedCompanion  — always runs alongside the lead.
  - BranchCompanion — paralegal answers a question at draft time and
                      the right OptionN runs.

Slot configs describe how the lead fills a child variable whose
source is value_from_parent_bundle. Three kinds (paralegal-facing
labels in parens):
  - parent_variable    — "From a field"
  - extract_from_draft — "From the document"
  - literal            — "Fixed text"
"""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class TemplateRole(StrEnum):
    SINGLE = "single"
    MASTER = "master"
    PART_OF_PACKET = "part_of_packet"


class ParentVariableSlotConfig(BaseModel):
    """Lead fills the child slot from one of its own resolved variables."""
    model_config = ConfigDict(extra="forbid")

    kind: Literal["parent_variable"] = "parent_variable"
    parent_variable: str


class ExtractFromDraftSlotConfig(BaseModel):
    """Lead fills the child slot via an LLM extraction from the lead's
    rendered draft text (extract_instruction is the natural-language
    prompt the extractor follows)."""
    model_config = ConfigDict(extra="forbid")

    kind: Literal["extract_from_draft"] = "extract_from_draft"
    extract_instruction: str


class LiteralSlotConfig(BaseModel):
    """Lead fills the child slot with a hardcoded value."""
    model_config = ConfigDict(extra="forbid")

    kind: Literal["literal"] = "literal"
    literal_value: str


SlotConfig = Annotated[
    ParentVariableSlotConfig | ExtractFromDraftSlotConfig | LiteralSlotConfig,
    Field(discriminator="kind"),
]


class FixedCompanion(BaseModel):
    """Always-runs companion. Single child template, single slot map."""
    model_config = ConfigDict(extra="forbid")

    kind: Literal["fixed"] = "fixed"
    id: str
    label: str
    child_template_id: str | None = None
    slot_configurations: dict[str, SlotConfig] = Field(default_factory=dict)


class BranchOption(BaseModel):
    """One branch of a BranchCompanion question."""
    model_config = ConfigDict(extra="forbid")

    id: str
    option_label: str
    child_template_id: str | None = None
    slot_configurations: dict[str, SlotConfig] = Field(default_factory=dict)


class BranchCompanion(BaseModel):
    """Companion that asks a question at draft time and picks one
    OptionN to run based on the answer."""
    model_config = ConfigDict(extra="forbid")

    kind: Literal["branch"] = "branch"
    id: str
    label: str
    question: str
    options: list[BranchOption] = Field(default_factory=list)


BundleCompanion = Annotated[
    FixedCompanion | BranchCompanion,
    Field(discriminator="kind"),
]


class TemplateConfigV2(BaseModel):
    """Template-level config — role plus the companion list (only
    meaningful when role == MASTER)."""
    model_config = ConfigDict(extra="forbid")

    role: TemplateRole = TemplateRole.SINGLE
    companions: list[BundleCompanion] = Field(default_factory=list)
