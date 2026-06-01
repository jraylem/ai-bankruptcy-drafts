"""Pick wire types — what the FE submits during /dry-run/resume.

Discriminated by SHAPE (one value vs many values vs text+files), NOT
by source kind. The server already knows the field's source via
`template_fields[var_name].params.source` and decides how to interpret
the pick from there (chip picks go through prose heal, date picks
normalize to firm format, supporting-docs picks polish against
attached files, etc.).

Carry-over invariant from v1: keeps the wire schema small — a dropdown
pick and a plain-text pick are IDENTICAL on the wire (`{value: "..."}`)
because the server already knows the family from the field's source.

v1's GroupDropdownPick is dropped — v2 has no group dropdowns (per
the source taxonomy goal: 25 → 8 sources, no group_dropdown_from_*).
"""

from __future__ import annotations

from typing import Union

from pydantic import BaseModel, ConfigDict, Field


class SingleValuePickV2(BaseModel):
    """One-value pick.

    Wire payload: ``{value: "Acme Bank — $1,200"}``.

    Used by every single-value family:
    - gmail / case_file with `presentation_shape = "dropdown"` (extractor's
      `submit_options` returned a list; paralegal picked one)
    - gmail / case_file with `presentation_shape = "chip"` (paralegal
      picked or edited a suggestion)
    - attorney with `presentation_shape = "dropdown"` (paralegal picked
      from the firm ATTORNEYS roster)
    - author_input with `kind = "plain_text"` (free text)
    - author_input with `kind = "date"` (ISO 8601 string; BE date-heals
      to firm-default `%B %-d, %Y`)
    """

    model_config = ConfigDict(extra="forbid")

    value: str


class MultiSelectPickV2(BaseModel):
    """Many-value pick.

    Wire payload: ``{picked_values: ["A", "B", ...]}``.

    Used by every multi-value family:
    - gmail / case_file with `presentation_shape = "multi_select"`
    - attorney with `presentation_shape = "multi_select"`

    `expand_picks_v2` dedupes case-insensitively, validates
    `min_picks` / `max_picks`, and Oxford-comma-joins the picks into a
    single prose string for the resolved `value`. Each pick's
    `raw_context` is preserved by joining the source slices with
    `\\n---\\n` before sending to derived children.
    """

    model_config = ConfigDict(extra="forbid")

    picked_values: list[str] = Field(default_factory=list)


class SupportingDocsPickV2(BaseModel):
    """Text + files pick.

    Wire payload: ``{user_text: "...", file_urls: ["https://r2/...", ...]}``.

    Used exclusively by author_input with `kind = "with_docs"` — the
    paralegal types a hardship narrative / explanation and attaches
    supporting documentation. Server-side `expand_picks_v2`:
    1. Validates every `file_url` is scoped to the case's R2 prefix
       (security: no cross-case file references).
    2. Downloads each file via `r2_service.download_by_key`.
    3. Runs `ExplanationEnhanceAgentV2` to polish `user_text` against
       the docs' content (e.g. cross-reference dates / dollar amounts
       from the attached statements into the narrative).
    """

    model_config = ConfigDict(extra="forbid")

    user_text: str
    file_urls: list[str] = Field(default_factory=list)


UserSelectionV2 = Union[SingleValuePickV2, MultiSelectPickV2, SupportingDocsPickV2]
"""Discriminated by Python type. The /dry-run/resume + /drafting/{id}/
submit-input routes receive a dict keyed by template_variable name
mapping to one of these shapes. Pydantic discrimination happens via
the presence/absence of each shape's distinctive field — `value` vs
`picked_values` vs `user_text` + `file_urls`."""
