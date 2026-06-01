from sqlalchemy import Column, String, DateTime, Integer, Text, ForeignKey, Boolean, Index, text as sql_text, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

Base = declarative_base()

class ReviewResults(Base):
    """Database model for bankruptcy review results."""
    __tablename__ = "review_results"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    pdf_path = Column(String, nullable=False)
    review_data = Column(Text, nullable=False)  # JSON string of review results
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)
    
    # Relationship to session
    session = relationship("Session", back_populates="review_results")

# Update Session model to include review_results relationship
class Session(Base):
    """Database model for user sessions."""
    __tablename__ = "sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=True)  # Reference to user ID (no foreign key constraint)
    firm_id = Column(String, nullable=True, index=True)  # Tenant identifier (no FK — cross-DB)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    is_active = Column(Boolean, default=True)
    
    # Relationship to PDFs
    pdfs = relationship("PDFDocument", back_populates="session", cascade="all, delete-orphan")
    
    # Relationship to chat threads
    chat_threads = relationship("ChatThread", back_populates="session", cascade="all, delete-orphan")
    
    # Relationship to review results
    review_results = relationship("ReviewResults", back_populates="session", cascade="all, delete-orphan")
    
    # Relationship to courtdrive ingestions
    courtdrive_ingestions = relationship("CourtdriveIngestion", back_populates="session", cascade="all, delete-orphan")

    # Relationship to monitored motions
    monitored_motions = relationship("MonitoredMotion", back_populates="session", cascade="all, delete-orphan")

    # Relationship to motion draft logs
    motion_draft_logs = relationship("MotionDraftLog", back_populates="session", cascade="all, delete-orphan")


class UserInboxState(Base):
    """Tracks whether a user's pending inbox has been initialized."""
    __tablename__ = "user_inbox_states"

    user_id = Column(String, primary_key=True)
    initialized_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class PDFDocument(Base):
    """Database model for uploaded PDF documents."""
    __tablename__ = "pdf_documents"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    firm_id = Column(String, nullable=True, index=True)  # Tenant identifier (no FK — cross-DB)
    filename = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)
    collection_name = Column(String, default="default_collection")
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    inbox_checked_at = Column(DateTime(timezone=True), nullable=True)
    petition_status = Column(String, nullable=True)
    source = Column(String, nullable=True)  # 'manual', 'gdrive', 'ecf', 'courtdrive'; NULL = manual (legacy)
    is_active = Column(Boolean, default=True)
    
    # Relationship to session
    session = relationship("Session", back_populates="pdfs")

class ChatThread(Base):
    """Database model for chat conversation threads."""
    __tablename__ = "chat_threads"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    firm_id = Column(String, nullable=True, index=True)  # Tenant identifier (no FK — cross-DB)
    openai_thread_id = Column(String, nullable=True)  # OpenAI thread ID
    title = Column(String, nullable=True)
    summary = Column(Text, nullable=True)
    case_number = Column(String, nullable=True)
    district = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    is_active = Column(Boolean, default=True)

    # Relationship to session
    session = relationship("Session", back_populates="chat_threads")


class ChatMessage(Base):
    """Database model for individual chat messages within a thread."""
    __tablename__ = "chat_messages"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    thread_id = Column(String, ForeignKey("chat_threads.id"), nullable=False)
    role = Column(String, nullable=False)  # 'user' | 'assistant' | 'system'
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CourtdriveIngestion(Base):
    """Database model for CourtDrive ingestion status tracking."""
    __tablename__ = "courtdrive_ingestions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    ingestion_type = Column(String, nullable=False)  # 'auto', 'specific', 'claim', or actual case_number
    status = Column(String, nullable=False)  # 'running', 'completed', 'failed'
    case_number = Column(String, nullable=True)  # Actual case number if known
    collection_name = Column(String, nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    result = Column(Text, nullable=True)  # JSON string of result data
    error_message = Column(Text, nullable=True)  # Error message if failed
    is_viewed = Column(Boolean, nullable=False, default=False, server_default=sql_text("false"))

    # Relationship to session
    session = relationship("Session", back_populates="courtdrive_ingestions")

    # Composite unique index on session_id and ingestion_type
    __table_args__ = (
        Index('idx_session_ingestion_type', 'session_id', 'ingestion_type', unique=True),
    )


class UserActivityLog(Base):
    """Tracks meaningful user actions for activity metrics and audit trail."""
    __tablename__ = "user_activity_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=True)   # nullable — some actions are system-triggered
    session_id = Column(String, nullable=True)
    firm_id = Column(String, nullable=True, index=True)  # Tenant identifier (no FK — cross-DB)
    action = Column(String, nullable=False)   # e.g. upload_pdf, summon_case, accept_case, draft_motion
    activity_metadata = Column(JSON, nullable=True)    # extra context (motion_type, case_number, etc.)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('idx_activity_user_id', 'user_id'),
        Index('idx_activity_action', 'action'),
        Index('idx_activity_created_at', 'created_at'),
    )


class MotionDraftLog(Base):
    """Tracks every drafted motion and order across its full lifecycle.

    Inserted as 'pending' when a task is queued; updated to 'completed' or
    'failed' when the worker finishes. Covers all motion types — not just
    those with corresponding orders.
    """
    __tablename__ = "motion_draft_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    firm_id = Column(String, nullable=True, index=True)  # Tenant identifier (no FK — cross-DB)
    motion_type = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False, default="pending")  # pending | completed | failed | cancelled
    case_name = Column(String, nullable=True)
    case_number = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    cos_type     = Column(String(30), nullable=True)
    # Allowed values: "WithNoticeOfHearing" | "WithoutNoticeOfHearing" | "No" | NULL

    session = relationship("Session", back_populates="motion_draft_logs")
    comments = relationship("MotionComment", back_populates="motion_draft_log", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_draft_log_session_id', 'session_id'),
        Index('idx_draft_log_status', 'status'),
        Index('idx_draft_log_motion_type', 'motion_type'),
        Index('idx_draft_log_created_at', 'created_at'),
    )


class MonitoredMotion(Base):
    """Database model for tracking motions that need order generation monitoring."""
    __tablename__ = "monitored_motions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    motion_type = Column(String(50), nullable=False)
    pending_order_type = Column(String(50), nullable=False)
    status = Column(String(20), default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    motion_metadata = Column(JSON, nullable=True)

    # Relationship to session
    session = relationship("Session", back_populates="monitored_motions")

    __table_args__ = (
        Index('idx_monitored_session_id', 'session_id'),
        Index('idx_monitored_status', 'status'),
    )


class DashboardChatMessage(Base):
    """Persisted dashboard AI chat messages per user + date-range key.

    Stores only user and assistant text turns — tool_use intermediate
    blocks are transient and never written here.
    range_key is the stable preset string ("7d" | "30d" | "today") or
    "custom:YYYY-MM-DD:YYYY-MM-DD" for custom date ranges.
    No FK to the users table — user_id is a UUID string from the auth DB.
    """
    __tablename__ = "dashboard_chat_messages"

    id         = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id    = Column(String, nullable=False)
    user_email = Column(String, nullable=True)    # denormalised for auditability — auth DB is separate
    range_key  = Column(String, nullable=False)
    role       = Column(String, nullable=False)   # "user" | "assistant"
    content    = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_dashboard_chat_user_range", "user_id", "range_key"),
    )
