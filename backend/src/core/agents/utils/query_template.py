"""`{{variable}}` reference parsing + substitution for query strings.

Authors can embed `{{var_name}}` in `subject_query`, `body_query`, or
`text_query` source-params fields. At fetch dispatch time, each `{{x}}`
is replaced with the resolved value of variable `x`. Enables cross-case
queries like `body_query="Notice of Order {{prior_case_number}}"`.

The helper is reused by:
- `DraftContextService.fetch_with_substitution` — Pass-2 fetch in the
  topological-fetch pipeline.
- `_validate_query_template_refs_*` validators — compose-time checks that
  every `{{ref}}` names an existing variable resolvable before USER_INPUT.
- `_validate_no_resolution_cycles` — extends the auto-derive cycle graph
  with `{{var}}` reference edges.

Pattern is intentionally narrow: snake_case identifiers only. Anything
else (numeric leads, dashes, dots) is left as literal text so a stray
`{{...}}` in user prose can't accidentally trip substitution.
"""

import re
from typing import Literal

from ..types.resolution import ResolvedTemplateValue, ResolverStage
from ..types.spec import TemplateField, root_parent_stage


_VAR_REF_PATTERN = re.compile(r"\{\{([a-z_][a-z0-9_]*)\}\}")


def extract_var_refs(s: str | None) -> set[str]:
    """Return every `{{name}}` reference in `s` as a set of variable names.

    Empty / None input yields an empty set. Matches are de-duplicated."""
    if not s:
        return set()
    return set(_VAR_REF_PATTERN.findall(s))


def substitute(
    s: str | None,
    resolved_by_name: dict[str, ResolvedTemplateValue],
) -> str | None:
    """Replace each `{{name}}` in `s` with `resolved_by_name[name].value`.

    Missing references substitute to an empty string. The validator should
    have caught these at compose time, so a runtime miss means an upstream
    resolution genuinely failed and the caller should treat the resulting
    query as best-effort."""
    if not s:
        return s

    def repl(m: re.Match) -> str:
        rv = resolved_by_name.get(m.group(1))
        if rv is None or rv.value is None:
            return ""
        return rv.value

    return _VAR_REF_PATTERN.sub(repl, s)


_QUERY_FIELD_NAMES: tuple[str, ...] = ("subject_query", "body_query", "text_query")


def extract_var_refs_from_source_params(source_params: object) -> set[str]:
    """Aggregate `{{name}}` references across every supported query field.

    Walks the well-known query-field names on whatever Pydantic-ish object
    is passed. Also iterates the list-shaped `case_vector_queries`
    sub-query list (used by `reco_chips_from_dependent_variables`).

    Returns empty set when source_params is None or has no query fields."""
    if source_params is None:
        return set()
    refs: set[str] = set()
    for field_name in _QUERY_FIELD_NAMES:
        value = getattr(source_params, field_name, None)
        if isinstance(value, str):
            refs |= extract_var_refs(value)
    case_vector_queries = getattr(source_params, "case_vector_queries", None)
    if isinstance(case_vector_queries, list):
        for entry in case_vector_queries:
            entry_query = getattr(entry, "text_query", None)
            if isinstance(entry_query, str):
                refs |= extract_var_refs(entry_query)
    return refs


def classify_wave(
    field: TemplateField,
    by_name: dict[str, TemplateField],
) -> Literal["A", "B"] | None:
    """Wave-A vs Wave-B classification for LLM_DRAFT-stage fields.

    - Wave A: fires in Pass 2 (pre-pause) — every `{{var}}` reference in
      the field's source-params query strings resolves to a target whose
      effective stage is LLM_DRAFT or SYSTEM_GENERATED.
    - Wave B: fires in Pass 3 (post-pause) — at least one reference
      resolves to a USER_INPUT-rooted effective stage. The pipeline
      defers these fetches until after `UserInputResolver.expand_picks`
      and the late auto-derive pass have populated the user's picks +
      their auto_derived descendants.

    Returns None for non-LLM_DRAFT fields (the wave concept doesn't
    apply to them; they're routed by stage, not by wave).

    Missing references are skipped silently — the validator catches
    unknown refs at compose time, so a missing entry here would mean
    the spec is already invalid and resolution will fail downstream.
    """
    if field.stage != ResolverStage.LLM_DRAFT:
        return None
    for ref_name in extract_var_refs_from_source_params(field.source_params):
        target = by_name.get(ref_name)
        if target is None:
            continue
        if root_parent_stage(target, by_name) == ResolverStage.USER_INPUT:
            return "B"
    return "A"


def substitute_source_params(
    source_params: object,
    resolved_by_name: dict[str, ResolvedTemplateValue],
):
    """Return a Pydantic-model copy with every query field substituted.

    Falls back to returning the original object unchanged when there are
    no `{{ref}}` references or no `model_copy` method available. Caller is
    free to use the returned object as a drop-in replacement."""
    if source_params is None:
        return source_params
    updates: dict[str, str] = {}
    for field_name in _QUERY_FIELD_NAMES:
        current = getattr(source_params, field_name, None)
        if not isinstance(current, str):
            continue
        if not extract_var_refs(current):
            continue
        substituted = substitute(current, resolved_by_name)
        if substituted is not None and substituted != current:
            updates[field_name] = substituted
    if not updates:
        return source_params
    model_copy = getattr(source_params, "model_copy", None)
    if model_copy is None:
        return source_params
    return model_copy(update=updates)
