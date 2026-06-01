"""
Analytics sub-page: Case Lookup & KPIs.

GET /analytics/cases              → /api/dashboard/analytics/cases
GET /analytics/cases/{session_id} → /api/dashboard/analytics/cases/{session_id}

Design notes:
  - All case data lives in chat_db — no cross-database join needed except for
    resolving actor names (user identity lives in user_db).
  - KPIs are always global for the date range; list filters do not affect them.
  - Pending KPI uses _BASE_CTE bucket='pending' (global, unlike the user-scoped
    inbox count in kpis.py).
  - Archived KPI includes Google Drive "Archived Petitions" folder for consistency
    with the existing /cases KPI endpoint.
  - Timeline is assembled in Python from three batched queries (pdf_documents,
    user_activity_logs, motion_draft_logs) to avoid N+1 per list item.
  - Actor names are resolved via a single batch query against user_db after all
    chat_db queries complete (same cross-DB merge pattern as analytics_users.py).
  - The detail endpoint uses _SINGLE_SESSION_CTE — a scoped variant of _BASE_CTE
    that omits the date-range filter and classifies exactly one session using the
    identical CASE logic.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text

from ...auth.models import User
from ...common.dependencies import get_current_firm_user
from ...auth.database import UserAsyncSessionLocal
from ...chatbot.database import AsyncSessionLocal
from ...gmail.drive_service import list_archived_petition_filenames
from ._shared import (
    DateRangeParams,
    DateRangeInfo,
    _BASE_CTE,
    _MOTION_DISPLAY_NAMES,
    _build_activity_detail,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analytics"])


# ---------------------------------------------------------------------------
# Internal query functions — called by analytics_insights.py chat tools
# ---------------------------------------------------------------------------

async def _query_cases_list(
    start: datetime,
    end: datetime,
    status: Optional[str] = None,
    district: Optional[str] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: str = "created_at",
    limit: int = 20,
) -> dict:
    """
    Called by: _execute_chat_tool (analytics_insights.py)
    Returns total_count (full matching set) and up to 50 rows.
    COUNT(*) OVER () computes the total before LIMIT is applied — one query pass.
    """
    where_clauses = ["sb.bucket != 'other'"]
    list_extra: dict = {}
    range_params = {"start": start, "end": end}

    if search:
        where_clauses.append(
            "(LOWER(cm.case_number) LIKE :search_pat"
            " OR LOWER(cm.debtor_name) LIKE :search_pat"
            " OR LOWER(sb.session_id) LIKE :search_pat)"
        )
        list_extra["search_pat"] = f"%{search.strip().lower()}%"
    if status:
        where_clauses.append("sb.petition_status = :status_filter")
        list_extra["status_filter"] = status
    if district:
        where_clauses.append("cm.district = :district_filter")
        list_extra["district_filter"] = district
    if source:
        where_clauses.append("cs.source = :source_filter")
        list_extra["source_filter"] = source

    where_sql = "WHERE " + " AND ".join(where_clauses)
    sort_col = {
        "created_at": "s.created_at",
        "motions_count": "mc.motions_count",
        "last_activity_at": "la.last_activity_at",
    }.get(sort_by, "s.created_at")

    base_sql = f"""
        {_BASE_CTE},
        case_meta AS (
            SELECT DISTINCT ON (ct.session_id)
                ct.session_id, ct.case_number, ct.title AS debtor_name, ct.district
            FROM chat_threads ct ORDER BY ct.session_id, ct.created_at DESC
        ),
        case_source AS (
            SELECT DISTINCT ON (p.session_id) p.session_id, p.source
            FROM pdf_documents p ORDER BY p.session_id, p.uploaded_at DESC
        ),
        motion_counts AS (
            SELECT session_id, COUNT(*) AS motions_count
            FROM motion_draft_logs GROUP BY session_id
        ),
        last_activity AS (
            SELECT session_id, MAX(created_at) AS last_activity_at
            FROM user_activity_logs WHERE session_id IS NOT NULL GROUP BY session_id
        )
        SELECT
            sb.session_id, sb.petition_status,
            cm.case_number, cm.debtor_name, cm.district, cs.source,
            s.created_at, la.last_activity_at,
            COALESCE(mc.motions_count, 0) AS motions_count,
            COUNT(*) OVER () AS total_count
        FROM session_bucket sb
        INNER JOIN sessions s ON s.id = sb.session_id
        LEFT JOIN case_meta cm ON cm.session_id = sb.session_id
        LEFT JOIN case_source cs ON cs.session_id = sb.session_id
        LEFT JOIN motion_counts mc ON mc.session_id = sb.session_id
        LEFT JOIN last_activity la ON la.session_id = sb.session_id
        {where_sql}
    """

    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            text(f"{base_sql} ORDER BY {sort_col} DESC NULLS LAST LIMIT :limit"),
            {**range_params, **list_extra, "limit": min(limit, 50)},
        )
        all_rows = rows.fetchall()

    total_count = int(all_rows[0].total_count) if all_rows else 0

    return {
        "total_count": total_count,
        "returned": len(all_rows),
        "items": [
            {
                "session_id": str(row.session_id),
                "case_number": row.case_number,
                "debtor_name": row.debtor_name,
                "district": row.district,
                "petition_status": row.petition_status,
                "source": row.source,
                "motions_count": int(row.motions_count),
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "last_activity_at": row.last_activity_at.isoformat() if row.last_activity_at else None,
            }
            for row in all_rows
        ],
    }


async def _query_case_detail(session_id: str) -> dict:
    """
    Called by: _execute_chat_tool (analytics_insights.py)
    Full case detail: metadata + documents + last 10 motions + last 10 timeline events.
    """
    async with AsyncSessionLocal() as db:
        meta_result = await db.execute(
            text(f"""
                {_SINGLE_SESSION_CTE}
                SELECT
                    s.id AS session_id, s.created_at,
                    sb.bucket, sb.petition_status AS effective_status, sb.source,
                    ct.case_number, ct.title AS debtor_name, ct.district
                FROM sessions s
                INNER JOIN session_bucket sb ON sb.session_id = s.id
                LEFT JOIN LATERAL (
                    SELECT case_number, title, district FROM chat_threads
                    WHERE session_id = s.id ORDER BY created_at DESC LIMIT 1
                ) ct ON true
                WHERE s.id = :sid
            """),
            {"sid": session_id},
        )
        meta = meta_result.fetchone()
        if meta is None:
            return {"error": f"Session {session_id} not found"}

        docs_result = await db.execute(
            text("""
                SELECT filename, source, uploaded_at FROM pdf_documents
                WHERE session_id = :sid ORDER BY uploaded_at ASC
            """),
            {"sid": session_id},
        )

        motions_result = await db.execute(
            text("""
                SELECT motion_type, status, created_at,
                       EXTRACT(EPOCH FROM (completed_at - created_at)) AS processing_seconds
                FROM motion_draft_logs
                WHERE session_id = :sid
                ORDER BY created_at DESC LIMIT 10
            """),
            {"sid": session_id},
        )

        timeline_result = await db.execute(
            text("""
                SELECT action, created_at
                FROM user_activity_logs
                WHERE session_id = :sid
                  AND action IN ('accept_case', 'deny_case', 'archive_case',
                                 'summon_case', 'generate_document')
                ORDER BY created_at DESC LIMIT 10
            """),
            {"sid": session_id},
        )

        all_docs = docs_result.fetchall()
        all_motions = motions_result.fetchall()
        all_timeline = timeline_result.fetchall()

    return {
        "session": {
            "session_id": str(meta.session_id),
            "case_number": meta.case_number,
            "debtor_name": meta.debtor_name,
            "district": meta.district,
            "petition_status": meta.effective_status,
            "created_at": meta.created_at.isoformat() if meta.created_at else None,
        },
        "documents": [
            {
                "filename": r.filename,
                "source": r.source,
                "uploaded_at": r.uploaded_at.isoformat() if r.uploaded_at else None,
            }
            for r in all_docs
        ],
        "motions": [
            {
                "motion_type": r.motion_type,
                "display_name": _MOTION_DISPLAY_NAMES.get(r.motion_type, r.motion_type),
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "processing_seconds": (
                    round(float(r.processing_seconds), 2)
                    if r.processing_seconds is not None else None
                ),
            }
            for r in all_motions
        ],
        "timeline": [
            {
                "event_type": r.action,
                "occurred_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in all_timeline
        ],
    }


# ---------------------------------------------------------------------------
# Single-session variant of _BASE_CTE
#
# Mirrors the classification CASE expressions in _shared._BASE_CTE exactly
# but scopes to one session (:sid) with no date-range filter.
# Used only by GET /analytics/cases/{session_id}.
# ---------------------------------------------------------------------------

_SINGLE_SESSION_CTE = """
    WITH sessions_with_pdf AS (
        SELECT DISTINCT p.session_id, s.is_active AS session_is_active
        FROM pdf_documents p
        INNER JOIN sessions s ON s.id = p.session_id
        WHERE s.id = :sid
    ),
    sessions_with_active_thread AS (
        SELECT DISTINCT session_id
        FROM chat_threads
        WHERE is_active = true AND session_id = :sid
    ),
    sessions_with_pending_ingestion AS (
        SELECT DISTINCT session_id
        FROM courtdrive_ingestions
        WHERE ingestion_type = 'pending_acceptance'
          AND status = 'pending_acceptance'
          AND session_id = :sid
    ),
    latest_pdf_status AS (
        SELECT DISTINCT ON (p.session_id)
            p.session_id,
            p.petition_status,
            p.inbox_checked_at,
            p.source,
            (p.filename ~ '^Bankruptcy_Petition_') AS is_inbox_file,
            swp.session_is_active,
            (sat.session_id IS NOT NULL) AS has_active_thread,
            (spi.session_id IS NOT NULL) AS has_pending_ingestion
        FROM pdf_documents p
        INNER JOIN sessions_with_pdf swp ON swp.session_id = p.session_id
        LEFT JOIN sessions_with_active_thread sat ON sat.session_id = p.session_id
        LEFT JOIN sessions_with_pending_ingestion spi ON spi.session_id = p.session_id
        ORDER BY p.session_id, p.uploaded_at DESC
    ),
    session_bucket AS (
        SELECT
            session_id,
            CASE
                WHEN petition_status IS NULL AND session_is_active AND has_active_thread     THEN 'working'
                WHEN petition_status IS NULL AND NOT session_is_active                       THEN 'deleted'
                WHEN petition_status IS NULL AND session_is_active AND NOT has_active_thread THEN 'deleted'
                WHEN NOT session_is_active AND petition_status IN ('working', 'accepted')    THEN 'deleted'
                WHEN session_is_active AND NOT has_active_thread
                     AND petition_status IN ('working', 'accepted')                          THEN 'deleted'
                WHEN NOT session_is_active AND petition_status = 'pending_acceptance'        THEN 'denied'
                WHEN petition_status = 'pending_acceptance' AND session_is_active
                     AND (inbox_checked_at IS NOT NULL OR NOT is_inbox_file
                          OR NOT has_pending_ingestion)                                      THEN 'denied'
                ELSE petition_status
            END AS petition_status,
            CASE
                WHEN petition_status IN ('working', 'accepted') AND session_is_active
                     AND has_active_thread                                                   THEN 'active'
                WHEN petition_status IS NULL AND session_is_active AND has_active_thread     THEN 'active'
                WHEN petition_status IN ('working', 'accepted') AND NOT session_is_active    THEN 'inactive'
                WHEN petition_status IN ('working', 'accepted') AND session_is_active
                     AND NOT has_active_thread                                               THEN 'inactive'
                WHEN petition_status IS NULL AND NOT session_is_active                       THEN 'inactive'
                WHEN petition_status IS NULL AND session_is_active AND NOT has_active_thread THEN 'inactive'
                WHEN petition_status = 'pending_acceptance' AND session_is_active
                     AND inbox_checked_at IS NULL AND is_inbox_file
                     AND has_pending_ingestion                                               THEN 'pending'
                WHEN petition_status = 'pending_acceptance' AND NOT session_is_active        THEN 'inactive'
                WHEN petition_status = 'pending_acceptance' AND session_is_active            THEN 'inactive'
                WHEN petition_status IN ('denied', 'archived', 'deleted', 'auto_archived')    THEN 'inactive'
                ELSE 'other'
            END AS bucket,
            source
        FROM latest_pdf_status
    )
"""


# ---------------------------------------------------------------------------
# Response schemas — GET /cases
# ---------------------------------------------------------------------------

class CasesAnalyticsActiveKpis(BaseModel):
    sum: int
    manual: int
    summoned: int
    from_pending: int


class CasesAnalyticsInactiveKpis(BaseModel):
    sum: int
    denied: int
    archived: int
    deleted: int


class CasesAnalyticsByDistrict(BaseModel):
    flnb: int
    flmb: int
    flsb: int
    pawb: int
    other: int


class CasesAnalyticsKpis(BaseModel):
    total: int
    active: CasesAnalyticsActiveKpis
    pending: int
    inactive: CasesAnalyticsInactiveKpis
    by_district: CasesAnalyticsByDistrict


class CaseTimelineActor(BaseModel):
    user_id: str
    name: Optional[str]


class CaseTimelineEvent(BaseModel):
    event: str
    at: datetime
    detail: Optional[str]
    actor: Optional[CaseTimelineActor]


class CaseDocument(BaseModel):
    filename: str
    source: Optional[str]
    uploaded_at: datetime


class CaseAnalyticsItem(BaseModel):
    session_id: str
    case_number: Optional[str]
    debtor_name: Optional[str]
    district: Optional[str]
    petition_status: Optional[str]
    bucket: str
    source: Optional[str]
    created_at: datetime
    last_activity_at: Optional[datetime]
    motions_count: int
    thread_id: Optional[str]


class CasesAnalyticsPagination(BaseModel):
    page: int
    page_size: int
    total: int


class ListPagination(BaseModel):
    page: int
    page_size: int
    total: int


class CasesAnalyticsResponse(BaseModel):
    kpis: CasesAnalyticsKpis
    pagination: CasesAnalyticsPagination
    cases: list[CaseAnalyticsItem]
    date_range: DateRangeInfo


# ---------------------------------------------------------------------------
# Response schemas — GET /cases/{session_id}
# ---------------------------------------------------------------------------

class CaseMotion(BaseModel):
    task_id: str
    motion_type: str
    status: str
    case_name: Optional[str]
    case_number: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]
    processing_seconds: Optional[float]


class CaseDetailResponse(BaseModel):
    session_id: str
    case_number: Optional[str]
    debtor_name: Optional[str]
    district: Optional[str]
    petition_status: Optional[str]
    bucket: str
    source: Optional[str]
    created_at: datetime
    last_activity_at: Optional[datetime]
    thread_id: Optional[str]
    motions_count: int              # total motions for the case, unfiltered
    documents: list[CaseDocument]  # no pagination — typically few docs per case
    motions: list[CaseMotion]
    motions_pagination: ListPagination
    timeline: list[CaseTimelineEvent]
    timeline_pagination: ListPagination


# ---------------------------------------------------------------------------
# Timeline helpers
# ---------------------------------------------------------------------------

async def _fetch_user_names(user_ids: set[str]) -> dict[str, str]:
    """Batch-fetch display names from user_db for a set of user IDs."""
    if not user_ids:
        return {}
    async with UserAsyncSessionLocal() as user_db:
        rows = await user_db.execute(
            text("SELECT id, email, first_name, last_name FROM users WHERE id = ANY(:ids)"),
            {"ids": list(user_ids)},
        )
        return {
            row.id: (" ".join(filter(None, [row.first_name, row.last_name])) or row.email)
            for row in rows
        }


# ---------------------------------------------------------------------------
# GET /cases
# ---------------------------------------------------------------------------

@router.get("/cases", response_model=CasesAnalyticsResponse)
async def get_cases_analytics(
    dr: DateRangeParams = Depends(),
    _user: User = Depends(get_current_firm_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort_by: str = Query("created_at", pattern="^(created_at|status|district|debtor_name|bucket|source|last_activity_at|motions_count)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    search: Optional[str] = Query(None, description="Case number, debtor name, or session ID"),
    status: Optional[str] = Query(None, description="Filter by petition_status"),
    district: Optional[str] = Query(None, description="Filter by district code"),
    source: Optional[str] = Query(None, pattern="^(manual|ecf|gdrive|courtdrive)$"),
):
    """
    Returns case KPIs (global for the date range) and a filtered, paginated
    case list.

    KPIs are never affected by the list filters (search/status/district/source)
    — they always reflect the full picture for the chosen date window.

    Timeline events include per-event detail strings and actor info (resolved
    via a batch lookup against user_db after all chat_db queries complete).
    """
    range_params: dict = {"start": dr.start, "end": dr.end}

    sort_col = {
        "created_at":      "s.created_at",
        "status":          "sb.petition_status",
        "district":        "cm.district",
        "debtor_name":     "cm.debtor_name",
        "bucket":          "sb.bucket",
        "source":          "cs.source",
        "last_activity_at": "la.last_activity_at",
        "motions_count":   "mc.motions_count",
    }[sort_by]
    order = "DESC" if sort_dir == "desc" else "ASC"

    # Build optional WHERE predicates for the list query
    where_clauses: list[str] = ["sb.bucket != 'other'"]
    list_extra: dict = {}

    if search:
        where_clauses.append(
            "(LOWER(cm.case_number) LIKE :search_pat"
            " OR LOWER(cm.debtor_name) LIKE :search_pat"
            " OR LOWER(sb.session_id) LIKE :search_pat)"
        )
        list_extra["search_pat"] = f"%{search.strip().lower()}%"

    if status:
        where_clauses.append("sb.petition_status = :status_filter")
        list_extra["status_filter"] = status

    if district:
        where_clauses.append("cm.district = :district_filter")
        list_extra["district_filter"] = district

    if source:
        where_clauses.append("cs.source = :source_filter")
        list_extra["source_filter"] = source

    where_sql = "WHERE " + " AND ".join(where_clauses)

    async with AsyncSessionLocal() as db:

        # --------------------------------------------------------------
        # KPI: bucket counts (active / inactive breakdown)
        # --------------------------------------------------------------
        bucket_rows = await db.execute(
            text(f"""
                {_BASE_CTE}
                SELECT bucket, petition_status, COUNT(*) AS cnt
                FROM session_bucket
                GROUP BY bucket, petition_status
            """),
            range_params,
        )
        active_sum = denied = deleted = 0
        for row in bucket_rows:
            if row.bucket == "active":
                active_sum += row.cnt
            elif row.bucket == "inactive":
                if row.petition_status == "denied":
                    denied += row.cnt
                elif row.petition_status == "deleted":
                    deleted += row.cnt

        # Sync stale pending sessions before counting so the KPI matches the inbox list.
        try:
            from ...gmail.workflow_services import CaseAcceptanceService
            asyncio.create_task(CaseAcceptanceService().auto_archive_stale_pending_cases())
        except Exception:
            pass

        # --------------------------------------------------------------
        # KPI: pending — global bucket count (not user-scoped)
        # --------------------------------------------------------------
        pending_result = await db.execute(
            text(f"""
                {_BASE_CTE}
                SELECT COUNT(*) AS cnt FROM session_bucket WHERE bucket = 'pending'
            """),
            range_params,
        )
        pending_count: int = pending_result.scalar() or 0

        # --------------------------------------------------------------
        # KPI: active entry-type breakdown (manual / summoned / from_pending)
        # --------------------------------------------------------------
        entry_rows = await db.execute(
            text(f"""
                {_BASE_CTE},
                active_sessions AS (
                    SELECT session_id FROM session_bucket WHERE bucket = 'active'
                ),
                latest_source AS (
                    SELECT DISTINCT ON (p.session_id)
                        p.session_id,
                        p.source
                    FROM pdf_documents p
                    INNER JOIN active_sessions a ON a.session_id = p.session_id
                    ORDER BY p.session_id, p.uploaded_at DESC
                ),
                session_entry AS (
                    SELECT
                        session_id,
                        CASE
                            WHEN source IN ('gdrive', 'courtdrive') THEN 'summoned'
                            WHEN source = 'ecf'                     THEN 'from_pending'
                            ELSE 'manual'
                        END AS entry_type
                    FROM latest_source
                )
                SELECT entry_type, COUNT(*) AS cnt
                FROM session_entry
                GROUP BY entry_type
            """),
            range_params,
        )
        entry_counts: dict[str, int] = {row.entry_type: row.cnt for row in entry_rows}

        # --------------------------------------------------------------
        # KPI: archived — DB rows + Google Drive (mirrors kpis.py)
        # --------------------------------------------------------------
        archived_db_rows = await db.execute(
            text(f"""
                {_BASE_CTE},
                archived_sessions AS (
                    SELECT session_id FROM session_bucket
                    WHERE bucket = 'inactive' AND petition_status = 'archived'
                )
                SELECT DISTINCT ON (p.session_id) p.filename
                FROM pdf_documents p
                INNER JOIN archived_sessions a ON a.session_id = p.session_id
                ORDER BY p.session_id, p.uploaded_at DESC
            """),
            range_params,
        )
        db_archived_names = {
            Path(r.filename).stem.lower() for r in archived_db_rows if r.filename
        }
        drive_filenames_raw: list[str] = await asyncio.get_event_loop().run_in_executor(
            None, list_archived_petition_filenames
        )
        drive_archived_names = {Path(n).stem.lower() for n in drive_filenames_raw if n}
        archived = len(db_archived_names | drive_archived_names)

        # --------------------------------------------------------------
        # KPI: district breakdown — active sessions only
        # --------------------------------------------------------------
        district_rows = await db.execute(
            text(f"""
                {_BASE_CTE},
                active_sessions AS (
                    SELECT session_id FROM session_bucket WHERE bucket = 'active'
                ),
                latest_district AS (
                    SELECT DISTINCT ON (ct.session_id)
                        ct.session_id,
                        ct.district
                    FROM chat_threads ct
                    INNER JOIN active_sessions a ON a.session_id = ct.session_id
                    WHERE ct.district IS NOT NULL
                    ORDER BY ct.session_id, ct.created_at DESC
                )
                SELECT
                    COALESCE(ld.district, 'other') AS district,
                    COUNT(*) AS cnt
                FROM active_sessions a
                LEFT JOIN latest_district ld ON ld.session_id = a.session_id
                GROUP BY COALESCE(ld.district, 'other')
            """),
            range_params,
        )
        district_counts: dict[str, int] = {row.district: row.cnt for row in district_rows}

        total_cases = active_sum + pending_count + denied + archived + deleted

        kpis = CasesAnalyticsKpis(
            total=total_cases,
            active=CasesAnalyticsActiveKpis(
                sum=active_sum,
                manual=entry_counts.get("manual", 0),
                summoned=entry_counts.get("summoned", 0),
                from_pending=entry_counts.get("from_pending", 0),
            ),
            pending=pending_count,
            inactive=CasesAnalyticsInactiveKpis(
                sum=denied + archived + deleted,
                denied=denied,
                archived=archived,
                deleted=deleted,
            ),
            by_district=CasesAnalyticsByDistrict(
                flnb=district_counts.get("flnb", 0),
                flmb=district_counts.get("flmb", 0),
                flsb=district_counts.get("flsb", 0),
                pawb=district_counts.get("pawb", 0),
                other=district_counts.get("other", 0),
            ),
        )

        # --------------------------------------------------------------
        # Case list — base CTE extended with metadata joins
        # --------------------------------------------------------------
        base_list_sql = f"""
            {_BASE_CTE},
            case_meta AS (
                -- Most-recent thread per session carries debtor name, case number, district.
                SELECT DISTINCT ON (ct.session_id)
                    ct.session_id,
                    ct.id       AS thread_id,
                    ct.case_number,
                    ct.title    AS debtor_name,
                    ct.district
                FROM chat_threads ct
                ORDER BY ct.session_id, ct.created_at DESC
            ),
            case_source AS (
                -- Latest PDF determines the intake source for the session.
                SELECT DISTINCT ON (p.session_id)
                    p.session_id,
                    p.source
                FROM pdf_documents p
                ORDER BY p.session_id, p.uploaded_at DESC
            ),
            motion_counts AS (
                SELECT session_id, COUNT(*) AS motions_count
                FROM motion_draft_logs
                GROUP BY session_id
            ),
            last_activity AS (
                SELECT session_id, MAX(created_at) AS last_activity_at
                FROM user_activity_logs
                WHERE session_id IS NOT NULL
                GROUP BY session_id
            )
            SELECT
                sb.session_id,
                sb.bucket,
                sb.petition_status,
                cm.thread_id,
                cm.case_number,
                cm.debtor_name,
                cm.district,
                cs.source,
                s.created_at,
                la.last_activity_at,
                COALESCE(mc.motions_count, 0) AS motions_count
            FROM session_bucket sb
            INNER JOIN sessions s ON s.id = sb.session_id
            LEFT JOIN case_meta     cm ON cm.session_id = sb.session_id
            LEFT JOIN case_source   cs ON cs.session_id = sb.session_id
            LEFT JOIN motion_counts mc ON mc.session_id = sb.session_id
            LEFT JOIN last_activity la ON la.session_id = sb.session_id
            {where_sql}
        """

        all_params = {**range_params, **list_extra}

        count_result = await db.execute(
            text(f"SELECT COUNT(*) FROM ({base_list_sql}) AS _q"),
            all_params,
        )
        total_filtered: int = count_result.scalar() or 0

        if total_filtered == 0:
            return CasesAnalyticsResponse(
                kpis=kpis,
                pagination=CasesAnalyticsPagination(page=page, page_size=page_size, total=0),
                cases=[],
                date_range=DateRangeInfo(preset=dr.range, start=dr.start, end=dr.end),
            )

        offset = (page - 1) * page_size
        list_result = await db.execute(
            text(
                f"{base_list_sql}"
                f" ORDER BY {sort_col} {order} NULLS LAST"
                f" LIMIT :limit OFFSET :offset"
            ),
            {**all_params, "limit": page_size, "offset": offset},
        )
        list_rows = list_result.fetchall()

    # ------------------------------------------------------------------
    # Assemble response items
    # ------------------------------------------------------------------
    cases: list[CaseAnalyticsItem] = [
        CaseAnalyticsItem(
            session_id=row.session_id,
            case_number=row.case_number,
            debtor_name=row.debtor_name,
            district=row.district,
            petition_status=row.petition_status,
            bucket=row.bucket,
            source=row.source,
            created_at=row.created_at,
            last_activity_at=row.last_activity_at,
            motions_count=int(row.motions_count),
            thread_id=row.thread_id,
        )
        for row in list_rows
    ]

    return CasesAnalyticsResponse(
        kpis=kpis,
        pagination=CasesAnalyticsPagination(
            page=page,
            page_size=page_size,
            total=total_filtered,
        ),
        cases=cases,
        date_range=DateRangeInfo(preset=dr.range, start=dr.start, end=dr.end),
    )


# ---------------------------------------------------------------------------
# GET /cases/{session_id}
# ---------------------------------------------------------------------------

_TIMELINE_CTE = """
    WITH all_events AS (
        -- PDF uploads
        SELECT
            'pdf_uploaded'                                  AS event,
            p.uploaded_at                                   AS at,
            COALESCE(p.original_filename, p.filename)       AS detail_raw,
            s.user_id                                       AS user_id,
            NULL::text                                      AS action,
            NULL::jsonb                                     AS activity_metadata,
            NULL::text                                      AS motion_type,
            NULL::text                                      AS case_number
        FROM pdf_documents p
        INNER JOIN sessions s ON s.id = p.session_id
        WHERE p.session_id = :sid

        UNION ALL

        -- Activity milestones (action mapped to display event name)
        SELECT
            CASE action
                WHEN 'accept_case'       THEN 'accepted'
                WHEN 'deny_case'         THEN 'denied'
                WHEN 'archive_case'      THEN 'archived'
                WHEN 'summon_case'       THEN 'case_summoned'
                WHEN 'generate_document' THEN 'document_generated'
            END                                             AS event,
            created_at                                      AS at,
            NULL                                            AS detail_raw,
            user_id                                         AS user_id,
            action                                          AS action,
            activity_metadata::jsonb                        AS activity_metadata,
            activity_metadata->>'motion_type'               AS motion_type,
            activity_metadata->>'case_number'               AS case_number
        FROM user_activity_logs
        WHERE session_id = :sid
          AND action IN ('accept_case', 'deny_case', 'archive_case',
                         'summon_case', 'generate_document')

        UNION ALL

        -- Completed motions
        SELECT
            'motion_drafted'                                AS event,
            m.created_at                                    AS at,
            m.motion_type                                   AS detail_raw,
            s.user_id                                       AS user_id,
            NULL                                            AS action,
            NULL::jsonb                                     AS activity_metadata,
            m.motion_type                                   AS motion_type,
            m.case_number                                   AS case_number
        FROM motion_draft_logs m
        INNER JOIN sessions s ON s.id = m.session_id
        WHERE m.session_id = :sid AND m.status = 'completed'
    ),
    deduped AS (
        SELECT DISTINCT ON (event, DATE_TRUNC('minute', at))
            event, at, detail_raw, user_id, action, activity_metadata,
            motion_type, case_number
        FROM all_events
        ORDER BY event, DATE_TRUNC('minute', at), at
    )
"""


@router.get("/cases/{session_id}", response_model=CaseDetailResponse)
async def get_case_detail(
    session_id: str,
    _user: User = Depends(get_current_firm_user),
    # ── Motions pagination / filter / sort ──────────────────────────────
    motions_page: int = Query(1, ge=1),
    motions_page_size: int = Query(20, ge=1, le=100),
    motions_search: Optional[str] = Query(None, description="Search in motion_type, case_name, case_number"),
    motions_status: Optional[str] = Query(None, description="Filter by motion status"),
    motions_motion_type: Optional[str] = Query(None, description="Filter by exact motion_type"),
    motions_sort_by: str = Query("created_at", pattern="^(created_at|motion_type|status|processing_seconds)$"),
    motions_sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    # ── Timeline pagination / filter ────────────────────────────────────
    timeline_page: int = Query(1, ge=1),
    timeline_page_size: int = Query(20, ge=1, le=100),
    timeline_event: Optional[str] = Query(None, description="Filter by event type (e.g. pdf_uploaded, accepted)"),
    timeline_actor_id: Optional[str] = Query(None, description="Filter by actor user_id"),
    timeline_search: Optional[str] = Query(None, description="Search in detail_raw and motion_type"),
    timeline_sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
):
    """
    Returns the full detail view for a single case with server-side pagination
    for both the motions list and the timeline.

    No date-range filter — always reflects the current state of the case.

    Motions and timeline are independently paginated; documents are always
    returned in full (typically few per case).
    """
    # ── Build motions WHERE clause ────────────────────────────────────────
    m_where: list[str] = ["session_id = :sid"]
    m_params: dict = {"sid": session_id}

    if motions_status:
        m_where.append("status = :m_status")
        m_params["m_status"] = motions_status

    if motions_motion_type:
        m_where.append("motion_type = :m_type")
        m_params["m_type"] = motions_motion_type

    if motions_search:
        m_where.append(
            "(motion_type ILIKE :m_search"
            " OR COALESCE(case_name, '') ILIKE :m_search"
            " OR COALESCE(case_number, '') ILIKE :m_search)"
        )
        m_params["m_search"] = f"%{motions_search}%"

    m_where_sql = "WHERE " + " AND ".join(m_where)

    m_sort_col = {
        "created_at":         "created_at",
        "motion_type":        "motion_type",
        "status":             "status",
        "processing_seconds": "EXTRACT(EPOCH FROM (completed_at - created_at))",
    }[motions_sort_by]
    m_order = "DESC" if motions_sort_dir == "desc" else "ASC"
    m_offset = (motions_page - 1) * motions_page_size

    # ── Build timeline WHERE clause ───────────────────────────────────────
    tl_where: list[str] = []
    tl_params: dict = {"sid": session_id}

    if timeline_event:
        tl_where.append("event = :tl_event")
        tl_params["tl_event"] = timeline_event

    if timeline_actor_id:
        tl_where.append("user_id = :tl_actor_id")
        tl_params["tl_actor_id"] = timeline_actor_id

    if timeline_search:
        tl_where.append(
            "(detail_raw ILIKE :tl_search"
            " OR motion_type ILIKE :tl_search"
            " OR COALESCE(case_number, '') ILIKE :tl_search)"
        )
        tl_params["tl_search"] = f"%{timeline_search}%"

    tl_where_sql = ("WHERE " + " AND ".join(tl_where)) if tl_where else ""
    tl_order = "DESC" if timeline_sort_dir == "desc" else "ASC"
    tl_offset = (timeline_page - 1) * timeline_page_size

    async with AsyncSessionLocal() as db:

        # ------------------------------------------------------------------
        # Core metadata — classification + thread info
        # ------------------------------------------------------------------
        meta_result = await db.execute(
            text(f"""
                {_SINGLE_SESSION_CTE}
                SELECT
                    s.id                AS session_id,
                    s.created_at,
                    sb.bucket,
                    sb.petition_status  AS effective_status,
                    sb.source,
                    (SELECT MAX(ual.created_at)
                     FROM user_activity_logs ual
                     WHERE ual.session_id = :sid)   AS last_activity_at,
                    (SELECT COUNT(*)
                     FROM motion_draft_logs mdl
                     WHERE mdl.session_id = :sid)   AS motions_count,
                    ct.id               AS thread_id,
                    ct.case_number,
                    ct.title            AS debtor_name,
                    ct.district
                FROM sessions s
                INNER JOIN session_bucket sb ON sb.session_id = s.id
                LEFT JOIN LATERAL (
                    SELECT id, case_number, title, district
                    FROM chat_threads
                    WHERE session_id = s.id
                    ORDER BY created_at DESC
                    LIMIT 1
                ) ct ON true
                WHERE s.id = :sid
            """),
            {"sid": session_id},
        )
        meta = meta_result.fetchone()

        if meta is None:
            raise HTTPException(status_code=404, detail="Case not found")

        # ------------------------------------------------------------------
        # Documents (all, unfiltered — typically few per case)
        # ------------------------------------------------------------------
        docs_result = await db.execute(
            text("""
                SELECT p.filename, p.source, p.uploaded_at
                FROM pdf_documents p
                WHERE p.session_id = :sid
                ORDER BY p.uploaded_at ASC
            """),
            {"sid": session_id},
        )
        documents = [
            CaseDocument(filename=r.filename, source=r.source, uploaded_at=r.uploaded_at)
            for r in docs_result.fetchall()
        ]

        # ------------------------------------------------------------------
        # Motions — filtered, sorted, paginated with window-function total
        # ------------------------------------------------------------------
        motions_result = await db.execute(
            text(f"""
                SELECT id, motion_type, status, case_name, case_number,
                       created_at, completed_at,
                       COUNT(*) OVER() AS total_count
                FROM motion_draft_logs
                {m_where_sql}
                ORDER BY {m_sort_col} {m_order} NULLS LAST
                LIMIT :m_limit OFFSET :m_offset
            """),
            {**m_params, "m_limit": motions_page_size, "m_offset": m_offset},
        )
        motion_rows = motions_result.fetchall()
        motions_total = int(motion_rows[0].total_count) if motion_rows else 0
        motions = [
            CaseMotion(
                task_id=r.id,
                motion_type=r.motion_type,
                status=r.status,
                case_name=r.case_name,
                case_number=r.case_number,
                created_at=r.created_at,
                completed_at=r.completed_at,
                processing_seconds=(
                    (r.completed_at - r.created_at).total_seconds()
                    if r.completed_at and r.status == "completed"
                    else None
                ),
            )
            for r in motion_rows
        ]

        # ------------------------------------------------------------------
        # Timeline — SQL UNION + dedup + filter + paginate
        # ------------------------------------------------------------------
        tl_count_result = await db.execute(
            text(f"{_TIMELINE_CTE} SELECT COUNT(*) FROM deduped {tl_where_sql}"),
            tl_params,
        )
        timeline_total: int = tl_count_result.scalar() or 0

        tl_result = await db.execute(
            text(f"""
                {_TIMELINE_CTE}
                SELECT event, at, detail_raw, user_id, action,
                       activity_metadata, motion_type, case_number
                FROM deduped
                {tl_where_sql}
                ORDER BY at {tl_order}
                LIMIT :tl_limit OFFSET :tl_offset
            """),
            {**tl_params, "tl_limit": timeline_page_size, "tl_offset": tl_offset},
        )
        tl_rows = tl_result.fetchall()

    # ------------------------------------------------------------------
    # Resolve actor names for timeline page only
    # ------------------------------------------------------------------
    tl_user_ids = {r.user_id for r in tl_rows if r.user_id}
    user_name_map = await _fetch_user_names(tl_user_ids)

    # Build CaseTimelineEvent from SQL rows
    timeline: list[CaseTimelineEvent] = []
    for r in tl_rows:
        if r.event == "pdf_uploaded":
            detail: Optional[str] = Path(r.detail_raw).name if r.detail_raw else None
        elif r.action:
            detail = _build_activity_detail(r.action, r.activity_metadata)
        else:  # motion_drafted
            display = _MOTION_DISPLAY_NAMES.get(r.motion_type, r.motion_type) if r.motion_type else None
            detail = f"{display} — {r.case_number}" if display and r.case_number else display

        actor: Optional[CaseTimelineActor] = None
        if r.user_id:
            actor = CaseTimelineActor(user_id=r.user_id, name=user_name_map.get(r.user_id))

        timeline.append(CaseTimelineEvent(event=r.event, at=r.at, detail=detail, actor=actor))

    return CaseDetailResponse(
        session_id=session_id,
        case_number=meta.case_number,
        debtor_name=meta.debtor_name,
        district=meta.district,
        petition_status=meta.effective_status,
        bucket=meta.bucket,
        source=meta.source,
        created_at=meta.created_at,
        last_activity_at=meta.last_activity_at,
        thread_id=meta.thread_id,
        motions_count=int(meta.motions_count),
        documents=documents,
        motions=motions,
        motions_pagination=ListPagination(
            page=motions_page,
            page_size=motions_page_size,
            total=motions_total,
        ),
        timeline=timeline,
        timeline_pagination=ListPagination(
            page=timeline_page,
            page_size=timeline_page_size,
            total=timeline_total,
        ),
    )
