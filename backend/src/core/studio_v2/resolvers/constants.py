"""constants resolver — reads firm reference_data by `short_code`.

The wizard's "Firm Constant" source binds a field to a
`reference_data` row (firm address, default disclaimer, trustee
name, etc.). This resolver looks up the row at resolve time and
returns its `value`.

Reuses v1's `ReferenceDataRepository` via read-only import.
"""

from __future__ import annotations

import logging

from src.core.common.storage.database import ReferenceDataRepository

from ..types.resolution import ResolvedTemplateValueV2
from ..types.wizard_sources import WizardSourceParams

logger = logging.getLogger(__name__)


async def resolve_constant(
    *,
    template_variable: str,
    params: WizardSourceParams,
) -> ResolvedTemplateValueV2:
    """Resolve a `constants` source by looking up
    `params.constants_short_code` in `reference_data`.

    Errors degrade gracefully — missing short_code, missing reference_data
    row, or DB exception all produce a row with empty value + low
    confidence + a `note` describing the cause. Never raises into the
    pipeline.
    """
    short_code = (params.constants_short_code or "").strip()
    if not short_code:
        return ResolvedTemplateValueV2(
            template_variable=template_variable,
            value="",
            confidence="none",
            note="constants: no constants_short_code on params",
        )

    try:
        row = await ReferenceDataRepository.get(short_code)
    except Exception as err:  # noqa: BLE001 — degrade, don't crash
        logger.warning(
            "constants_resolver: lookup failed for short_code=%s (%s)",
            short_code, err,
        )
        return ResolvedTemplateValueV2(
            template_variable=template_variable,
            value="",
            confidence="none",
            note=f"constants: reference_data lookup failed ({err})",
        )

    if row is None:
        return ResolvedTemplateValueV2(
            template_variable=template_variable,
            value="",
            confidence="none",
            note=f"constants: short_code '{short_code}' not found in reference_data",
        )

    return ResolvedTemplateValueV2(
        template_variable=template_variable,
        value=(row.value or "").strip(),
        confidence="high",
        note=f"constants: {short_code}",
    )
