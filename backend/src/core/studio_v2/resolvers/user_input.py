"""User-input envelope emitters — produce the `PendingUserInputV2`
shape the FE's awaiting-input modal renders.

Used by `orchestration.dispatcher.WizardResolver.dispatch` for every
(source, shape) that PAUSES on a paralegal pick:

| Source       | Shape               | Envelope                                    |
|--------------|---------------------|---------------------------------------------|
| attorney     | dropdown            | PendingAttorneyPickV2 { multi_select=False }|
| attorney     | multi_select        | PendingAttorneyPickV2 { multi_select=True } |
| author_input | kind=plain_text     | PendingAuthorTextV2                         |
| author_input | kind=date           | PendingAuthorDateV2                         |
| author_input | kind=with_docs      | PendingAuthorDocsV2                         |

All emitters return Pydantic envelope instances ready to drop into
`InitialStagesResultV2.pending_inputs`. None of them call an LLM.

Companions of the pick (gmail / case_file dropdown / chip /
multi_select) are emitted by the extractor agents themselves (slice B)
— their `run(...)` returns the envelope directly.
"""

from __future__ import annotations

import logging

from src.core.common.storage.database import (
    ATTORNEYS_SHORT_CODE,
    AttorneyRosterRepository,
)

from ..types.pending import (
    AttorneyRow,
    PendingAttorneyPickV2,
    PendingAuthorDateV2,
    PendingAuthorDocsV2,
    PendingAuthorTextV2,
)
from ..types.wizard_sources import AuthorInputKind, WizardSourceParams

logger = logging.getLogger(__name__)


def _derive_label(template_variable: str, params: WizardSourceParams) -> str:
    """Use the wizard-saved `label` when set; otherwise humanize the
    variable name with a "Pick the X" / "Enter the X" template."""
    if params.label and params.label.strip():
        return params.label.strip()
    pretty = template_variable.replace("_", " ").strip()
    return f"Pick the {pretty}" if pretty else "Pick a value"


async def emit_attorney_pick_envelope(
    *,
    template_variable: str,
    params: WizardSourceParams,
    multi_select: bool,
) -> PendingAttorneyPickV2:
    """Load the firm's ATTORNEYS roster and build a
    `PendingAttorneyPickV2` envelope.

    Falls back to an empty options list on any failure (DB error,
    missing roster row) — the FE then shows an empty picker rather
    than the request 500ing.
    """
    label = _derive_label(template_variable, params)

    try:
        roster = await AttorneyRosterRepository.list()
    except Exception as err:  # noqa: BLE001
        logger.warning(
            "emit_attorney_pick_envelope: failed to load %s roster (%s); "
            "emitting empty options",
            ATTORNEYS_SHORT_CODE, err,
        )
        roster = []

    options = [
        AttorneyRow(id=att.id, display_name=att.full_name)
        for att in roster
    ]
    return PendingAttorneyPickV2(
        label=label,
        options=options,
        multi_select=multi_select,
        min_picks=params.min_picks if multi_select else 1,
        max_picks=params.max_picks if multi_select else 1,
    )


def emit_author_input_envelope(
    *,
    template_variable: str,
    params: WizardSourceParams,
) -> PendingAuthorTextV2 | PendingAuthorDateV2 | PendingAuthorDocsV2:
    """Build the right `PendingAuthor*V2` envelope per
    `params.author_input_kind`.

    Defaults to `plain_text` when `author_input_kind` is None (legacy
    spec rows from before the field was required — extremely rare in
    practice, but defensive).
    """
    label = _derive_label(template_variable, params)
    kind = params.author_input_kind or AuthorInputKind.PLAIN_TEXT

    if kind == AuthorInputKind.DATE:
        return PendingAuthorDateV2(
            label=label,
            placeholder=params.example_format or None,
        )

    if kind == AuthorInputKind.WITH_DOCS:
        return PendingAuthorDocsV2(label=label)

    # PLAIN_TEXT fallback.
    return PendingAuthorTextV2(
        label=label,
        placeholder=params.example_format or None,
        example_output_sentence=params.output_expectation or None,
    )
