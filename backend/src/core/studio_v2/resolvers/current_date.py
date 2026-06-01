"""current_date resolver — reads the system clock and returns the
ISO date string. The pipeline's date-heal finalizer pass normalizes
it to the firm-default `%B %-d, %Y` format regardless of the source's
`date_format` field (Behavior Contract #6 — date formatting is BE
policy, never user-editable).
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..types.resolution import ResolvedTemplateValueV2
from ..types.wizard_sources import WizardSourceParams


def resolve_current_date(
    *,
    template_variable: str,
    params: WizardSourceParams,
    now: datetime | None = None,
) -> ResolvedTemplateValueV2:
    """Resolve a `current_date` source.

    Returns ISO-8601 (YYYY-MM-DD) — the finalizer's
    `DateHealingResolverV2` reshapes it to the firm-default format
    (`%B %-d, %Y`). The `now` parameter is for test injection; in
    production callers omit it and we use `datetime.now(timezone.utc)`.

    `params.date_format` is intentionally ignored — paralegals never
    set it through the wizard, and the heal pass overrides anything
    the BE would write.
    """
    _ = params  # accepted for signature symmetry with the other resolvers
    instant = now if now is not None else datetime.now(timezone.utc)
    iso = instant.strftime("%Y-%m-%d")
    return ResolvedTemplateValueV2(
        template_variable=template_variable,
        value=iso,
        raw_context="",
        confidence="high",
        note="current_date: system clock; finalizer will format to firm default.",
    )
