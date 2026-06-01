"""Normalize LLM-extracted date strings to the canonical render format.

The draft agent returns values in whatever form the source material used
(e.g. '01/21/2026', '2026-01-21', 'Jan 21 2026'). Downstream consumers —
derivative_resolver.py parsing parent values and docx rendering — expect
the canonical DEFAULT_DATE_FORMAT. This module detects common date
formats and rewrites matching values. Runs after the draft agent and
before DerivativeResolver.apply.
"""

from datetime import datetime

from ..types.resolution import ResolvedTemplateValue
from ..types.sources import DEFAULT_DATE_FORMAT

_DATE_PARSE_FORMATS = [
    "%m/%d/%Y",
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d-%m-%Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%d %B %Y",
    "%d %b %Y",
]


def _try_parse_date(value: str) -> datetime | None:
    stripped = value.strip()
    if not stripped:
        return None
    for fmt in _DATE_PARSE_FORMATS:
        try:
            return datetime.strptime(stripped, fmt)
        except ValueError:
            continue
    return None


class DateHealingResolver:
    """Post-processor that normalizes LLM-extracted date strings to DEFAULT_DATE_FORMAT.

    Not tied to a single ResolverStage — runs over already-resolved values
    regardless of which stage produced them.
    """

    @classmethod
    def apply(
        cls,
        values: list[ResolvedTemplateValue],
    ) -> list[ResolvedTemplateValue]:
        """Return a new list with date-like values normalized to DEFAULT_DATE_FORMAT.

        Non-date values pass through unchanged. Values that already render
        identically to the canonical format are also unchanged. When a value
        is rewritten, the reasoning string is annotated so the original
        extraction is still traceable in logs.
        """
        healed: list[ResolvedTemplateValue] = []
        for rv in values:
            if not rv.value:
                healed.append(rv)
                continue
            parsed = _try_parse_date(rv.value)
            if parsed is None:
                healed.append(rv)
                continue
            normalized = parsed.strftime(DEFAULT_DATE_FORMAT)
            if normalized == rv.value:
                healed.append(rv)
                continue
            healed.append(
                rv.model_copy(
                    update={
                        "value": normalized,
                        "reasoning": f"{rv.reasoning} (auto-normalized date from '{rv.value}')",
                    }
                )
            )
        return healed
