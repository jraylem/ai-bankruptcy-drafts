"""Case identity + resource-key helpers.

Leaf module — pure-Python normalization helpers + a small Case-aware
lookup. Intentionally has NO imports from `src.core.agents.*` so it
can be safely imported from anywhere (pipeline, finalizer, resolvers,
service layers, etc.) without circular-dependency risk.

Three layers of identity post-Phase-1 of the unfiled-petitions epic:

  1. `cases.id` — UUID primary key. The only stable identifier for a
     case across its lifecycle. Threaded through DB foreign keys
     (case_sessions.case_id, etc.), the FE URL `/draft-v2/case/<id>`,
     and chatbot tool contexts (`ctx.case.id`).
  2. `cases.case_number` — normalized human-readable docket number
     ("26-10700"). Nullable: unfiled rows don't have one. Used for
     dedup, display, Gmail variant matching.
  3. **resource_key** — derived from a Case row to construct R2 object
     paths (`cases/<resource_key>/petition.pdf`) and pgvector collection
     names (`case_file_<resource_key>`). NOT a stored column — `case_resource_key`
     computes it from the row's other fields.

The resource_key contract:
  - Legacy migrated rows: `case.legacy_id` (the pre-UUID sanitized slug,
    e.g. `"26_10700"`). R2 objects + pgvector collections still live
    under this name, untouched by the migration.
  - New filed rows: `_sanitize_case_id(_normalize_case_number(case_number))`.
    Preserves the "resource = sanitized case_number" invariant.
  - New unfiled rows: `case.id` (UUID). They have no case_number to
    sanitize; their petition R2 object lives under the UUID.

When an unfiled case is later promoted to filed (Phase 2's
`promote_unfiled`), resource_key changes from UUID → sanitized
case_number — the promotion flow is responsible for moving the R2
object and re-materializing pgvector collections.
"""

from __future__ import annotations

import re

from fastapi import HTTPException

from src.core.common.storage.database import Case


# Matches "0:26-bk-10700" / "1:25-bk-15244-KKS" / "0 26 bk 10700"
_CASE_WITH_CHAPTER = re.compile(
    r"^(\d{1,2})[\s\-:_](\d{2})[\s\-_]bk[\s\-_](\d{4,7})(?:[\s\-_][A-Za-z]{2,5})?$",
    re.IGNORECASE,
)
# Matches "26-bk-11993" / "26 bk 11993"
_CASE_BK = re.compile(
    r"^(\d{2})[\s\-_]bk[\s\-_](\d{4,7})(?:[\s\-_][A-Za-z]{2,5})?$",
    re.IGNORECASE,
)
# Matches "26-10700" / "25-31154-KKS"
_CASE_SHORT = re.compile(
    r"^(\d{2})[\s\-_](\d{4,7})(?:[\s\-_][A-Za-z]{2,5})?$",
)


def normalize_case_number(raw: str) -> str:
    """Canonicalize any accepted case number form into 'YY-NNNNN'."""
    value = raw.strip()

    m = _CASE_WITH_CHAPTER.match(value)
    if m:
        return f"{m.group(2)}-{m.group(3)}"

    m = _CASE_BK.match(value)
    if m:
        return f"{m.group(1)}-{m.group(2)}"

    m = _CASE_SHORT.match(value)
    if m:
        return f"{m.group(1)}-{m.group(2)}"

    raise HTTPException(
        status_code=422,
        detail=f"Could not normalize case number: {raw!r}",
    )


def sanitize_case_id(normalized: str) -> str:
    """Turn 'YY-NNNNN' into a Postgres-safe collection suffix: 'YY_NNNNN'."""
    safe = re.sub(r"[^0-9A-Za-z]+", "_", normalized).strip("_").lower()
    if not safe:
        raise HTTPException(
            status_code=422,
            detail=f"Could not derive case_id from normalized case number: {normalized!r}",
        )
    return safe


def case_resource_key(case: Case) -> str:
    """Return the R2 / pgvector resource key for a Case row.

    See the module docstring for the contract. Falls back to `case.id`
    if the case_number stored on the row turns out to be unparseable
    (defensive — we normalize on insert, so this should never trip in
    practice).
    """
    if case.legacy_id:
        return case.legacy_id
    if case.case_number:
        try:
            return sanitize_case_id(normalize_case_number(case.case_number))
        except HTTPException:
            pass
    return case.id
