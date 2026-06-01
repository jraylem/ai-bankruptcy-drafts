"""`DraftContextService` — builds + populates a `DraftAgentContext`.

Two-pass topological fetch: `fetch_static` dispatches every field whose
source can resolve without waiting on another variable; `fetch_with_substitution`
dispatches the deferred remainder after `resolved_by_name` has been
populated by Pass-1 resolvers. `fetch` is a back-compat shim that runs
both passes back-to-back.
"""

from fastapi import HTTPException

from src.core.common.storage.database import CaseRepository
from src.core.components.cases.identity import case_resource_key

from ..types.bundling import ParentBundleContext
from ..types.resolution import ResolverStage
from ..types.spec import AgentConfig, TemplateField
from ..types.sources import FieldSource
from ..utils.query_template import (
    extract_var_refs,
    extract_var_refs_from_source_params,
    substitute,
    substitute_source_params,
)
from .handlers import _SOURCE_HANDLERS
from .types import DraftAgentContext, FetchedContext


_QUERY_FIELD_NAMES_FOR_DISPLAY: tuple[str, ...] = (
    "subject_query",
    "body_query",
    "text_query",
)


def _format_resolved_query(source_params: object) -> str | None:
    """Render the substituted query string(s) for display in the DraftAgent prompt.

    Pulls non-empty query fields off `source_params` (subject_query,
    body_query, text_query) and joins them as one-per-line `key: value`
    pairs. Returns None when no query fields are present — that becomes
    a no-op on the prompt builder side.
    """
    if source_params is None:
        return None
    lines: list[str] = []
    for field_name in _QUERY_FIELD_NAMES_FOR_DISPLAY:
        value = getattr(source_params, field_name, None)
        if isinstance(value, str) and value.strip():
            lines.append(f"{field_name}: {value}")
    if not lines:
        return None
    return "\n".join(lines)


def _field_needs_resolved_values(field: TemplateField) -> bool:
    """Return True if the field's fetch must be deferred to Pass 2.

    Pass-2 fields depend on values resolved during Pass 1 — through
    `{{var}}` substitution in their query strings or instruction, or
    through explicit `dependent_variables` lists on
    `reco_chips_from_dependent_variables`. Dispatching them in Pass 1
    would either substitute empty strings (for `{{var}}` refs) or
    return None (for the chip composer).
    """
    if field.source == FieldSource.RECO_CHIPS_FROM_DEPENDENT_VARIABLES:
        return True
    if extract_var_refs_from_source_params(field.source_params):
        return True
    if extract_var_refs(field.instruction):
        return True
    return False


class DraftContextService:
    """Canonical surface for building and populating a DraftAgentContext.

    Two public staticmethods — `build` constructs the per-case runtime
    context, `fetch` iterates the template_fields and dispatches through
    the `_SOURCE_HANDLERS` registry.
    """

    @staticmethod
    async def build(
        agent_config: AgentConfig,
        case_id: str | None,
        parent_context: ParentBundleContext | None = None,
    ) -> DraftAgentContext:
        """Construct a DraftAgentContext for a single draft-agent invocation.

        When case_id is provided, loads the Case row and populates
        case_number (for case-scoped email queries) plus the three
        per-case pgvector collection names (case_file / gmail /
        courtdrive) so downstream `fetch` calls can hit the right
        collections without re-querying the DB. Raises HTTPException(404)
        if case_id is set but no active Case row matches — dry runs
        should fail fast with a clear error rather than silently
        resolving against unscoped searches.

        When case_id is None, the returned context has every per-case
        field unset and the draft agent behaves as if no case context is
        attached.

        `parent_context` is supplied ONLY when this build is part of a
        bundling run scheduling a child template — carries the parent's
        resolved values + draft text + per-slot configurations so the
        child's InheritFromParentResolver can dispatch slot filling.
        Standalone runs and the parent's own pipeline always pass None.
        """
        if not case_id:
            return DraftAgentContext(
                agent_config=agent_config,
                parent_context=parent_context,
            )

        case_row = await CaseRepository.get(case_id)
        if case_row is None:
            raise HTTPException(
                status_code=404,
                detail=f"Case '{case_id}' not found",
            )

        return DraftAgentContext(
            agent_config=agent_config,
            case_id=case_id,
            case_number=case_row.case_number,
            resource_key=case_resource_key(case_row),
            case_file_collection=case_row.case_file_collection,
            gmail_collection=case_row.gmail_collection,
            courtdrive_collection=case_row.courtdrive_collection,
            petition_pdf_url=getattr(case_row, "petition_pdf_url", None),
            case_details={
                "case_name": case_row.case_name,
                "case_number": case_row.case_number,
                "chapter": case_row.chapter,
                "court_district": case_row.court_district,
            },
            parent_context=parent_context,
        )

    @staticmethod
    async def fetch_static(draft_context: DraftAgentContext) -> list[FetchedContext]:
        """Pass 1 of the two-pass topological fetch.

        Dispatches every field whose source can fetch WITHOUT waiting for
        another variable's resolved value — i.e. no `{{var}}` references
        in any query string and no `dependent_variables` list. Returns the
        raw_results for those fields. Pipeline.py runs DraftAgent +
        DateHealingResolver + SystemValueResolver against this output to
        populate `draft_context.resolved_by_name` before Pass 2.
        """
        contexts: list[FetchedContext] = []
        for field in draft_context.agent_config.template_fields:
            if field.stage not in {ResolverStage.LLM_DRAFT, ResolverStage.USER_INPUT}:
                continue
            if _field_needs_resolved_values(field):
                continue
            handler = _SOURCE_HANDLERS.get(field.source)
            if handler is None:
                continue
            raw_result = await handler(field, draft_context)
            if raw_result is None:
                continue
            contexts.append(FetchedContext(
                property_name=field.property_name,
                source=field.source,
                raw_result=raw_result,
                instruction=field.instruction,
            ))
        return contexts

    @staticmethod
    async def fetch_with_substitution(draft_context: DraftAgentContext) -> list[FetchedContext]:
        """Pass 2 of the two-pass topological fetch.

        Dispatches every field that was deferred by `fetch_static` —
        sources with `{{var}}` refs in query fields or with explicit
        `dependent_variables` lists. `{{var}}` references in query
        strings get substituted from `draft_context.resolved_by_name`
        before the handler runs; the chip composer reads the same map
        directly via its handler.

        Also substitutes `{{var}}` in `field.instruction` and surfaces
        the substituted query string on `FetchedContext.resolved_query`
        so the DraftAgent prompt can show the LLM which specific value
        drove the search.
        """
        contexts: list[FetchedContext] = []
        resolved = draft_context.resolved_by_name or {}
        for field in draft_context.agent_config.template_fields:
            if field.stage not in {ResolverStage.LLM_DRAFT, ResolverStage.USER_INPUT}:
                continue
            if not _field_needs_resolved_values(field):
                continue
            handler = _SOURCE_HANDLERS.get(field.source)
            if handler is None:
                continue
            substituted_params = substitute_source_params(field.source_params, resolved)
            substituted_field = (
                field if substituted_params is field.source_params
                else field.model_copy(update={"source_params": substituted_params})
            )
            raw_result = await handler(substituted_field, draft_context)
            if raw_result is None:
                continue
            substituted_instruction = substitute(field.instruction, resolved)
            contexts.append(FetchedContext(
                property_name=substituted_field.property_name,
                source=substituted_field.source,
                raw_result=raw_result,
                instruction=substituted_instruction,
                resolved_query=_format_resolved_query(substituted_params),
            ))
        return contexts

    @staticmethod
    async def fetch(draft_context: DraftAgentContext) -> list[FetchedContext]:
        """Back-compat single-pass fetch.

        Equivalent to running `fetch_static` followed by `fetch_with_substitution`
        with whatever `resolved_by_name` happens to be on the context. Most
        callers should use the explicit two-pass pair from `pipeline.py`;
        this remains for legacy callers and for tests that don't run the
        full resolver chain.
        """
        static_contexts = await DraftContextService.fetch_static(draft_context)
        substituted_contexts = await DraftContextService.fetch_with_substitution(draft_context)
        return static_contexts + substituted_contexts
