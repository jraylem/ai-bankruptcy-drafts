"""AUTO_DERIVED ResolverStage — derive values from already-resolved parents.

Two derivation paths:
  - `EXTRACT_SUBSTRING` (LLM via `AutoDeriveAgent`) — for tabular row
    children that pull a piece of the parent's resolved value
    (e.g. `claim_no_title` from a `claim_row` virtual parent).
  - `PLURALIZE_BY_COUNT` (deterministic, no LLM) — for grammar derivatives
    that agree with a list-style parent's pick count (e.g. `s` suffix,
    `has`/`have`, `is`/`are`). Inspects the parent's joined string for an
    Oxford-comma plurality signal; emits one of two author-defined values.

Runs inside `finalize_run` between the R2 download and the heal pass —
by that point every primary stage has produced its values. Empty
results (parent unresolved or empty) are skipped silently.
"""

import asyncio
import logging

from ..llm.auto_derive import AutoDeriveAgent
from ..types.resolution import ResolvedTemplateValue, ResolverStage
from ..types.sources import AutoDerivedRuleEffect, AutoDerivedSourceParams
from ..types.spec import TemplateField, root_parent_stage

logger = logging.getLogger(__name__)


def _detect_plurality(joined: str) -> bool:
    """Return True when the joined string represents 2+ items.

    Tuned for `multi_select_from_*` Oxford-style joins (default `oxford=true`):
      - 1 item:  "Aidvantage on behalf of Dept of Education" → False
      - 2 items: "Bank of America and JPMorgan Chase"        → True
      - 3+ items: "Bank of America, JPMorgan Chase, and Wells Fargo" → True

    The presence of `, and ` (oxford) OR ` and ` between non-empty fragments
    is a high-precision plurality signal. We deliberately do NOT split on
    commas alone — many single creditor names contain commas
    (e.g. "Acme, Inc., on behalf of Beta") and a comma-only heuristic
    would false-positive.

    Caveat: a single legal name containing " and " (e.g. "Smith and
    Wesson, LLC") would false-positive. Mitigations are documented on
    `AutoDerivedSourceParams`.
    """
    s = (joined or "").strip()
    if not s:
        return False
    if ", and " in s:
        return True
    parts = s.split(" and ")
    return len(parts) > 1 and all(p.strip() for p in parts)


class AutoDerivedResolver:
    """Resolve AUTO_DERIVED-stage fields by deriving values from already-resolved parent variables."""

    stage = ResolverStage.AUTO_DERIVED

    @classmethod
    async def apply(
        cls,
        template_fields: list[TemplateField],
        resolved_values: list[ResolvedTemplateValue],
        *,
        only_root_stages: frozenset[ResolverStage] | None = None,
    ) -> list[ResolvedTemplateValue]:
        """Derive values for every AUTO_DERIVED_FROM_VARIABLE field.

        Iterative topological resolution: each pass dispatches every field
        whose parent IS already resolved (jobs run in parallel via
        asyncio.gather). Newly-derived values get added to the lookup table
        so their own children can resolve in the next pass. Loops until no
        progress is made.

        When `only_root_stages` is supplied, only children whose root
        parent stage (per `root_parent_stage`) is in that set are
        eligible — used by the pipeline to resolve LLM_DRAFT-parented
        children EARLY (between Pass 1 and Pass 2) so their values are
        available for `{{var}}` substitution in later LLM_DRAFT queries.
        Calls without the filter sweep everything remaining; the resolver
        is idempotent on already-resolved children.

        Cycles are caught at validate time
        (`_validate_no_resolution_cycles`); a stuck pass at runtime here
        means a parent's resolution genuinely failed earlier (logged as a
        warning, child stays unresolved).

        Returns ONLY the new derived ResolvedTemplateValues; the caller
        appends them to the existing list.
        """
        resolved_by_name = {rv.property_name: rv for rv in resolved_values}
        by_name = {f.property_name: f for f in template_fields}

        remaining: list[tuple[TemplateField, AutoDerivedSourceParams]] = []
        for field in template_fields:
            if field.stage != ResolverStage.AUTO_DERIVED:
                continue
            params = field.source_params
            if not isinstance(params, AutoDerivedSourceParams):
                continue
            if field.property_name in resolved_by_name:
                # Idempotent: already resolved in an earlier pass.
                continue
            if only_root_stages is not None:
                effective = root_parent_stage(field, by_name)  # type: ignore[arg-type]
                if effective is None or effective not in only_root_stages:
                    continue
            remaining.append((field, params))

        new_values: list[ResolvedTemplateValue] = []
        while remaining:
            ready: list[tuple[TemplateField, AutoDerivedSourceParams, ResolvedTemplateValue]] = []
            pending: list[tuple[TemplateField, AutoDerivedSourceParams]] = []
            for field, params in remaining:
                parent = resolved_by_name.get(params.dependent_variable)
                if parent is not None and bool((parent.value or "").strip()):
                    ready.append((field, params, parent))
                else:
                    pending.append((field, params))

            if not ready:
                for field, params in pending:
                    logger.warning(
                        "AutoDerivedResolver: skipping '%s' — parent '%s' unresolved or empty",
                        field.property_name,
                        params.dependent_variable,
                    )
                break

            # Split into two paths: deterministic pluralize-by-count and
            # LLM-driven extract-substring. Pluralize jobs resolve in-line
            # (sub-millisecond); substring jobs fan out via gather.
            pluralize_results: list[tuple[TemplateField, AutoDerivedSourceParams, str]] = []
            substring_jobs: list[tuple[TemplateField, AutoDerivedSourceParams, ResolvedTemplateValue]] = []
            for field, params, parent in ready:
                if params.rule_effect == AutoDerivedRuleEffect.PLURALIZE_BY_COUNT:
                    derived = (
                        params.plural_value
                        if _detect_plurality(parent.value)
                        else params.singular_value
                    ) or ""
                    pluralize_results.append((field, params, derived))
                else:
                    substring_jobs.append((field, params, parent))

            substring_values = await asyncio.gather(
                *(
                    AutoDeriveAgent.run(
                        parent_variable=params.dependent_variable,
                        parent_value=parent.value,
                        derived_marker=field.template_property_marker or "",
                        derived_context=field.template_identifying_text_match or "",
                    )
                    for field, params, parent in substring_jobs
                )
            )

            for (field, params, _), derived in zip(substring_jobs, substring_values):
                if not derived:
                    continue
                rv = ResolvedTemplateValue.high_confidence(
                    field.property_name,
                    derived,
                    f"Auto-derived from '{params.dependent_variable}'.",
                )
                resolved_by_name[field.property_name] = rv
                new_values.append(rv)

            for field, params, derived in pluralize_results:
                # Empty string is a valid pluralize output (e.g. the `s`
                # suffix in `Creditor{s}` for one creditor → singular "");
                # emit the ResolvedTemplateValue regardless so the docx
                # placeholder gets filled with "" rather than left as the
                # literal `[[s]]` token.
                rv = ResolvedTemplateValue.high_confidence(
                    field.property_name,
                    derived,
                    (
                        f"Pluralize-by-count from '{params.dependent_variable}': "
                        f"emitted {'plural' if derived == params.plural_value else 'singular'} "
                        f"value {derived!r}."
                    ),
                )
                resolved_by_name[field.property_name] = rv
                new_values.append(rv)

            remaining = pending

        return new_values
