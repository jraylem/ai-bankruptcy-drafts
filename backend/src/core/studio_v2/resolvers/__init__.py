"""Deterministic resolvers for the v2 pipeline.

`orchestration.dispatcher.WizardResolver` dispatches each field on
`(source, presentation_shape)` to the right resolver or extractor
agent. This package holds the deterministic resolvers (no LLM call);
the LLM extractor + heal + derive agents live under
`studio_v2/agents/`.

Resolver responsibilities:
- `current_date.resolve(...)` — system clock; date heal runs in finalizer.
- `constants.resolve(...)` — reference_data lookup by short_code.
- `attorney.resolve_static(...)` — attorney raw mode (specific attorney
  pinned to the template).
- `inherit_from_parent.resolve(...)` — value_from_parent_bundle dispatch
  on the companion's slot configurations.
- `date_healing.DateHealingResolverV2` — finalizer-stage date
  normalization to the firm-default format.

Each function returns `ResolvedTemplateValueV2` and never raises into
the pipeline — failures degrade to empty value + low confidence + a
diagnostic note.
"""

from .attorney import resolve_attorney_static
from .constants import resolve_constant
from .current_date import resolve_current_date
from .date_healing import DateHealingResolverV2
from .inherit_from_parent import resolve_inherit_from_parent
from .user_input import (
    emit_attorney_pick_envelope,
    emit_author_input_envelope,
)

__all__ = [
    "DateHealingResolverV2",
    "emit_attorney_pick_envelope",
    "emit_author_input_envelope",
    "resolve_attorney_static",
    "resolve_constant",
    "resolve_current_date",
    "resolve_inherit_from_parent",
]
