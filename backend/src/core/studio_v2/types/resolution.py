"""Resolved value type for the v2 pipeline.

`ResolvedTemplateValueV2` is what every resolver / extractor agent /
finalizer step in the v2 pipeline emits. It carries the final string
that substitutes into the docx PLUS `raw_context` — the source slice
(email body, pgvector chunk, paragraph) the value was extracted from.

`raw_context` is load-bearing: derived children of dropdown / chip /
multi-select picks read it instead of the cleaned display string, so
e.g. a `vin` child of a `vehicle_record` parent can extract from the
full vehicle paragraph rather than the truncated dropdown label.

v1's `ResolvedTemplateValue` is NOT imported. This is a brand-new v2
type with `raw_context` built-in from day one (in v1 it was bolted on
the side in an unrelated field).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ResolvedTemplateValueV2(BaseModel):
    """The result of resolving one template variable.

    Always emitted by the pipeline — even unresolvable fields emit a
    row with empty `value` and a warning in the finalizer's warnings
    list. That keeps `resolved_by_name` a complete map for derive +
    fill stages downstream.
    """

    model_config = ConfigDict(extra="forbid")

    template_variable: str
    value: str = ""
    # The verbatim source slice this value came from (Gmail body chunk,
    # case-file pgvector chunk, etc.). Capped at 2k chars to bound the
    # per-row token cost when a derived child reads it. EMPTY for
    # source kinds that have no chunk (current_date, constants,
    # author_input plain_text/date) — derive children fall back to
    # `value` when raw_context is empty.
    raw_context: str = Field(default="", max_length=2000)
    # Resolver / agent confidence in the value. "high" = deterministic
    # or strong LLM signal; "medium" = LLM extracted with some
    # uncertainty; "low" = best-effort; "none" = couldn't resolve.
    confidence: str = "high"
    # Free-form note attached to the value — surfaced in warnings when
    # confidence < high, used in debug traces in the dry-run result modal.
    note: str = ""
