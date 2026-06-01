"""Pending-input envelope types — what the BE emits when the pipeline
pauses on a user-pick field, and what the FE renders to collect the
pick.

Discriminated by `kind` (NOT by source — same shape-not-source
principle as picks). One envelope per pending field; the dry-run /
draft pipeline returns a `dict[var_name, PendingUserInputV2]` for the
FE to walk.

Mapping (source × shape) → envelope:

| Source        | Shape                       | Envelope                                            |
|---------------|-----------------------------|-----------------------------------------------------|
| gmail / case_file | dropdown                | PendingDropdownV2                                   |
| gmail / case_file | chip                    | PendingChipV2                                       |
| gmail / case_file | multi_select            | PendingMultiSelectV2                                |
| attorney      | dropdown                    | PendingAttorneyPickV2 { multi_select: false }       |
| attorney      | multi_select                | PendingAttorneyPickV2 { multi_select: true }        |
| author_input  | kind=plain_text             | PendingAuthorTextV2                                 |
| author_input  | kind=date                   | PendingAuthorDateV2                                 |
| author_input  | kind=with_docs              | PendingAuthorDocsV2                                 |

Non-user-input source kinds (constants, current_date, derived,
value_from_parent_bundle, all `raw` shapes) NEVER produce a pending
envelope — they resolve automatically.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


class PendingDropdownV2(BaseModel):
    """Dropdown of N candidates; paralegal picks ONE."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["dropdown"] = "dropdown"
    label: str
    options: list[str] = Field(default_factory=list)
    # Each option's source slice from `_ExtractedOptions.options[i].raw_context`.
    # Same length as `options` (or empty if extractor didn't return them).
    raw_contexts: list[str] = Field(default_factory=list)
    instruction: str | None = None


class PendingChipV2(BaseModel):
    """1-3 suggestion chips; paralegal picks one or edits."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["chip"] = "chip"
    label: str
    chips: list[str] = Field(default_factory=list, max_length=3)
    raw_contexts: list[str] = Field(default_factory=list)
    instruction: str | None = None


class PendingMultiSelectV2(BaseModel):
    """N candidates; paralegal picks K (between min_picks and max_picks)."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["multi_select"] = "multi_select"
    label: str
    options: list[str] = Field(default_factory=list)
    raw_contexts: list[str] = Field(default_factory=list)
    min_picks: int = 1
    max_picks: int = 5
    instruction: str | None = None


class PendingAuthorTextV2(BaseModel):
    """author_input kind=plain_text — free-form textarea."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["author_text"] = "author_text"
    label: str
    placeholder: str | None = None
    example_output_sentence: str | None = None


class PendingAuthorDateV2(BaseModel):
    """author_input kind=date — calendar picker; FE sends ISO 8601;
    BE date-heals to firm default `%B %-d, %Y`. NO format field — date
    formatting is BE policy, never user-editable (Behavior Contract #6)."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["author_date"] = "author_date"
    label: str
    placeholder: str | None = None


class PendingAuthorDocsV2(BaseModel):
    """author_input kind=with_docs — textarea + file uploader.

    `accepted_file_types` is a hint for the FE's accept attribute; the
    server validates each uploaded `file_url` against the case's R2
    prefix in `expand_picks_v2` regardless of what the FE sent.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["author_docs"] = "author_docs"
    label: str
    accepted_file_types: list[str] = Field(
        default_factory=lambda: [".pdf", ".docx", ".png", ".jpg"]
    )


class AttorneyRow(BaseModel):
    """One attorney from the firm's ATTORNEYS reference_data row.

    Shape mirrors the FE's `MOCK_ATTORNEYS` Phase 0 fixture so the
    awaiting-input modal can render the picker identically against
    real data.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    display_name: str
    bar_number: str | None = None


class PendingAttorneyPickV2(BaseModel):
    """attorney-source dropdown / multi-select. Options come from
    ATTORNEYS reference_data, NOT from an LLM extraction — the pipeline
    short-circuits the extractor entirely for this source family."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["attorney_pick"] = "attorney_pick"
    label: str
    options: list[AttorneyRow] = Field(default_factory=list)
    multi_select: bool = False
    min_picks: int = 1
    max_picks: int = 5


PendingUserInputV2 = Annotated[
    Union[
        PendingDropdownV2,
        PendingChipV2,
        PendingMultiSelectV2,
        PendingAuthorTextV2,
        PendingAuthorDateV2,
        PendingAuthorDocsV2,
        PendingAttorneyPickV2,
    ],
    Field(discriminator="kind"),
]
"""Pydantic-discriminated union — every envelope carries a unique
`kind` literal so `model_validate(...)` routes to the right subtype
without ambiguity."""
