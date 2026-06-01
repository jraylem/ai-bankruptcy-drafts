"""Draft-agent data-fetching pipeline.

The draft agent (src/core/agents/llm/draft/agent.py) takes a list of
FetchedContext objects as input — one per template field, each carrying
the raw data retrieved from the field's configured source. This package
is what actually retrieves that data by orchestrating tool calls through
the canonical toolbox surface.

Public operations on `DraftContextService`:

    DraftContextService.build(agent_config, case_id) -> DraftAgentContext
        Pair a template-bound AgentConfig with runtime case context
        (case_number + the three per-case pgvector collection names pulled
        from the Case row) so downstream tool calls can scope email / vector
        searches to a specific case.

    DraftContextService.fetch_static(draft_context) -> list[FetchedContext]
        Pass 1 of the topological fetch. Dispatches every source whose
        params can be evaluated without waiting on another variable's
        resolved value — no `{{var}}` references in query strings, no
        `dependent_variables` list.

    DraftContextService.fetch_with_substitution(draft_context) -> list[FetchedContext]
        Pass 2. Dispatches the deferred sources from Pass 1, substituting
        `{{var}}` refs in query strings from `draft_context.resolved_by_name`
        and feeding the chip composer the same lookup directly. Pipeline.py
        populates that map after running DraftAgent + DateHealingResolver +
        SystemValueResolver on Pass 1's output.

    DraftContextService.fetch(draft_context) -> list[FetchedContext]
        Back-compat shim for legacy callers; runs both passes back-to-back.

Adding a new source is a single registry entry in `_SOURCE_HANDLERS`
(in `handlers.py`) plus a small handler function — no new if-elif branch
needed.

Internal layout:
  - `types.py` — `FetchedContext`, `DraftAgentContext`, `SourceHandler` alias.
  - `handlers.py` — per-source `_handle_*` functions + `_SOURCE_HANDLERS` registry.
  - `service.py` — `DraftContextService` + the `_field_needs_resolved_values` helper.
"""

from .handlers import (
    _CASE_VECTOR_TEXT_QUERY_SOURCES,
    _EMAIL_COURT_DRIVE_SOURCES,
    _EMAIL_GMAIL_SOURCES,
    _SOURCE_HANDLERS,
    _STRUCTURED_CONSTANTS_SHORT_CODES,
    _fetch_email_with_vector_fallback,
    _handle_case_vector_auto_query,
    _handle_case_vector_text_query,
    _handle_constants,
    _handle_court_drive_email,
    _handle_gmail_email,
    _handle_law_practice_vector,
    _handle_multi_select_from_case_vector,
    _handle_multi_select_from_gmail,
    _handle_reco_chips_from_dependent_variables,
    _is_empty_email_result,
)
from .service import DraftContextService, _field_needs_resolved_values
from .types import DraftAgentContext, FetchedContext, SourceHandler

__all__ = [
    "DraftAgentContext",
    "DraftContextService",
    "FetchedContext",
    "SourceHandler",
    "_CASE_VECTOR_TEXT_QUERY_SOURCES",
    "_EMAIL_COURT_DRIVE_SOURCES",
    "_EMAIL_GMAIL_SOURCES",
    "_SOURCE_HANDLERS",
    "_STRUCTURED_CONSTANTS_SHORT_CODES",
    "_fetch_email_with_vector_fallback",
    "_field_needs_resolved_values",
    "_handle_case_vector_auto_query",
    "_handle_case_vector_text_query",
    "_handle_constants",
    "_handle_court_drive_email",
    "_handle_gmail_email",
    "_handle_law_practice_vector",
    "_handle_multi_select_from_case_vector",
    "_handle_multi_select_from_gmail",
    "_handle_reco_chips_from_dependent_variables",
    "_is_empty_email_result",
]
