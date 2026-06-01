"""attorney resolver — handles the static (raw) attorney binding.

The wizard's "Attorney" source has two presentation shapes:
- `raw` (no pick) — author pins a SPECIFIC attorney via
  `params.attorney_id`. This resolver looks up the attorney's
  full_name from the ATTORNEYS reference_data row. Deterministic; no
  LLM. Handled here.
- `dropdown` / `multi_select` — the pipeline emits a
  `PendingAttorneyPickV2` envelope with the firm's full attorney
  roster as options. The paralegal picks at draft time. Handled by
  `UserInputResolverV2` in slice F (not in this module).

Reuses v1's `AttorneyRosterRepository` via read-only import.
"""

from __future__ import annotations

import logging

from src.core.common.storage.database import AttorneyRosterRepository

from ..types.resolution import ResolvedTemplateValueV2
from ..types.wizard_sources import WizardSourceParams

logger = logging.getLogger(__name__)


async def resolve_attorney_static(
    *,
    template_variable: str,
    params: WizardSourceParams,
) -> ResolvedTemplateValueV2:
    """Resolve `(source=attorney, shape=raw)` by looking up
    `params.attorney_id` in the firm's ATTORNEYS roster.

    Errors degrade gracefully — missing attorney_id, attorney row not
    found, or DB exception all produce a row with empty value + low
    confidence + a `note` describing the cause.
    """
    attorney_id = (params.attorney_id or "").strip()
    if not attorney_id:
        return ResolvedTemplateValueV2(
            template_variable=template_variable,
            value="",
            confidence="none",
            note="attorney: no attorney_id on params (paralegal must pin one)",
        )

    try:
        attorney = await AttorneyRosterRepository.get(attorney_id)
    except Exception as err:  # noqa: BLE001
        logger.warning(
            "attorney_resolver: roster lookup failed for id=%s (%s)",
            attorney_id, err,
        )
        return ResolvedTemplateValueV2(
            template_variable=template_variable,
            value="",
            confidence="none",
            note=f"attorney: roster lookup failed ({err})",
        )

    if attorney is None:
        return ResolvedTemplateValueV2(
            template_variable=template_variable,
            value="",
            confidence="none",
            note=(
                f"attorney: id '{attorney_id}' not in ATTORNEYS roster — "
                f"attorney may have been removed; re-pin via wizard."
            ),
        )

    return ResolvedTemplateValueV2(
        template_variable=template_variable,
        value=attorney.full_name,
        confidence="high",
        note=f"attorney: pinned id={attorney_id}",
    )
