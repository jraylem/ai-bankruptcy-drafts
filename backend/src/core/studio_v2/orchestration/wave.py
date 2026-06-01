"""Wave classification for the v2 pipeline.

A field is **wave-B** when its extraction depends on a value that
won't be known until the paralegal picks at draft time — i.e. when
its `query_dependencies` (or its derived-from-variable parent chain)
transitively reaches a USER_INPUT-rooted field. Wave-B fields are
DEFERRED to `run_resume_stages_v2` so their extractor agent sees real
dependency values in its `dependency_values` map instead of empty
strings.

A field is **wave-A** otherwise (or doesn't apply — `None` return).
Wave-A fields resolve in `run_initial_stages_v2`'s first pass.

Mirrors v1's `classify_wave` from
`src/core/agents/utils/query_template.py` in shape; v2 traverses
`query_dependencies` (a list of names) instead of v1's inline
`{{var}}` references in source params.
"""

from __future__ import annotations

from typing import Literal

from ..types.fields import TemplateFieldV2
from ..types.wizard_sources import SourceKind


# Logical "stages" — same purpose as v1's `ResolverStage` but scoped
# to the v2 source kinds. The wave classifier uses the root-parent
# stage to decide whether a field's dependency chain reaches
# USER_INPUT territory.
Stage = Literal[
    "USER_INPUT",      # gmail/case_file with pick shape, attorney pick, author_input
    "LLM_DRAFT",       # gmail/case_file with raw shape (DraftAgentV2)
    "SYSTEM",          # current_date, constants, attorney-raw, value_from_parent_bundle
    "DERIVED",         # derived_from_variable — chain through to root
    "UNKNOWN",         # params=None or unknown source — treat as non-USER_INPUT
]


_SYSTEM_SOURCES: frozenset[SourceKind] = frozenset({
    SourceKind.CURRENT_DATE,
    SourceKind.CONSTANTS,
    SourceKind.VALUE_FROM_PARENT_BUNDLE,
})


def stage_of_v2(field: TemplateFieldV2) -> Stage:
    """Map a field to its logical resolver stage.

    DERIVED fields are walked through `root_parent_stage_v2` to get
    the chain's root stage; this helper returns only the field's own
    discriminator without chasing the chain.
    """
    params = field.params
    if params is None:
        return "UNKNOWN"

    source = params.source

    if source == SourceKind.AUTHOR_INPUT:
        return "USER_INPUT"

    if source in (SourceKind.GMAIL, SourceKind.CASE_FILE):
        # Raw shape resolves via DraftAgentV2 inside the initial pass;
        # pick shapes (dropdown / chip / multi_select) produce a pending
        # envelope so they're USER_INPUT for wave purposes.
        from ..types.wizard_sources import PresentationShape
        return (
            "LLM_DRAFT"
            if params.presentation_shape == PresentationShape.RAW
            else "USER_INPUT"
        )

    if source == SourceKind.ATTORNEY:
        from ..types.wizard_sources import PresentationShape
        return (
            "SYSTEM"
            if params.presentation_shape == PresentationShape.RAW
            else "USER_INPUT"
        )

    if source in _SYSTEM_SOURCES:
        return "SYSTEM"

    if source == SourceKind.DERIVED_FROM_VARIABLE:
        return "DERIVED"

    return "UNKNOWN"


def root_parent_stage_v2(
    field: TemplateFieldV2,
    by_name: dict[str, TemplateFieldV2],
) -> Stage:
    """Walk the derived_from_variable chain and return the ROOT
    stage.

    For non-DERIVED fields, returns their own stage. For DERIVED
    fields, follows `params.dependent_variable` through `by_name` until
    the chain ends at a non-DERIVED field — that field's stage is the
    root stage.

    Cycle-safe (capped at 50 hops with a visited set). Missing
    parents → `UNKNOWN`.
    """
    seen: set[str] = set()
    current = field
    for _ in range(50):
        own = stage_of_v2(current)
        if own != "DERIVED":
            return own
        if current.params is None or not current.params.dependent_variable:
            return "UNKNOWN"
        if current.template_variable in seen:
            return "UNKNOWN"  # cycle
        seen.add(current.template_variable)
        parent_name = current.params.dependent_variable
        parent = by_name.get(parent_name)
        if parent is None:
            return "UNKNOWN"
        current = parent
    return "UNKNOWN"


def classify_wave_v2(
    field: TemplateFieldV2,
    by_name: dict[str, TemplateFieldV2],
) -> Literal["A", "B"] | None:
    """Return wave classification:

    - `"B"` when this LLM_DRAFT field's `query_dependencies`
      transitively reach a USER_INPUT-rooted field (deferred to Pass 3).
    - `"A"` when it's an LLM_DRAFT field whose deps all root to
      LLM_DRAFT / SYSTEM (runs in Pass 2 pre-pause).
    - `None` for non-LLM-extractor fields (no wave classification
      applies — they resolve via deterministic resolvers or pause as
      pending envelopes themselves).

    Non-LLM_DRAFT extractor fields (gmail/case_file dropdown / chip /
    multi_select) are USER_INPUT-stage and return `None` too — they
    themselves produce pending envelopes, so wave classification is
    irrelevant for them.
    """
    params = field.params
    if params is None:
        return None

    own_stage = stage_of_v2(field)
    if own_stage != "LLM_DRAFT":
        return None

    deps = list(params.query_dependencies or [])
    if not deps:
        return "A"

    # Walk each dependency's root stage.
    visited_deps: set[str] = set()
    queue = list(deps)
    while queue:
        name = queue.pop(0)
        if name in visited_deps:
            continue
        visited_deps.add(name)
        dep_field = by_name.get(name)
        if dep_field is None:
            # Missing dep — treat as wave-A (safest: try in pass 2;
            # extractor will see empty dependency_values for the missing
            # name and decide what to do).
            continue
        root = root_parent_stage_v2(dep_field, by_name)
        if root == "USER_INPUT":
            return "B"
        # Chase transitive query_dependencies through the dep's own deps.
        if dep_field.params and dep_field.params.query_dependencies:
            queue.extend(dep_field.params.query_dependencies)

    return "A"
