"""Database operations for CourtDrive ingestion status tracking."""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.orm import selectinload
from ..chatbot.database import AsyncSessionLocal
from ..chatbot.models import CourtdriveIngestion
from ..config import settings

logger = logging.getLogger(__name__)

# Create sync engine for sync operations (used in background tasks)
# Convert asyncpg URL to psycopg for sync operations (psycopg-binary is installed)
sync_database_url = settings.CHAT_DATABASE_URL.replace("+asyncpg", "+psycopg")

sync_engine = create_engine(
    sync_database_url,
    pool_pre_ping=True,
    pool_recycle=300,
    echo=False
)
SyncSessionLocal = sessionmaker(bind=sync_engine, expire_on_commit=False)


async def get_ingestion_status(session_id: str, ingestion_type: str) -> Optional[Dict]:
    """Get ingestion status from database."""
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(CourtdriveIngestion)
                .where(
                    CourtdriveIngestion.session_id == session_id,
                    CourtdriveIngestion.ingestion_type == ingestion_type
                )
            )
            ingestion = result.scalar_one_or_none()
            
            if not ingestion:
                return None
            
            return {
                "session_id": ingestion.session_id,
                "ingestion_type": ingestion.ingestion_type,
                "status": ingestion.status,
                "case_number": ingestion.case_number,
                "collection_name": ingestion.collection_name,
                "started_at": ingestion.started_at.isoformat() if ingestion.started_at else None,
                "completed_at": ingestion.completed_at.isoformat() if ingestion.completed_at else None,
                "result": json.loads(ingestion.result) if ingestion.result else None,
                "error_message": ingestion.error_message,
                "is_viewed": bool(getattr(ingestion, "is_viewed", False)),
            }
        except Exception as e:
            logger.error("Failed to get ingestion status from database: %s", e)
            return None


async def create_or_update_ingestion(
    session_id: str,
    ingestion_type: str,
    status: str,
    collection_name: str,
    case_number: Optional[str] = None,
    result: Optional[Dict] = None,
    error_message: Optional[str] = None,
    is_viewed: Optional[bool] = None,
) -> bool:
    """Create or update ingestion status in database."""
    async with AsyncSessionLocal() as db:
        try:
            # Check if ingestion exists
            result_query = await db.execute(
                select(CourtdriveIngestion)
                .where(
                    CourtdriveIngestion.session_id == session_id,
                    CourtdriveIngestion.ingestion_type == ingestion_type
                )
            )
            ingestion = result_query.scalar_one_or_none()
            
            if ingestion:
                # Update existing
                ingestion.status = status
                ingestion.collection_name = collection_name
                if case_number:
                    ingestion.case_number = case_number
                if status == "completed" or status == "failed":
                    ingestion.completed_at = datetime.now()
                if result:
                    ingestion.result = json.dumps(result)
                if error_message:
                    ingestion.error_message = error_message
                if is_viewed is not None:
                    ingestion.is_viewed = is_viewed
            else:
                # Create new
                ingestion = CourtdriveIngestion(
                    session_id=session_id,
                    ingestion_type=ingestion_type,
                    status=status,
                    collection_name=collection_name,
                    case_number=case_number,
                    result=json.dumps(result) if result else None,
                    error_message=error_message,
                    is_viewed=bool(is_viewed) if is_viewed is not None else False,
                )
                if status == "completed" or status == "failed":
                    ingestion.completed_at = datetime.now()
                db.add(ingestion)
            
            await db.commit()
            return True
        except Exception as e:
            await db.rollback()
            logger.error("Failed to save ingestion status to database: %s", e)
            return False


async def get_all_ingestions_for_session(session_id: str) -> list[Dict]:
    """Get all ingestions for a session."""
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(CourtdriveIngestion)
                .where(CourtdriveIngestion.session_id == session_id)
            )
            ingestions = result.scalars().all()
            
            return [
                {
                    "session_id": ing.session_id,
                    "ingestion_type": ing.ingestion_type,
                    "status": ing.status,
                    "case_number": ing.case_number,
                    "collection_name": ing.collection_name,
                    "started_at": ing.started_at.isoformat() if ing.started_at else None,
                    "completed_at": ing.completed_at.isoformat() if ing.completed_at else None,
                    "result": json.loads(ing.result) if ing.result else None,
                    "error_message": ing.error_message,
                    "is_viewed": bool(getattr(ing, "is_viewed", False)),
                }
                for ing in ingestions
            ]
        except Exception as e:
            logger.error("Failed to get ingestions for session: %s", e)
            return []


async def list_pending_acceptance_view_states(session_ids: list[str]) -> dict[str, bool]:
    """Return pending-acceptance viewed flags keyed by session_id."""
    if not session_ids:
        return {}

    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(CourtdriveIngestion.session_id, CourtdriveIngestion.is_viewed)
                .where(
                    CourtdriveIngestion.ingestion_type == "pending_acceptance",
                    CourtdriveIngestion.session_id.in_(session_ids),
                )
            )
            return {row[0]: bool(row[1]) for row in result.all() if row[0]}
        except Exception as e:
            logger.error("Failed to load pending-acceptance view states: %s", e)
            return {}


async def list_pending_acceptance_states(session_ids: list[str]) -> dict[str, Dict]:
    """Return pending-acceptance ingestion state keyed by session_id."""
    if not session_ids:
        return {}

    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(CourtdriveIngestion)
                .where(
                    CourtdriveIngestion.ingestion_type == "pending_acceptance",
                    CourtdriveIngestion.session_id.in_(session_ids),
                )
            )
            ingestions = result.scalars().all()
            return {
                ingestion.session_id: {
                    "session_id": ingestion.session_id,
                    "status": ingestion.status,
                    "case_number": ingestion.case_number,
                    "collection_name": ingestion.collection_name,
                    "result": json.loads(ingestion.result) if ingestion.result else None,
                    "is_viewed": bool(getattr(ingestion, "is_viewed", False)),
                }
                for ingestion in ingestions
                if ingestion.session_id
            }
        except Exception as e:
            logger.error("Failed to load pending-acceptance states: %s", e)
            return {}


async def mark_pending_acceptance_viewed(session_id: str, is_viewed: bool = True) -> bool:
    """Persist viewed state for a pending petition candidate."""
    async with AsyncSessionLocal() as db:
        try:
            result_query = await db.execute(
                select(CourtdriveIngestion)
                .where(
                    CourtdriveIngestion.session_id == session_id,
                    CourtdriveIngestion.ingestion_type == "pending_acceptance",
                )
            )
            ingestion = result_query.scalar_one_or_none()

            if ingestion:
                ingestion.is_viewed = is_viewed
            else:
                ingestion = CourtdriveIngestion(
                    session_id=session_id,
                    ingestion_type="pending_acceptance",
                    status="pending_acceptance",
                    collection_name=f"case_candidates_{session_id}",
                    is_viewed=is_viewed,
                )
                db.add(ingestion)

            await db.commit()
            return True
        except Exception as e:
            await db.rollback()
            logger.error("Failed to update pending-acceptance viewed state: %s", e)
            return False


async def cleanup_old_ingestions(hours: int = 24) -> int:
    """Clean up ingestion records older than specified hours. Returns count of deleted records."""
    from sqlalchemy import delete
    async with AsyncSessionLocal() as db:
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            
            result = await db.execute(
                delete(CourtdriveIngestion)
                .where(
                    CourtdriveIngestion.status.in_(["completed", "failed"]),
                    CourtdriveIngestion.completed_at < cutoff_time
                )
            )
            
            await db.commit()
            return result.rowcount
        except Exception as e:
            await db.rollback()
            logger.error("Failed to cleanup old ingestions: %s", e)
            return 0


def cleanup_old_ingestions_sync(hours: int = 24) -> int:
    """Synchronous version - clean up ingestion records older than specified hours."""
    from sqlalchemy import delete
    with SyncSessionLocal() as db:
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            
            result = db.execute(
                delete(CourtdriveIngestion)
                .where(
                    CourtdriveIngestion.status.in_(["completed", "failed"]),
                    CourtdriveIngestion.completed_at < cutoff_time
                )
            )
            
            db.commit()
            return result.rowcount
        except Exception as e:
            db.rollback()
            logger.error("Failed to cleanup old ingestions (sync): %s", e)
            return 0


# Sync functions for use in synchronous code (background tasks)
# These use the sync engine directly to avoid event loop conflicts

def get_ingestion_status_sync(session_id: str, ingestion_type: str) -> Optional[Dict]:
    """Synchronous version - get ingestion status from database."""
    with SyncSessionLocal() as db:
        try:
            result = db.execute(
                select(CourtdriveIngestion)
                .where(
                    CourtdriveIngestion.session_id == session_id,
                    CourtdriveIngestion.ingestion_type == ingestion_type
                )
            )
            ingestion = result.scalar_one_or_none()
            
            if not ingestion:
                return None
            
            return {
                "session_id": ingestion.session_id,
                "ingestion_type": ingestion.ingestion_type,
                "status": ingestion.status,
                "case_number": ingestion.case_number,
                "collection_name": ingestion.collection_name,
                "started_at": ingestion.started_at.isoformat() if ingestion.started_at else None,
                "completed_at": ingestion.completed_at.isoformat() if ingestion.completed_at else None,
                "result": json.loads(ingestion.result) if ingestion.result else None,
                "error_message": ingestion.error_message,
                "is_viewed": bool(getattr(ingestion, "is_viewed", False)),
            }
        except Exception as e:
            logger.error("Failed to get ingestion status from database (sync): %s", e)
            return None


def create_or_update_ingestion_sync(
    session_id: str,
    ingestion_type: str,
    status: str,
    collection_name: str,
    case_number: Optional[str] = None,
    result: Optional[Dict] = None,
    error_message: Optional[str] = None,
    is_viewed: Optional[bool] = None,
) -> bool:
    """Synchronous version - create or update ingestion status in database."""
    with SyncSessionLocal() as db:
        try:
            # Check if ingestion exists
            result_query = db.execute(
                select(CourtdriveIngestion)
                .where(
                    CourtdriveIngestion.session_id == session_id,
                    CourtdriveIngestion.ingestion_type == ingestion_type
                )
            )
            ingestion = result_query.scalar_one_or_none()
            
            if ingestion:
                # Update existing
                ingestion.status = status
                ingestion.collection_name = collection_name
                if case_number:
                    ingestion.case_number = case_number
                if status == "completed" or status == "failed":
                    ingestion.completed_at = datetime.now()
                if result:
                    ingestion.result = json.dumps(result)
                if error_message:
                    ingestion.error_message = error_message
                if is_viewed is not None:
                    ingestion.is_viewed = is_viewed
            else:
                # Create new
                ingestion = CourtdriveIngestion(
                    session_id=session_id,
                    ingestion_type=ingestion_type,
                    status=status,
                    collection_name=collection_name,
                    case_number=case_number,
                    result=json.dumps(result) if result else None,
                    error_message=error_message,
                    is_viewed=bool(is_viewed) if is_viewed is not None else False,
                )
                if status == "completed" or status == "failed":
                    ingestion.completed_at = datetime.now()
                db.add(ingestion)
            
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            logger.error("Failed to save ingestion status to database (sync): %s", e)
            return False


def get_all_ingestions_for_session_sync(session_id: str) -> list[Dict]:
    """Synchronous version - get all ingestions for a session."""
    with SyncSessionLocal() as db:
        try:
            result = db.execute(
                select(CourtdriveIngestion)
                .where(CourtdriveIngestion.session_id == session_id)
            )
            ingestions = result.scalars().all()
            
            return [
                {
                    "session_id": ing.session_id,
                    "ingestion_type": ing.ingestion_type,
                    "status": ing.status,
                    "case_number": ing.case_number,
                    "collection_name": ing.collection_name,
                    "started_at": ing.started_at.isoformat() if ing.started_at else None,
                    "completed_at": ing.completed_at.isoformat() if ing.completed_at else None,
                    "result": json.loads(ing.result) if ing.result else None,
                    "error_message": ing.error_message
                }
                for ing in ingestions
            ]
        except Exception as e:
            logger.error("Failed to get ingestions for session (sync): %s", e)
            return []
