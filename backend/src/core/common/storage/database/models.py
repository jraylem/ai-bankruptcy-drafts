"""SQLAlchemy ORM models backing the core database layer.

Tables today: Case (per-bankruptcy-case row, anchors pgvector collection
names), DraftTemplate (per-template row, holds template_spec + committed
agent_config), ReferenceData (reusable constants mapped to short_codes),
CaseGenerationLog (durable audit of every v2 template-draft attempt),
CaseSession + CaseSessionMessage (per-user-per-case agentic chat transcript
for the v2 drafting workspace).
"""

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from src.chatbot.models import Base


class ReferenceData(Base):
    """Database model for storing reusable reference/constant values.

    Examples: firm_phone, firm_address, attorney_name, attorney_bar_number, etc.
    These values can be used as template variable sources via CONSTANTS source type.
    """
    __tablename__ = "reference_data"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    short_code = Column(String(100), nullable=False, unique=True)
    display_name = Column(String(255), nullable=False)
    value = Column(Text, nullable=False)
    category = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    is_active = Column(Boolean, default=True)

    __table_args__ = (
        Index('idx_reference_data_short_code', 'short_code'),
        Index('idx_reference_data_category', 'category'),
    )


class DraftTemplate(Base):
    """Database model for storing draft templates and their configurations.

    Stores the template URL, generated template spec, and agent config for reuse.
    """
    __tablename__ = "draft_templates"

    id = Column(String, primary_key=True)
    name = Column(String(255), nullable=False)
    original_doc_url = Column(Text, nullable=True)
    template_doc_url = Column(Text, nullable=True)
    template_spec = Column(JSONB, nullable=True)
    agent_config = Column(JSONB, nullable=True)
    bundle_role = Column(String, nullable=False, server_default="standalone")
    bundle_companions = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    is_active = Column(Boolean, default=True)

    __table_args__ = (
        Index('idx_draft_template_name', 'name'),
    )


class Case(Base):
    """A legal case (bankruptcy petition) ingested into the system.

    Post-Phase-1 the PK is a UUID (uniform across filed + unfiled).
    Per-case pgvector collection NAMES still derive from a separate
    resource key — sanitized normalized case_number for filed cases,
    UUID id as fallback for unfiled. Legacy rows preserve their pre-UUID
    sanitized-case_number slug in `legacy_id` for back-compat URL navigation.
    """
    __tablename__ = "cases"

    id = Column(String, primary_key=True)
    firm_id = Column(String, nullable=True, index=True)
    legacy_id = Column(String(100), nullable=True, index=True)
    case_name = Column(String(255), nullable=False)
    case_number = Column(String(100), nullable=True, index=True)
    case_number_original = Column(String(255), nullable=True)
    court_district = Column(String(100), nullable=True)
    chapter = Column(Integer, nullable=True)
    petition_pdf_url = Column(Text, nullable=True)
    # Collection-name columns hold NULL on unfiled rows. Phase 2's
    # `promote_unfiled` materializes them on filing.
    case_file_collection = Column(String(255), nullable=True)
    gmail_collection = Column(String(255), nullable=True)
    courtdrive_collection = Column(String(255), nullable=True)
    # Unfiled-petition support: `status` discriminates filed vs unfiled;
    # `ssn_last4` is the matching key when an ECF notice arrives for a
    # previously-uploaded unfiled petition.
    ssn_last4 = Column(String(4), nullable=True)
    ssn_extraction_status = Column(String(16), nullable=False, default="not_found")
    status = Column(String(16), nullable=False, default="filed")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    is_active = Column(Boolean, default=True)

    __table_args__ = (
        Index('idx_cases_case_number', 'case_number'),
        Index(
            'idx_cases_firm_id', 'firm_id',
            postgresql_where=text("firm_id IS NOT NULL"),
        ),
        Index('idx_cases_status', 'status'),
        Index(
            'idx_cases_legacy_id', 'legacy_id',
            postgresql_where=text("legacy_id IS NOT NULL"),
        ),
        # Composite partial index supporting the Phase 2 unfiled-match
        # query: firm_id leads + ssn_last4 + status='unfiled'.
        Index(
            'idx_cases_ssn_match', 'firm_id', 'ssn_last4', 'status',
            postgresql_where=text(
                "status = 'unfiled' AND ssn_last4 IS NOT NULL"
            ),
        ),
        # Partial UNIQUE — case_number must be unique across all filed
        # rows; unfiled rows have NULL and are exempt by PG's default
        # NULL handling in unique indexes.
        Index(
            'uq_cases_case_number', 'case_number',
            unique=True,
            postgresql_where=text("case_number IS NOT NULL"),
        ),
    )


class CaseGenerationLog(Base):
    """Durable audit trail of every v2 template-draft attempt.

    One row per `(user_id, case_id, draft_template_id)` invocation. Backs the
    EXISTING_FOUND check at draft start and powers the per-case generation
    history view. R2 keys are stored raw — the router re-signs on read so the
    FE always receives a fresh presigned URL.
    """
    __tablename__ = "case_generation_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False)
    case_id = Column(String, nullable=False)
    draft_template_id = Column(String, nullable=False)
    template_name = Column(String(255), nullable=True)
    status = Column(String(32), nullable=False)
    r2_object_key = Column(Text, nullable=True)
    children = Column(JSONB, nullable=True)
    task_id = Column(String, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index(
            'idx_case_generation_logs_lookup',
            'case_id', 'draft_template_id', 'user_id', 'status', 'created_at',
        ),
        Index('idx_case_generation_logs_case_id', 'case_id'),
    )


class CaseSession(Base):
    """One canonical agentic-chat session per `(user_id, case_id)`.

    Backs the v2 drafting UI's chat pane. Auto-created the first time a user
    opens the case in `/draft-v2/case/<id>`. The unique constraint on
    `(user_id, case_id)` for active rows enforces "one chat per case per user"
    — a future change can drop the partial unique index to allow forking into
    multiple parallel sessions, without a schema migration of the messages
    table.
    """
    __tablename__ = "case_sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String, ForeignKey("cases.id"), nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    title = Column(String(255), nullable=False, server_default="Chat")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    # server_default="true" is load-bearing: this repo INSERTs via raw SQL
    # without specifying is_active, so the Python-side default=True never
    # fires. Without server_default the column lands as NULL and every
    # `is_active = true` filter excludes the just-inserted row.
    is_active = Column(
        Boolean, nullable=False, default=True, server_default=text("true"),
    )

    __table_args__ = (
        # Partial unique index enforces canonical-per-pair while still
        # allowing soft-deleted rows to coexist with a fresh active one.
        Index(
            'uq_case_sessions_user_case_active',
            'user_id', 'case_id',
            unique=True,
            postgresql_where=text("is_active = true"),
        ),
    )


class CaseSessionMessage(Base):
    """One row per turn in a `CaseSession` transcript.

    `role` is one of `user`, `assistant`, `tool`:
      - `user`: a user-typed prompt. `content` is the text; `thinking` /
        `tool_calls` / `tool_call_id` are null.
      - `assistant`: a model turn. `content` is the final visible text,
        `thinking` is the extended-thinking trace (nullable), and
        `tool_calls` is a JSONB list of `{id, name, input}` entries the
        model emitted on this turn (nullable when the turn was a plain
        text reply).
      - `tool`: the result of executing a tool call. `tool_call_id`
        points back to the assistant message's `tool_calls[i].id`; the
        JSON-encoded result lives in `content`.

    `sequence_number` is assigned monotonically by the repository on
    append, so ordered transcript loads are a single `ORDER BY` away.
    """
    __tablename__ = "case_session_messages"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    case_session_id = Column(
        String, ForeignKey("case_sessions.id"), nullable=False, index=True,
    )
    sequence_number = Column(Integer, nullable=False)
    role = Column(String(16), nullable=False)
    content = Column(Text, nullable=False, server_default="")
    thinking = Column(Text, nullable=True)
    tool_calls = Column(JSONB, nullable=True)
    tool_call_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # See CaseSession.is_active — same Python-default-vs-raw-INSERT trap.
    is_active = Column(
        Boolean, nullable=False, default=True, server_default=text("true"),
    )

    __table_args__ = (
        Index(
            'idx_case_session_messages_session_seq',
            'case_session_id', 'sequence_number',
        ),
    )


class LlmCostLog(Base):
    """One row per LLM (or embedding) call from src/core/.

    `firm_id` + `kind` + `created_at` are the primary aggregation axes
    for the studio's Costs panel. case_id / user_id / session_id live
    inside `log_metadata` (JSONB) so v1 schema doesn't lock us into a
    single slicing — adding a column later is harder than reading JSONB.

    `kind` taxonomy is defined in
    `src/core/common/cost_tracking/context.py::CostContext`. `model` is
    the raw Claude/OpenAI model identifier; pricing normalizes the name
    before lookup.

    Writes are best-effort: `LlmCostLogRepository.record(...)` swallows
    exceptions so cost-tracking never breaks the LLM request path.
    """
    __tablename__ = "llm_cost_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    firm_id = Column(String, nullable=True, index=True)
    kind = Column(String(32), nullable=False, index=True)
    model = Column(String(64), nullable=False)
    input_tokens = Column(Integer, nullable=False, default=0, server_default=text("0"))
    output_tokens = Column(Integer, nullable=False, default=0, server_default=text("0"))
    cache_read_tokens = Column(Integer, nullable=False, default=0, server_default=text("0"))
    cache_write_tokens = Column(Integer, nullable=False, default=0, server_default=text("0"))
    cost_usd = Column(Numeric(12, 6), nullable=False)
    run_id = Column(String(64), nullable=True)
    semantic_id = Column(String(64), nullable=True)
    semantic_id_kind = Column(String(32), nullable=True)
    log_metadata = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index(
            'idx_llm_cost_logs_firm_kind_created',
            'firm_id', 'kind', 'created_at',
        ),
        Index('idx_llm_cost_logs_created_at', 'created_at'),
        Index(
            'idx_llm_cost_logs_semantic',
            'firm_id', 'semantic_id_kind', 'semantic_id',
        ),
    )


class CaseInbox(Base):
    """Pending petitions discovered via the v2 ECF cron, awaiting paralegal action.

    One row per petition PDF the cron successfully downloaded from a PACER
    ECF notice email. Replaces the legacy `/uploads/`-scan inbox (which
    treated the filesystem as ground truth).

    Lifecycle (`status` state machine):
      ingesting → ready  →  accepted   (user accept or summon → Case row created)
                          → archived  (user dismiss or 48h timeout)
      ingesting → failed_ingest (R2 upload exhausted 3× retries)

    Visible-in-UI rules:
      - status='ready'    → main /inbox list
      - status='archived' → /inbox/archived list (recoverable via Summon)
      - other statuses    → not surfaced in v1 UI; queryable via DB

    R2 path is STABLE through the row's lifetime: `case_inbox/{id}/petition.pdf`.
    The status column carries the lifecycle, not the path. Only on `accepted`
    does the inbox key get deleted (the Case row's `cases/{case_id}/...` is the
    live artifact).
    """
    __tablename__ = "case_inbox"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    firm_id = Column(String, nullable=True, index=True)

    # Email-body-parsed metadata (display-only preview for the inbox UI;
    # LLM re-extracts the authoritative values from PDF bytes on accept).
    case_number = Column(String(100), nullable=True)
    case_name = Column(String(255), nullable=True)
    ssn_last4 = Column(String(4), nullable=True)
    ssn_extraction_status = Column(String(16), nullable=False, default="not_found")
    court_district = Column(String(10), nullable=True)

    # R2 object — stable path for the row's lifetime
    petition_r2_key = Column(String, nullable=False)

    # State machine
    status = Column(String(16), nullable=False, default="ingesting", index=True)
    failure_reason = Column(Text, nullable=True)  # populated only when status='failed_ingest'

    # Source + dedup
    source = Column(String(32), nullable=False, default="gmail_ecf")
    gmail_message_id = Column(String(128), nullable=True, index=True)
    fingerprint_sha256 = Column(String(64), nullable=True, index=True)
    received_at = Column(DateTime(timezone=True), nullable=True)

    # Audit timestamps + actor refs
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    archived_at = Column(DateTime(timezone=True), nullable=True)
    dismissed_at = Column(DateTime(timezone=True), nullable=True)
    dismissed_by_user_id = Column(String, nullable=True)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    accepted_by_user_id = Column(String, nullable=True)
    accepted_case_id = Column(String, nullable=True)

    # Phase 2 unfiled-petition match — populated at ingest time when an
    # unfiled cases row matches this notice by (firm_id, ssn_last4, fuzzy
    # name >= 85%). Re-evaluated at accept/dismiss time; the action-time
    # value is the source of truth for the merge-vs-create-new routing.
    matches_unfiled_case_id = Column(String, nullable=True)

    __table_args__ = (
        # Hot paths: ready (main inbox) + archived (summon list)
        Index('idx_case_inbox_ready', 'firm_id', postgresql_where=text("status = 'ready'")),
        Index(
            'idx_case_inbox_archived', 'firm_id', 'archived_at',
            postgresql_where=text("status = 'archived'"),
        ),
        # Summon-by-case-number search
        Index(
            'idx_case_inbox_case_number', 'firm_id', 'case_number', 'status',
            postgresql_where=text("case_number IS NOT NULL"),
        ),
        # Phase 2 matcher reverse-lookup (rare): "which inbox rows point
        # at this unfiled case?" — partial so we don't index NULLs.
        Index(
            'idx_case_inbox_matches_unfiled', 'matches_unfiled_case_id',
            postgresql_where=text("matches_unfiled_case_id IS NOT NULL"),
        ),
    )


class CaseIngestionLog(Base):
    """Per-attempt audit log of the ECF ingest cron.

    Written by `run_ingest_cycle` once per attempted PACER doc link
    (BEFORE the dedup decision so even skipped links are recorded).
    Fire-and-forget — `CaseIngestionLogRepository.record(...)` swallows
    exceptions so observability never breaks ingest itself.

    Operators query directly:
      SELECT outcome, COUNT(*) FROM case_ingestion_logs
        WHERE firm_id = $1 AND created_at >= now() - interval '24 hours'
        GROUP BY outcome;
    """
    __tablename__ = "case_ingestion_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    firm_id = Column(String, nullable=True, index=True)

    # Cycle correlation — same uuid for every row written in one cron run
    cycle_id = Column(String, nullable=True, index=True)

    # Source identifiers — populated as soon as known
    gmail_message_id = Column(String(128), nullable=True, index=True)
    case_number = Column(String(100), nullable=True)
    case_name = Column(String(255), nullable=True)
    court_district = Column(String(10), nullable=True)

    # Outcome — one of:
    #   'inserted' | 'gmail_dedup_skip' | 'fingerprint_dedup_skip'
    #   | 'dead_link' | 'r2_upload_failed' | 'db_insert_failed' | 'parse_error'
    outcome = Column(String(32), nullable=False, index=True)

    # Link to the resulting case_inbox row when outcome='inserted'
    case_inbox_id = Column(String, nullable=True)

    # Diagnostics
    error_message = Column(Text, nullable=True)
    pdf_size_bytes = Column(Integer, nullable=True)
    elapsed_ms = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('idx_case_ingestion_logs_firm_created', 'firm_id', 'created_at'),
        Index('idx_case_ingestion_logs_outcome_created', 'outcome', 'created_at'),
    )
