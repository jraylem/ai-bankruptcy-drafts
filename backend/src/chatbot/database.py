from datetime import datetime, timezone
import os
import re
import ssl
from typing import Literal
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy import text, func
from ..config import settings
from .models import Base, Session, PDFDocument, ChatThread, ChatMessage, UserInboxState, UserActivityLog, MotionDraftLog
import logging
import time
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Use NullPool for Taskiq workers to avoid connection-pool issues under concurrent tasks
_is_taskiq_worker = os.environ.get("TASKIQ_WORKER", "").lower() == "true"

def _get_db_url_and_ssl(url: str) -> tuple[str, dict]:
    """Strip SSL params from URL and return clean URL + connect_args for asyncpg."""
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)

    ssl_param = query_params.pop("ssl", [None])[0]
    query_params.pop("sslmode", None)

    new_query = urlencode(query_params, doseq=True)
    clean_url = urlunparse(parsed._replace(query=new_query))

    connect_args = {}
    if ssl_param in ("require", "true", "True", "1"):
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        connect_args["ssl"] = ssl_context

    return clean_url, connect_args

_db_url, _connect_args = _get_db_url_and_ssl(settings.CHAT_DATABASE_URL)

_engine_kwargs = {
    "echo": False,
    "connect_args": _connect_args,
}

if _is_taskiq_worker:
    _engine_kwargs["poolclass"] = NullPool
    logger.info("Using NullPool for worker database connections")
else:
    _engine_kwargs["pool_pre_ping"] = True
    _engine_kwargs["pool_recycle"] = 300

# Create async engine
engine = create_async_engine(
    _db_url,
    **_engine_kwargs,
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)
_UNSET = object()


def _normalize_utc_datetime(value: datetime | None) -> datetime | None:
    """Normalize timestamps to timezone-aware UTC before persistence."""
    if value is None:
        return None
    if getattr(value, "tzinfo", None) is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

async def get_db_session() -> AsyncSession:
    """Get a database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            await session.close()

async def init_db():
    """Initialize the database with tables."""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(
                text(
                    """
                    ALTER TABLE courtdrive_ingestions
                    ADD COLUMN IF NOT EXISTS is_viewed BOOLEAN NOT NULL DEFAULT false
                    """
                )
            )
            # v2 cost-tracking: typed polymorphic scope linkage on llm_cost_logs.
            # semantic_id is the parent entity (case_session.id / pleading_run task_id /
            # case.id / template_id); semantic_id_kind is its discriminator.
            # Aggregations in workflow_aggregates() filter on these columns.
            await conn.execute(
                text(
                    """
                    ALTER TABLE llm_cost_logs
                    ADD COLUMN IF NOT EXISTS semantic_id VARCHAR(64) NULL
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    ALTER TABLE llm_cost_logs
                    ADD COLUMN IF NOT EXISTS semantic_id_kind VARCHAR(32) NULL
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS idx_llm_cost_logs_semantic
                    ON llm_cost_logs (firm_id, semantic_id_kind, semantic_id)
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    ALTER TABLE pdf_documents
                    ADD COLUMN IF NOT EXISTS inbox_checked_at TIMESTAMPTZ NULL
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    ALTER TABLE pdf_documents
                    ADD COLUMN IF NOT EXISTS petition_status VARCHAR NULL
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    ALTER TABLE chat_threads
                    ADD COLUMN IF NOT EXISTS district VARCHAR NULL
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    ALTER TABLE draft_templates
                    ADD COLUMN IF NOT EXISTS bundle_role VARCHAR NOT NULL DEFAULT 'standalone'
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    ALTER TABLE draft_templates
                    ADD COLUMN IF NOT EXISTS bundle_companions JSONB
                    """
                )
            )
            # case_sessions / case_session_messages: the v2 chat repos
            # INSERT via raw SQL without specifying is_active, so any rows
            # created before this column had a server_default landed with
            # NULL. Backfill, set the DB default, and tighten to NOT NULL
            # so future rows can't repeat the bug.
            for table in ("case_sessions", "case_session_messages"):
                await conn.execute(
                    text(
                        f"ALTER TABLE {table} "
                        "ALTER COLUMN is_active SET DEFAULT TRUE"
                    )
                )
                await conn.execute(
                    text(
                        f"UPDATE {table} SET is_active = TRUE "
                        "WHERE is_active IS NULL"
                    )
                )
                await conn.execute(
                    text(
                        f"ALTER TABLE {table} "
                        "ALTER COLUMN is_active SET NOT NULL"
                    )
                )
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Failed to create database tables: {e}")
        raise

async def create_session(user_id: str = None, firm_id: str = None) -> Session:
    """Create a new session."""
    async with AsyncSessionLocal() as session:
        try:
            db_session = Session(user_id=user_id, firm_id=firm_id)
            session.add(db_session)
            await session.commit()
            await session.refresh(db_session)
            logger.info(f"Created new session: {db_session.id}")
            return db_session
        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to create session: {e}")
            raise

async def create_session_with_id(session_id: str, user_id: str = None, firm_id: str = None) -> Session:
    """Create a new session with a specific ID."""
    async with AsyncSessionLocal() as session:
        try:
            db_session = Session(id=session_id, user_id=user_id, firm_id=firm_id)
            session.add(db_session)
            await session.commit()
            await session.refresh(db_session)
            logger.info(f"Created new session with ID: {db_session.id}")
            return db_session
        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to create session with ID {session_id}: {e}")
            raise

async def list_all_threads(limit: int = 200, offset: int = 0, firm_id: str | None = None) -> list[ChatThread]:
    """List all active chat threads across sessions, scoped to a firm."""
    async with AsyncSessionLocal() as session:
        try:
            if firm_id:
                result = await session.execute(
                    text(
                        "SELECT * FROM chat_threads WHERE is_active = true AND firm_id = :firm_id ORDER BY updated_at DESC NULLS LAST, created_at DESC LIMIT :limit OFFSET :offset"
                    ),
                    {"limit": limit, "offset": offset, "firm_id": firm_id},
                )
            else:
                result = await session.execute(
                    text(
                        "SELECT * FROM chat_threads WHERE is_active = true ORDER BY updated_at DESC NULLS LAST, created_at DESC LIMIT :limit OFFSET :offset"
                    ),
                    {"limit": limit, "offset": offset},
                )
            rows = result.fetchall()
            return [ChatThread(**dict(r._mapping)) for r in rows]
        except Exception as e:
            logger.error(f"Failed to list all threads: {e}")
            raise

async def get_session(session_id: str) -> Session:
    """Get a session by ID."""
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                text("SELECT * FROM sessions WHERE id = :session_id AND is_active = true"),
                {"session_id": session_id}
            )
            db_session = result.fetchone()
            if db_session:
                return Session(**dict(db_session._mapping))
            return None
        except Exception as e:
            logger.error(f"Failed to get session {session_id}: {e}")
            raise

async def get_user_session(session_id: str, user_id: str) -> Session | None:
    """Get an active session owned by a specific user."""
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                text(
                    """
                    SELECT * FROM sessions
                    WHERE id = :session_id AND user_id = :user_id AND is_active = true
                    """
                ),
                {"session_id": session_id, "user_id": user_id},
            )
            db_session = result.fetchone()
            if db_session:
                return Session(**dict(db_session._mapping))
            return None
        except Exception as e:
            logger.error(f"Failed to get session {session_id} for user {user_id}: {e}")
            raise


async def get_user_inbox_initialized_at(user_id: str) -> datetime | None:
    """Return when a user's pending inbox was first initialized."""
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                text(
                    """
                    SELECT initialized_at
                    FROM user_inbox_states
                    WHERE user_id = :user_id
                    LIMIT 1
                    """
                ),
                {"user_id": user_id},
            )
            row = result.fetchone()
            if not row:
                return None
            initialized_at = row._mapping.get("initialized_at")
            if initialized_at is None:
                return None
            if getattr(initialized_at, "tzinfo", None) is None:
                return initialized_at.replace(tzinfo=timezone.utc)
            return initialized_at.astimezone(timezone.utc)
        except Exception as e:
            logger.error(f"Failed to get inbox init state for user {user_id}: {e}")
            raise


async def set_user_inbox_initialized_at(
    user_id: str,
    initialized_at: datetime | None = None,
) -> datetime:
    """Mark a user's pending inbox as initialized."""
    normalized = _normalize_utc_datetime(initialized_at or datetime.now(timezone.utc))

    async with AsyncSessionLocal() as session:
        try:
            await session.execute(
                text(
                    """
                    INSERT INTO user_inbox_states (user_id, initialized_at, created_at)
                    VALUES (:user_id, :initialized_at, now())
                    ON CONFLICT (user_id)
                    DO UPDATE SET
                        initialized_at = EXCLUDED.initialized_at,
                        updated_at = now()
                    """
                ),
                {"user_id": user_id, "initialized_at": normalized},
            )
            await session.commit()
            return normalized
        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to set inbox init state for user {user_id}: {e}")
            raise

async def get_session_pdfs(session_id: str) -> list[PDFDocument]:
    """Get all PDFs for a session."""
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                text("SELECT * FROM pdf_documents WHERE session_id = :session_id AND is_active = true"),
                {"session_id": session_id}
            )
            pdfs = result.fetchall()
            return [PDFDocument(**dict(pdf._mapping)) for pdf in pdfs]
        except Exception as e:
            logger.error(f"Failed to get PDFs for session {session_id}: {e}")
            raise


async def get_latest_session_pdf(
    session_id: str,
    include_inactive: bool = True,
) -> PDFDocument | None:
    """Get the most recently uploaded PDF for a session."""
    async with AsyncSessionLocal() as session:
        try:
            query = """
                SELECT * FROM pdf_documents
                WHERE session_id = :session_id
            """
            if not include_inactive:
                query += " AND is_active = true"
            query += " ORDER BY uploaded_at DESC NULLS LAST, id DESC LIMIT 1"

            result = await session.execute(text(query), {"session_id": session_id})
            row = result.fetchone()
            if row:
                return PDFDocument(**dict(row._mapping))
            return None
        except Exception as e:
            logger.error(f"Failed to get latest PDF for session {session_id}: {e}")
            raise

async def get_session_chat_thread(session_id: str, include_inactive: bool = False) -> ChatThread | None:
    """Get the latest chat thread for a session."""
    async with AsyncSessionLocal() as session:
        try:
            query = """
                SELECT * FROM chat_threads
                WHERE session_id = :session_id
            """
            if not include_inactive:
                query += " AND is_active = true"
            query += " ORDER BY updated_at DESC NULLS LAST, created_at DESC LIMIT 1"

            result = await session.execute(
                text(query),
                {"session_id": session_id}
            )
            thread = result.fetchone()
            if thread:
                return ChatThread(**dict(thread._mapping))
            return None
        except Exception as e:
            logger.error(f"Failed to get chat thread for session {session_id}: {e}")
            raise

async def create_or_update_chat_thread(session_id: str, openai_thread_id: str = None, firm_id: str | None = None) -> ChatThread:
    """Create or update a chat thread for a session."""
    async with AsyncSessionLocal() as session:
        try:
            # Fetch existing thread inside this session to avoid TOCTOU race
            result = await session.execute(
                text("SELECT * FROM chat_threads WHERE session_id = :session_id ORDER BY created_at ASC LIMIT 1"),
                {"session_id": session_id},
            )
            row = result.fetchone()

            if row:
                existing_thread = await session.get(ChatThread, row._mapping["id"])
                if openai_thread_id:
                    existing_thread.openai_thread_id = openai_thread_id
                existing_thread.updated_at = func.now()
                await session.commit()
                await session.refresh(existing_thread)
                return existing_thread
            else:
                # Resolve firm_id from the parent session if not explicitly supplied
                resolved_firm_id = firm_id
                if resolved_firm_id is None:
                    sess_row = await session.execute(
                        text("SELECT firm_id FROM sessions WHERE id = :sid LIMIT 1"),
                        {"sid": session_id},
                    )
                    sess_data = sess_row.fetchone()
                    if sess_data:
                        resolved_firm_id = sess_data._mapping["firm_id"]

                new_thread = ChatThread(
                    session_id=session_id,
                    openai_thread_id=openai_thread_id,
                    firm_id=resolved_firm_id,
                )
                session.add(new_thread)
                try:
                    await session.commit()
                    await session.refresh(new_thread)
                    return new_thread
                except Exception:
                    # Another concurrent request inserted first — fetch that row
                    await session.rollback()
                    result = await session.execute(
                        text("SELECT * FROM chat_threads WHERE session_id = :session_id ORDER BY created_at ASC LIMIT 1"),
                        {"session_id": session_id},
                    )
                    row = result.fetchone()
                    if row:
                        fallback_thread = await session.get(ChatThread, row._mapping["id"])
                        await session.refresh(fallback_thread)
                        return fallback_thread
                    raise
        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to create/update chat thread for session {session_id}: {e}")
            raise

async def deactivate_session(session_id: str):
    """Deactivate a session and all its associated data."""
    async with AsyncSessionLocal() as session:
        try:
            # Deactivate session
            await session.execute(
                text("UPDATE sessions SET is_active = false WHERE id = :session_id"),
                {"session_id": session_id}
            )
            
            # Deactivate associated PDFs
            await session.execute(
                text("UPDATE pdf_documents SET is_active = false WHERE session_id = :session_id"),
                {"session_id": session_id}
            )
            
            # Deactivate associated chat threads
            await session.execute(
                text("UPDATE chat_threads SET is_active = false WHERE session_id = :session_id"),
                {"session_id": session_id}
            )
            
            await session.commit()
            logger.info(f"Deactivated session: {session_id}")
        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to deactivate session {session_id}: {e}")
            raise

async def save_pdf_metadata(
    session_id: str,
    filename: str,
    original_filename: str,
    file_path: str,
    file_size: int,
    collection_name: str = "default_collection",
    inbox_checked_at: datetime | None = None,
    petition_status: str | None = "working",
    source: str | None = None,
    firm_id: str | None = None,
) -> PDFDocument:
    """Save PDF metadata to the database."""
    normalized_inbox_checked_at = _normalize_utc_datetime(inbox_checked_at)
    async with AsyncSessionLocal() as session:
        try:
            resolved_firm_id = firm_id
            if resolved_firm_id is None:
                session_row = await session.execute(
                    text("SELECT firm_id FROM sessions WHERE id = :sid LIMIT 1"),
                    {"sid": session_id},
                )
                session_data = session_row.fetchone()
                if session_data:
                    resolved_firm_id = session_data._mapping["firm_id"]

            pdf_doc = PDFDocument(
                session_id=session_id,
                firm_id=resolved_firm_id,
                filename=filename,
                original_filename=original_filename,
                file_path=file_path,
                file_size=file_size,
                collection_name=collection_name,
                inbox_checked_at=normalized_inbox_checked_at,
                petition_status=petition_status,
                source=source,
            )
            session.add(pdf_doc)
            await session.commit()
            await session.refresh(pdf_doc)
            logger.info(f"Saved PDF metadata for session {session_id}: {original_filename}")
            return pdf_doc
        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to save PDF metadata for session {session_id}: {e}")
            raise


async def create_or_update_session_pdf_metadata(
    session_id: str,
    filename: str,
    original_filename: str,
    file_path: str,
    file_size: int,
    collection_name: str = "default_collection",
    inbox_checked_at: datetime | None | object = _UNSET,
    petition_status: str | None = None,
    source: str | None = None,
    firm_id: str | None = None,
) -> PDFDocument:
    """Update the latest session PDF metadata or create one when missing."""
    normalized_inbox_checked_at = (
        _UNSET
        if inbox_checked_at is _UNSET
        else _normalize_utc_datetime(inbox_checked_at)
    )
    async with AsyncSessionLocal() as session:
        try:
            resolved_firm_id = firm_id
            if resolved_firm_id is None:
                session_row = await session.execute(
                    text("SELECT firm_id FROM sessions WHERE id = :sid LIMIT 1"),
                    {"sid": session_id},
                )
                session_data = session_row.fetchone()
                if session_data:
                    resolved_firm_id = session_data._mapping["firm_id"]

            result = await session.execute(
                text(
                    """
                    SELECT * FROM pdf_documents
                    WHERE session_id = :session_id
                    ORDER BY uploaded_at DESC NULLS LAST, id DESC
                    LIMIT 1
                    """
                ),
                {"session_id": session_id},
            )
            row = result.fetchone()

            if row:
                pdf_doc = await session.get(PDFDocument, row._mapping.get("id"))
                pdf_doc.filename = filename
                pdf_doc.original_filename = original_filename
                pdf_doc.file_path = file_path
                pdf_doc.file_size = file_size
                pdf_doc.collection_name = collection_name
                pdf_doc.is_active = True
                if normalized_inbox_checked_at is not _UNSET:
                    pdf_doc.inbox_checked_at = normalized_inbox_checked_at
                if petition_status is not None:
                    pdf_doc.petition_status = petition_status
                if source is not None:
                    pdf_doc.source = source
            else:
                pdf_doc = PDFDocument(
                    session_id=session_id,
                    firm_id=resolved_firm_id,
                    filename=filename,
                    original_filename=original_filename,
                    file_path=file_path,
                    file_size=file_size,
                    collection_name=collection_name,
                    inbox_checked_at=(
                        None
                        if normalized_inbox_checked_at is _UNSET
                        else normalized_inbox_checked_at
                    ),
                    petition_status=petition_status if petition_status is not None else "working",
                    source=source,
                )
                session.add(pdf_doc)

            await session.commit()
            await session.refresh(pdf_doc)
            return pdf_doc
        except Exception as e:
            await session.rollback()
            logger.error(
                f"Failed to create/update PDF metadata for session {session_id}: {e}"
            )
            raise


async def update_session_petition_inbox_state(
    session_id: str,
    *,
    petition_status: str | None = None,
    inbox_checked_at: datetime | None | object = _UNSET,
) -> int:
    """Update Inbox state fields on all petition records for a session."""
    normalized_inbox_checked_at = (
        _UNSET
        if inbox_checked_at is _UNSET
        else _normalize_utc_datetime(inbox_checked_at)
    )
    async with AsyncSessionLocal() as session:
        try:
            values = []
            params = {"session_id": session_id}

            if petition_status is not None:
                values.append("petition_status = :petition_status")
                params["petition_status"] = petition_status
            if normalized_inbox_checked_at is not _UNSET:
                values.append("inbox_checked_at = :inbox_checked_at")
                params["inbox_checked_at"] = normalized_inbox_checked_at
            if not values:
                return 0

            result = await session.execute(
                text(
                    f"""
                    UPDATE pdf_documents
                    SET {", ".join(values)}
                    WHERE session_id = :session_id
                    """
                ),
                params,
            )
            await session.commit()
            return int(result.rowcount or 0)
        except Exception as e:
            await session.rollback()
            logger.error(
                f"Failed to update petition inbox state for session {session_id}: {e}"
            )
            raise

async def save_chat_message(thread_id: str, role: str, content: str) -> ChatMessage:
    """Persist a chat message to the database."""
    async with AsyncSessionLocal() as session:
        try:
            message = ChatMessage(
                thread_id=thread_id,
                role=role,
                content=content
            )
            session.add(message)
            await session.commit()
            await session.refresh(message)
            return message
        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to save chat message for thread {thread_id}: {e}")
            raise

async def list_sessions(user_id: str | None = None, firm_id: str | None = None) -> list[Session]:
    """List active sessions, filtered by user_id and/or firm_id."""
    async with AsyncSessionLocal() as session:
        try:
            where_clauses = ["is_active = true"]
            params: dict = {}
            if user_id:
                where_clauses.append("user_id = :user_id")
                params["user_id"] = user_id
            if firm_id:
                where_clauses.append("firm_id = :firm_id")
                params["firm_id"] = firm_id
            where = " AND ".join(where_clauses)
            result = await session.execute(
                text(f"SELECT * FROM sessions WHERE {where} ORDER BY created_at DESC"),
                params,
            )
            rows = result.fetchall()
            return [Session(**dict(r._mapping)) for r in rows]
        except Exception as e:
            logger.error(f"Failed to list sessions: {e}")
            raise

async def list_threads(session_id: str) -> list[ChatThread]:
    """List active threads for a session."""
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                text("SELECT * FROM chat_threads WHERE session_id = :session_id AND is_active = true ORDER BY updated_at DESC, created_at DESC"),
                {"session_id": session_id}
            )
            rows = result.fetchall()
            return [ChatThread(**dict(r._mapping)) for r in rows]
        except Exception as e:
            logger.error(f"Failed to list threads for session {session_id}: {e}")
            raise

async def list_messages(
    thread_id: str,
    limit: int = 200,
    offset: int = 0,
    order: Literal["asc", "desc"] = "asc",
) -> list[ChatMessage]:
    """List messages for a thread."""
    async with AsyncSessionLocal() as session:
        try:
            order_sql = "DESC" if order == "desc" else "ASC"
            result = await session.execute(
                text(f"""
                    SELECT * FROM chat_messages 
                    WHERE thread_id = :thread_id 
                    ORDER BY created_at {order_sql}
                    LIMIT :limit OFFSET :offset
                """),
                {"thread_id": thread_id, "limit": limit, "offset": offset}
            )
            rows = result.fetchall()
            return [ChatMessage(**dict(r._mapping)) for r in rows]
        except Exception as e:
            logger.error(f"Failed to list messages for thread {thread_id}: {e}")
            raise

async def update_thread_metadata(thread_id: str, title: str | None = None, summary: str | None = None, case_number: str | None = None, district: str | None = None) -> ChatThread | None:
    """Update thread title/summary/case_number/district."""
    async with AsyncSessionLocal() as session:
        try:
            sets = []
            params = {"thread_id": thread_id}
            if title is not None:
                sets.append("title = :title")
                params["title"] = title
            if summary is not None:
                sets.append("summary = :summary")
                params["summary"] = summary
            if case_number is not None:
                sets.append("case_number = :case_number")
                params["case_number"] = case_number
            if district is not None:
                sets.append("district = :district")
                params["district"] = district
            if not sets:
                return None
            set_clause = ", ".join(sets)
            await session.execute(
                text(f"UPDATE chat_threads SET {set_clause}, updated_at = now() WHERE id = :thread_id"),
                params
            )
            await session.commit()
            # Re-read row
            result = await session.execute(
                text("SELECT * FROM chat_threads WHERE id = :thread_id"),
                {"thread_id": thread_id}
            )
            row = result.fetchone()
            return ChatThread(**dict(row._mapping)) if row else None
        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to update thread metadata {thread_id}: {e}")
            raise

async def delete_thread(thread_id: str) -> bool:
    """Soft-delete a thread: mark chat_threads inactive, remove its messages,
    and mark the session's PDFs as 'deleted' so the dashboard tracks it."""
    async with AsyncSessionLocal() as session:
        try:
            # Get session_id for this thread
            result = await session.execute(
                text("SELECT session_id FROM chat_threads WHERE id = :thread_id"),
                {"thread_id": thread_id}
            )
            row = result.fetchone()

            # Deactivate thread
            await session.execute(
                text("UPDATE chat_threads SET is_active = false WHERE id = :thread_id"),
                {"thread_id": thread_id}
            )
            # Delete messages for that thread
            await session.execute(
                text("DELETE FROM chat_messages WHERE thread_id = :thread_id"),
                {"thread_id": thread_id}
            )
            # Mark session's PDFs as deleted so dashboard can track this case
            if row and row.session_id:
                await session.execute(
                    text("UPDATE pdf_documents SET petition_status = 'deleted' WHERE session_id = :session_id"),
                    {"session_id": row.session_id}
                )
            await session.commit()
            return True
        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to delete thread {thread_id}: {e}")
            raise

async def save_review_results(session_id: str, pdf_path: str, review_results: dict) -> str:
    """Save bankruptcy review results to the database."""
    async with AsyncSessionLocal() as session:
        try:
            # Deactivate any existing review results for this session
            await session.execute(
                text("UPDATE review_results SET is_active = false WHERE session_id = :session_id"),
                {"session_id": session_id}
            )
            
            # Create new review results record
            review_id = f"review_{session_id}_{int(time.time())}"
            
            # Store the review results as JSON
            review_data_json = json.dumps(review_results)
            
            await session.execute(
                text("""
                    INSERT INTO review_results (id, session_id, pdf_path, review_data, is_active)
                    VALUES (:id, :session_id, :pdf_path, :review_data, :is_active)
                """),
                {
                    "id": review_id,
                    "session_id": session_id,
                    "pdf_path": pdf_path,
                    "review_data": review_data_json,
                    "is_active": True
                }
            )
            
            await session.commit()
            logger.info(f"Saved review results for session {session_id}")
            return review_id
        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to save review results for session {session_id}: {e}")
            raise

async def get_review_results(session_id: str, pdf_path: str) -> dict:
    """Get bankruptcy review results from the database."""
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                text("""
                    SELECT review_data FROM review_results 
                    WHERE session_id = :session_id AND pdf_path = :pdf_path AND is_active = true
                    ORDER BY created_at DESC LIMIT 1
                """),
                {"session_id": session_id, "pdf_path": pdf_path}
            )
            row = result.fetchone()
            if row and row.review_data:
                # Parse the stored JSON back to dict
                try:
                    return json.loads(row.review_data)
                except:
                    return None
            return None
        except Exception as e:
            logger.error(f"Failed to get review results for session {session_id}: {e}")
            return None

async def list_user_threads(user_id: str, limit: int = 200, offset: int = 0) -> list[ChatThread]:
    """List all active chat threads for a specific user."""
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                text(
                    """SELECT ct.* FROM chat_threads ct 
                    JOIN sessions s ON ct.session_id = s.id 
                    WHERE ct.is_active = true AND s.user_id = :user_id 
                    ORDER BY ct.updated_at DESC NULLS LAST, ct.created_at DESC 
                    LIMIT :limit OFFSET :offset"""
                ),
                {"user_id": user_id, "limit": limit, "offset": offset}
            )
            rows = result.fetchall()
            return [ChatThread(**dict(r._mapping)) for r in rows]
        except Exception as e:
            logger.error(f"Failed to list user threads: {e}")
            raise


async def log_user_action(
    action: str,
    user_id: str | None = None,
    session_id: str | None = None,
    firm_id: str | None = None,
    metadata: dict | None = None,
) -> None:
    """
    Insert a user activity log entry. Never raises — failures are logged as warnings
    so a logging error never breaks the calling request.

    Args:
        action:     Action key, e.g. 'upload_pdf', 'summon_case', 'accept_case',
                    'deny_case', 'archive_case', 'draft_motion'.
        user_id:    Authenticated user ID. Nullable for system-triggered actions.
        session_id: Related session ID. Nullable for user-level actions with no session.
        firm_id:    Tenant identifier. Nullable for anonymous/system requests.
        metadata:   Optional dict with extra context (motion_type, case_number, etc.).
    """
    try:
        async with AsyncSessionLocal() as db:
            db.add(UserActivityLog(
                user_id=user_id,
                session_id=session_id,
                firm_id=firm_id,
                action=action,
                activity_metadata=metadata,
            ))
            await db.commit()
    except Exception as e:
        logger.warning(f"[activity_log] Failed to log action '{action}' (user={user_id}): {e}")


async def get_motion_case_info(session_id: str) -> tuple[str | None, str | None]:
    """Return (case_name, case_number) for a session in a single query.
    Anchors on motion_draft_logs so the result is correct even when no chat_threads
    row exists. Falls back to chat_threads.case_number when motion_draft_logs has no
    valid XX-XXXXX case number.
    """
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                text(
                    "SELECT m.case_name, m.case_number AS mdl_case_number, "
                    "       ct.case_number AS ct_case_number "
                    "FROM motion_draft_logs m "
                    "LEFT JOIN chat_threads ct ON ct.session_id = m.session_id "
                    "WHERE m.session_id = :sid "
                    "ORDER BY m.created_at DESC "
                    "LIMIT 1"
                ),
                {"sid": session_id},
            )
            row = result.fetchone()
            if not row:
                return None, None
            case_name = row.case_name
            case_number = (
                row.mdl_case_number
                if row.mdl_case_number and re.search(r"\d{2}-\d{5}", row.mdl_case_number)
                else row.ct_case_number
            )
            return case_name, case_number
    except Exception as e:
        logger.warning(f"[get_motion_case_info] Failed for session {session_id}: {e}")
    return None, None
