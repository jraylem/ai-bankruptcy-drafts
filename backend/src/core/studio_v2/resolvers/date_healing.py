"""DateHealingResolverV2 — deterministic date normalizer for the v2
finalizer.

Walks the list of resolved values and rewrites any string that parses
as a date in one of the recognized formats into the firm-default
`%B %-d, %Y` rendering (e.g. "01/21/2026" → "January 21, 2026").

NO LLM call. Pure regex + `datetime.strptime`. v1's
`DateHealingResolver` is the structural inspiration; this class is
brand-new under the v2 namespace and imports nothing from v1.

Runs BEFORE `UserInputHealAgentV2` in the finalizer pipeline. That
ordering matters because the user-input heal pass receives
already-normalized date values and its prompt tells the LLM not to
touch date strings — so dates stay formatted regardless of source
(current_date / author_input date / LLM-drafted dates from gmail or
case_file / derived dates).

Behavior Contract #6 (from Phase 0): the firm-default date format is
BE policy. The wizard never lets paralegals set it. `date_format` on
WizardSourceParams is preserved on the field for v1 back-compat shape
but is NEVER read by this resolver — every date heals to the firm
default regardless.
"""

from __future__ import annotations

import re
from datetime import datetime

from ..types.resolution import ResolvedTemplateValueV2


# Firm-default rendering for every healed date. Lives here (rather than
# pulling from WizardSourceParams) precisely because the field's own
# `date_format` is BE-advisory; the heal pass owns the actual format.
DEFAULT_DATE_FORMAT_V2 = "%B %-d, %Y"


# Recognized input formats. Ordered roughly by likelihood-of-occurrence
# in our paralegals' source material (US date conventions first).
#
# 2-digit year variants use `%y` — Python's pivot is 00-68 → 20xx,
# 69-99 → 19xx (firm material is forward-looking, so this is fine).
_DATE_PARSE_FORMATS_V2: tuple[str, ...] = (
    "%m/%d/%Y",       # 04/30/2026
    "%m/%d/%y",       # 04/30/26
    "%Y-%m-%d",       # 2026-04-30 (ISO)
    "%Y/%m/%d",       # 2026/04/30
    "%m-%d-%Y",       # 04-30-2026 (US)
    "%m-%d-%y",       # 04-30-26
    "%d-%m-%Y",       # 30-04-2026
    "%B %d, %Y",      # April 30, 2026
    "%b %d, %Y",      # Apr 30, 2026
    "%d %B %Y",       # 30 April 2026
    "%d %b %Y",       # 30 Apr 2026
)


_MONTH_NAMES = (
    "January|February|March|April|May|June|July|August|September|"
    "October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|"
    "Sept|Oct|Nov|Dec"
)

# Ordinal suffixes to strip before parsing ("January 21st, 2026" → "January 21, 2026").
_ORDINAL_RE = re.compile(r"(\d+)(?:st|nd|rd|th)\b", flags=re.IGNORECASE)

# Patterns for finding date substrings embedded in larger strings.
# Each pattern's matches are passed back through `_try_parse_date_v2`
# to confirm + reformat. Patterns are intentionally narrow (word
# boundaries, year-length pinned) to avoid false positives like
# version numbers or fractional values.
#
# 4-digit-year patterns come BEFORE 2-digit-year patterns so the longer
# match wins on overlap (the dedupe in `_normalize_embedded_dates`
# keeps the first span when two overlap with the same start).
_EMBEDDED_DATE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b\d{4}-\d{1,2}-\d{1,2}\b"),                # 2026-04-30
    re.compile(r"\b\d{4}/\d{1,2}/\d{1,2}\b"),                # 2026/04/30
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b"),                # 4/30/2026
    re.compile(r"\b\d{1,2}-\d{1,2}-\d{4}\b"),                # 4-30-2026
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{2}\b"),                # 4/30/26
    re.compile(r"\b\d{1,2}-\d{1,2}-\d{2}\b"),                # 4-30-26
    re.compile(rf"\b(?:{_MONTH_NAMES})\.? \d{{1,2}}(?:st|nd|rd|th)?, \d{{4}}\b"),  # April 30, 2026 / January 21st, 2026
    re.compile(rf"\b\d{{1,2}}(?:st|nd|rd|th)? (?:{_MONTH_NAMES})\.? \d{{4}}\b"),   # 30 April 2026 / 21st January 2026
)


def _try_parse_date_v2(value: str) -> datetime | None:
    """Try every recognized format; return the first match or None.

    Strips trailing punctuation, ordinal suffixes ("21st" → "21"), and
    abbreviation periods on month names ("Mar." → "Mar") before
    attempting to parse — these are common variants the LLM emits.
    """
    stripped = value.strip().rstrip(".,;:")
    if not stripped:
        return None
    # "January 21st, 2026" → "January 21, 2026"
    stripped = _ORDINAL_RE.sub(r"\1", stripped)
    # "Mar. 20, 2026" → "Mar 20, 2026"
    stripped = re.sub(r"\b([A-Za-z]{3,9})\.", r"\1", stripped)
    for fmt in _DATE_PARSE_FORMATS_V2:
        try:
            return datetime.strptime(stripped, fmt)
        except ValueError:
            continue
    return None


def _normalize_embedded_dates(value: str) -> str:
    """Find every date substring inside `value` and rewrite each match
    to the firm-default format. Non-date substrings pass through.

    A substring is treated as a date when one of the narrow patterns
    above matches AND the matched span parses via `_try_parse_date_v2`.
    Already-normalized dates (matching `DEFAULT_DATE_FORMAT_V2`) are
    detected via the "Month D, YYYY" pattern but the rewrite is a
    no-op because the parsed `strftime(DEFAULT)` equals the source.
    """
    spans: list[tuple[int, int, str]] = []  # (start, end, replacement)
    for pattern in _EMBEDDED_DATE_PATTERNS:
        for match in pattern.finditer(value):
            parsed = _try_parse_date_v2(match.group(0))
            if parsed is None:
                continue
            replacement = parsed.strftime(DEFAULT_DATE_FORMAT_V2)
            spans.append((match.start(), match.end(), replacement))

    if not spans:
        return value

    # Drop overlapping spans (longer match wins; if equal, earlier wins).
    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    keep: list[tuple[int, int, str]] = []
    cursor = -1
    for start, end, replacement in spans:
        if start < cursor:
            continue
        keep.append((start, end, replacement))
        cursor = end

    out: list[str] = []
    pos = 0
    for start, end, replacement in keep:
        out.append(value[pos:start])
        out.append(replacement)
        pos = end
    out.append(value[pos:])
    return "".join(out)


class DateHealingResolverV2:
    """Post-processor that normalizes date-like values to the
    firm-default rendering.

    Stateless; every method is a classmethod. Runs in
    `finalize_run_v2` before `UserInputHealAgentV2`.
    """

    @classmethod
    def apply(
        cls,
        values: list[ResolvedTemplateValueV2],
    ) -> list[ResolvedTemplateValueV2]:
        """Return a new list with date-like values normalized to
        `DEFAULT_DATE_FORMAT_V2`.

        Non-date values pass through unchanged. Values whose rendering
        already equals the canonical format are returned as-is. When a
        value IS rewritten, the row's `note` is appended with the
        original string so the original extraction stays auditable in
        debug traces.
        """
        healed: list[ResolvedTemplateValueV2] = []
        for rv in values:
            if not rv.value:
                healed.append(rv)
                continue

            # Fast path: whole-value match. Cheap, handles the common
            # case where the LLM extracted exactly a date string.
            parsed = _try_parse_date_v2(rv.value)
            if parsed is not None:
                normalized = parsed.strftime(DEFAULT_DATE_FORMAT_V2)
                if normalized != rv.value:
                    healed.append(
                        rv.model_copy(
                            update={
                                "value": normalized,
                                "note": _append_note(
                                    rv.note,
                                    f"date healed from '{rv.value}'",
                                ),
                            }
                        )
                    )
                    continue
                # Already normalized; pass through.
                healed.append(rv)
                continue

            # Embedded-date path: the value is a longer string with
            # one or more dates inside (e.g. "Hearing on 3/20/2026").
            rewritten = _normalize_embedded_dates(rv.value)
            if rewritten != rv.value:
                healed.append(
                    rv.model_copy(
                        update={
                            "value": rewritten,
                            "note": _append_note(
                                rv.note,
                                "embedded date(s) healed",
                            ),
                        }
                    )
                )
                continue

            healed.append(rv)
        return healed


def _append_note(existing: str, addition: str) -> str:
    """Concatenate notes with a separator; tolerate empty existing."""
    if not existing:
        return addition
    return f"{existing}; {addition}"
