"""Data classes for the draft-agent fetch pipeline.

`FetchedContext` is the per-field payload carried into the draft agent;
`DraftAgentContext` pairs an AgentConfig with the case the draft is being
resolved against. Both are constructed at dry-run execution time and never
persisted.
"""

from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field

from ..types.bundling import ParentBundleContext
from ..types.resolution import ResolvedTemplateValue
from ..types.sources import FieldSource
from ..types.spec import AgentConfig, TemplateField


class FetchedContext(BaseModel):
    """Raw context fetched from a source, to be analyzed by the draft agent."""
    property_name: str
    source: FieldSource
    raw_result: Any
    instruction: str | None = None
    resolved_query: str | None = None
    """The query string(s) used to fetch this context AFTER `{{var}}`
    substitution. Surfaced to the DraftAgent prompt so the LLM knows
    which specific value drove the vector / email search — critical
    when the raw_data contains multiple plausible matches and only the
    substituted query disambiguates them (e.g. `creditor_name`'s
    `text_query = "secured claims for {{car_model}}"` resolves to
    "secured claims for 2023 Kia Sportage", and the LLM must pick the
    matching creditor row out of N siblings)."""


class DraftAgentContext(BaseModel):
    """Runtime context for a single draft-agent invocation.

    Pairs a pure (case-agnostic) AgentConfig with the case the draft should
    resolve against. Constructed at dry-run execution time and never
    persisted. When case_id / case_number are None, email searches run
    unscoped and the vector-cache fallback is disabled.

    Fields:
        agent_config: The template-bound AgentConfig (unchanged across cases).
        case_id: Sanitized Postgres-safe identifier for the case, e.g.
            '26_10700'. Used to look up the Case row and drives the
            vector-cache fallback in DraftContextService.fetch.
        case_number: Normalized case number (e.g. '26-10700') resolved from
            the Case row at dry-run time. Threaded into query_email so that
            Gmail / Court Drive searches are scoped to this case — the query
            builder expands it into all known case-number variants
            ("26-10700" OR "26-bk-10700") and AND's them with the agent
            config's subject/body filters.
        case_file_collection: pgvector collection name for the case's
            petition / uploaded case documents. Pulled from
            Case.case_file_collection, used by CASE_VECTOR fields.
        gmail_collection: pgvector collection name for the case's ingested
            Gmail threads. Pulled from Case.gmail_collection, used as a
            fallback when the live Gmail API returns empty.
        courtdrive_collection: pgvector collection name for the case's
            ingested Court Drive emails. Pulled from
            Case.courtdrive_collection, used as a fallback when the live
            Court Drive API returns empty.
    """
    agent_config: AgentConfig
    case_id: str | None = None
    case_number: str | None = None
    resource_key: str | None = None
    """R2 / pgvector resource key for this case. Differs from `case_id`
    (the UUID PK) — derived from `Case.legacy_id` for migrated rows or
    sanitized case_number for new filed rows. R2 path construction and
    supporting-doc upload/download paths use THIS, not case_id. Built by
    DraftContextService via cases.service.case_resource_key()."""
    case_file_collection: str | None = None
    gmail_collection: str | None = None
    courtdrive_collection: str | None = None
    case_details: dict[str, str | int | None] | None = None
    petition_pdf_url: str | None = None
    """The case's petition PDF URL — used by the case_vector vision-fallback
    agent to re-extract low-confidence values directly from the rendered
    PDF (catches checkbox state, tabular data, and form layout that
    pgvector chunks lose). May be `None` for cases that haven't ingested
    a petition; the vision fallback then no-ops."""
    resolved_by_name: dict[str, ResolvedTemplateValue] = Field(default_factory=dict)
    """Lookup of variables resolved during Pass 1 (LLM_DRAFT + SYSTEM_GENERATED).

    Populated by the pipeline between Pass 1 and Pass 2 of the topological
    fetch. `fetch_with_substitution` reads this map to substitute `{{var}}`
    references in query strings AND to compose context blocks for
    `reco_chips_from_dependent_variables` sources. Empty in any code path
    that doesn't run the explicit two-pass fetch (legacy `fetch` method,
    direct unit tests of single handlers, etc.)."""
    parent_context: ParentBundleContext | None = None
    """Bundling-engine handoff. Set ONLY when this context is being built
    for a child template scheduled by a parent's bundling run; carries
    the parent's resolved values, produced draft text, and per-slot
    configurations. Read by InheritFromParentResolver to dispatch each
    slot's filling strategy. None for standalone runs and for the
    parent's own pipeline."""


SourceHandler = Callable[[TemplateField, DraftAgentContext], Awaitable[Any]]
"""Per-source fetch handler. Returns the raw result (any shape) or None to skip."""
