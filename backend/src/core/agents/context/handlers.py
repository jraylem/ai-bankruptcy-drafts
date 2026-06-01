"""Per-source fetch handlers + the `_SOURCE_HANDLERS` dispatch registry.

Each handler accepts `(field, draft_context)` and returns the raw payload
to be wrapped in a `FetchedContext` (or None to skip). Adding a new source
is a registry entry plus a small handler — no if-elif branch in the
service layer.
"""

import logging
from typing import Any

from src.core.common.services.email import EmailType
from src.core.common.storage.database import ReferenceDataRepository
from src.core.common.toolbox import ToolBox

from ..types.sources import (
    CaseVectorSourceParams,
    FieldSource,
    MultiSelectFromCaseVectorSourceParams,
    MultiSelectFromGmailSourceParams,
    RecoChipsFromDependentVariablesSourceParams,
)
from ..types.spec import TemplateField
from .types import DraftAgentContext, SourceHandler

logger = logging.getLogger(__name__)


def _is_empty_email_result(result: Any) -> bool:
    return result is None or not getattr(result, "emails", None)


async def _fetch_email_with_vector_fallback(
    email_type: EmailType,
    subject_query: str | None,
    body_query: str | None,
    case_number: str | None,
    fallback_collection: str | None,
) -> Any:
    """Query the email backend live, falling back to the per-case pgvector collection.

    The fallback fires when the live call returns empty and a fallback
    query can be derived. Shared by all GMAIL- and COURT_DRIVE-sourced
    fields (plain, group-dropdown, reco-chips, dropdown) — the backend is
    selected by email_type, the fallback corpus by fallback_collection.
    """
    raw_result = await ToolBox.query_email(
        email_type=email_type,
        subject_query=subject_query,
        body_query=body_query,
        case_number=case_number,
    )
    if _is_empty_email_result(raw_result) and fallback_collection:
        fallback_query = subject_query or body_query or ""
        if fallback_query:
            raw_result = await ToolBox.query_case_specific(
                collection_name=fallback_collection,
                query=fallback_query,
                k=5,
            )
    return raw_result


async def _handle_gmail_email(field: TemplateField, ctx: DraftAgentContext) -> Any:
    """Fetch Gmail emails live with per-case gmail_collection fallback.

    Used by every Gmail-backed field variant (plain, group-dropdown,
    reco-chips, dropdown). Each variant's source_params exposes
    `subject_query` and `body_query`.

    `scope_to_current_case=True` (default) ANDs the case-number variants
    into the live Gmail query. Cross-case templates set it to `False` so
    the query-builder skips that AND-clause; authors typically pair this
    with `body_query="...{{prior_case_number}}..."` to reach into another
    case's email thread.
    """
    p = field.source_params
    case_number = ctx.case_number if getattr(p, "scope_to_current_case", True) else None
    return await _fetch_email_with_vector_fallback(
        EmailType.GMAIL,
        getattr(p, "subject_query", None),
        getattr(p, "body_query", None),
        case_number,
        ctx.gmail_collection,
    )


async def _handle_court_drive_email(field: TemplateField, ctx: DraftAgentContext) -> Any:
    """Fetch Court Drive emails live with per-case courtdrive_collection fallback.

    `scope_to_current_case` semantics mirror `_handle_gmail_email`."""
    p = field.source_params
    case_number = ctx.case_number if getattr(p, "scope_to_current_case", True) else None
    return await _fetch_email_with_vector_fallback(
        EmailType.COURT_DRIVE,
        getattr(p, "subject_query", None),
        getattr(p, "body_query", None),
        case_number,
        ctx.courtdrive_collection,
    )


async def _handle_case_vector_text_query(field: TemplateField, ctx: DraftAgentContext) -> Any:
    """Similarity-search the case_file collection with the author-supplied `text_query`.

    Used by RECO_CHIPS_FROM_CASE_VECTOR and DROPDOWN_FROM_CASE_VECTOR —
    both carry an explicit `text_query` on source_params.
    """
    if not ctx.case_file_collection:
        return None
    text_query = getattr(field.source_params, "text_query", None)
    if not text_query:
        return None
    return await ToolBox.query_case_specific(
        collection_name=ctx.case_file_collection,
        query=text_query,
        k=5,
    )


async def _handle_case_vector_auto_query(field: TemplateField, ctx: DraftAgentContext) -> Any:
    """Similarity-search the case_file collection.

    By default the query is auto-derived from the field's `property_name`
    (e.g. `debtor_name` → `"debtor name"`). When the field carries an
    explicit `CaseVectorSourceParams.text_query`, that string is used
    instead — useful when the variable name doesn't match the case-file
    phrasing, or when the author needs `{{var}}` substitution to reach
    across cases (e.g. `text_query="Schedule I {{prior_case_number}}"`).
    """
    if not ctx.case_file_collection:
        return None
    p = field.source_params
    explicit = getattr(p, "text_query", None) if isinstance(p, CaseVectorSourceParams) else None
    query = explicit.strip() if isinstance(explicit, str) and explicit.strip() else field.property_name.replace("_", " ")
    return await ToolBox.query_case_specific(
        collection_name=ctx.case_file_collection,
        query=query,
        k=5,
    )


async def _handle_reco_chips_from_dependent_variables(
    field: TemplateField, ctx: DraftAgentContext
) -> Any:
    """Emit a marker FetchedContext for a chip-from-deps variable.

    The actual composition (looking up dependent_variables in
    `resolved_by_name`) happens in `UserInputResolver.apply` — by then
    BOTH Pass 1 and Pass 2 LLM_DRAFT values are resolved, so dependents
    targeting Pass-2 LLM_DRAFT fields work correctly. If we composed
    here in Pass 2 fetch (before the second DraftAgent), Pass-2 LLM_DRAFT
    deps would still be missing and the chip envelope would never emit.

    The marker dict is intentionally non-None so a `FetchedContext`
    exists for `UserInputResolver` to find when iterating chip jobs.
    """
    p = field.source_params
    if not isinstance(p, RecoChipsFromDependentVariablesSourceParams):
        return None
    return {"__deferred_chip_compose__": True}


async def _handle_multi_select_from_case_vector(
    field: TemplateField, ctx: DraftAgentContext
) -> Any:
    """Similarity-search the case_file collection with the author-supplied `text_query`.

    Fetches up to k=10 chunks (more than the typical k=5 because
    multi-pick options expect more variety per query). At user-input
    apply-time the existing DropdownAgent extracts up to ~20 distinct
    option strings from these chunks matching the source's
    `example_format`.
    """
    if not ctx.case_file_collection:
        return None
    p = field.source_params
    if not isinstance(p, MultiSelectFromCaseVectorSourceParams):
        return None
    text_query = (p.text_query or "").strip()
    if not text_query:
        return None
    return await ToolBox.query_case_specific(
        collection_name=ctx.case_file_collection,
        query=text_query,
        k=10,
    )


async def _handle_multi_select_from_gmail(
    field: TemplateField, ctx: DraftAgentContext
) -> Any:
    """Search Gmail for the case's correspondence backing this multi-select.

    Mirrors the plain `gmail` raw-lookup handler shape: ANDs case-number
    variants into the live Gmail query (toggleable via
    `scope_to_current_case`), and falls back to the per-case
    `gmail_collection` pgvector when the live API returns empty. At
    user-input apply-time the DropdownAgent extracts up to ~20 distinct
    option strings matching `example_formats`.

    Used for multi-picks whose options live in case email correspondence
    (e.g. creditors from Proof of Claim filings, dockets from clerk
    notices).
    """
    p = field.source_params
    if not isinstance(p, MultiSelectFromGmailSourceParams):
        return None
    case_number = ctx.case_number if p.scope_to_current_case else None
    return await _fetch_email_with_vector_fallback(
        EmailType.GMAIL,
        p.subject_query,
        p.body_query,
        case_number,
        ctx.gmail_collection,
    )


async def _handle_law_practice_vector(field: TemplateField, _ctx: DraftAgentContext) -> Any:
    """[MOCK] Placeholder for law-practice KB lookups.

    ToolBox.query_law_practice returns a stub until the real KB collection
    is wired — see the TODO in VectorQueryService.query_law_practice.
    """
    text_query = getattr(field.source_params, "text_query", None)
    if not text_query:
        return None
    return await ToolBox.query_law_practice(text_query)


_STRUCTURED_CONSTANTS_SHORT_CODES = {"ATTORNEYS"}


async def _handle_constants(field: TemplateField, _ctx: DraftAgentContext) -> Any:
    """Fetch a reusable constant by short_code from the ReferenceData table.

    Guards against reserved short_codes whose `value` column is structured
    JSON (currently the ATTORNEYS roster). Those should never resolve via
    `constants` — they belong to `dropdown_from_constants`. Returning None
    here forces downstream code to treat the field as unresolved rather than
    inject a JSON blob into a draft.
    """
    short_code = getattr(field.source_params, "short_code", None)
    if not short_code:
        return None
    if short_code in _STRUCTURED_CONSTANTS_SHORT_CODES:
        logger.warning(
            "Ignoring constants fetch for structured short_code '%s'; "
            "this reference_data row is a reserved list and must be referenced "
            "via dropdown_from_constants, not constants.",
            short_code,
        )
        return None
    ref_data = await ReferenceDataRepository.get(short_code)
    return ref_data.value if ref_data else None


_EMAIL_GMAIL_SOURCES: tuple[FieldSource, ...] = (
    FieldSource.GMAIL,
    FieldSource.GROUP_DROPDOWN_FROM_GMAIL,
    FieldSource.RECO_CHIPS_FROM_GMAIL,
    FieldSource.DROPDOWN_FROM_GMAIL,
)
_EMAIL_COURT_DRIVE_SOURCES: tuple[FieldSource, ...] = (
    FieldSource.COURT_DRIVE,
    FieldSource.GROUP_DROPDOWN_FROM_COURT_DRIVE,
    FieldSource.RECO_CHIPS_FROM_COURT_DRIVE,
    FieldSource.DROPDOWN_FROM_COURT_DRIVE,
)
_CASE_VECTOR_TEXT_QUERY_SOURCES: tuple[FieldSource, ...] = (
    FieldSource.RECO_CHIPS_FROM_CASE_VECTOR,
    FieldSource.DROPDOWN_FROM_CASE_VECTOR,
)


_SOURCE_HANDLERS: dict[FieldSource, SourceHandler] = {
    **{s: _handle_gmail_email for s in _EMAIL_GMAIL_SOURCES},
    **{s: _handle_court_drive_email for s in _EMAIL_COURT_DRIVE_SOURCES},
    **{s: _handle_case_vector_text_query for s in _CASE_VECTOR_TEXT_QUERY_SOURCES},
    FieldSource.CASE_VECTOR: _handle_case_vector_auto_query,
    FieldSource.LAW_PRACTICE_VECTOR: _handle_law_practice_vector,
    FieldSource.CONSTANTS: _handle_constants,
    FieldSource.RECO_CHIPS_FROM_DEPENDENT_VARIABLES: _handle_reco_chips_from_dependent_variables,
    FieldSource.MULTI_SELECT_FROM_CASE_VECTOR: _handle_multi_select_from_case_vector,
    FieldSource.MULTI_SELECT_FROM_GMAIL: _handle_multi_select_from_gmail,
}
"""Registry of source-specific fetch handlers.

Sources NOT in this map (USER_INPUT_WITH_SUPPORTING_DOCS,
AUTO_DERIVED_FROM_VARIABLE, DEPENDENT_ON_VARIABLE, SYSTEM_GENERATED) are
intentionally omitted — they are resolved by later pipeline stages that
don't need pre-fetched context. `fetch` simply skips any field whose
source has no registered handler.
"""
