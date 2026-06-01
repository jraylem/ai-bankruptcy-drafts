"""
Analytics sub-page: Motion Analytics & Lookup.

GET /analytics/motions              → /api/dashboard/analytics/motions
GET /analytics/motions/sessions/{session_id} → /api/dashboard/analytics/motions/sessions/{session_id}

Design notes:
  - KPIs are always global for the date range; list filters do not affect them.
  - All motion data lives in motion_draft_logs (chat_db).
  - District and debtor_name require a LATERAL join to the latest chat_thread.
  - Actor names are resolved via a single batch query against user_db after all
    chat_db queries complete (same cross-DB merge pattern as analytics_cases.py).
  - _ORDER_KEYS classifies motion_type values into motions vs orders for the
    by_type split and the category list filter.
  - cos_type KPIs count only rows where cos_type IS NOT NULL (completed rows).
  - motion_type_ranking is assembled in Python from by_type.motions + orders.
  - The session endpoint returns KPIs over all rows and a filtered, paginated list.
"""

import asyncio
import logging
from collections import defaultdict
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text

from ...auth.models import User
from ...common.dependencies import get_current_firm_user
from ...auth.database import UserAsyncSessionLocal
from ...chatbot.database import AsyncSessionLocal
from ._shared import DateRangeParams, DateRangeInfo, _MOTION_DISPLAY_NAMES

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analytics"])

# ---------------------------------------------------------------------------
# Motion vs Order classification
# ---------------------------------------------------------------------------

_ORDER_KEYS: set[str] = {
    k for k in _MOTION_DISPLAY_NAMES
    if k.startswith("order-") or k == "objection-sustain"
}


# ---------------------------------------------------------------------------
# Response schemas — GET /analytics/motions
# ---------------------------------------------------------------------------

class MotionsAnalyticsKpisByStatus(BaseModel):
    pending: int
    completed: int
    failed: int
    cancelled: int


class MotionsAnalyticsByTypeItem(BaseModel):
    motion_type: str
    display_name: str
    completed: int
    total_attempted: int


class MotionsAnalyticsByType(BaseModel):
    motions: list[MotionsAnalyticsByTypeItem]
    orders: list[MotionsAnalyticsByTypeItem]


class MotionsAnalyticsDistrictItem(BaseModel):
    completed: int
    total_attempted: int


class MotionsAnalyticsByDistrict(BaseModel):
    flnb: MotionsAnalyticsDistrictItem
    flmb: MotionsAnalyticsDistrictItem
    flsb: MotionsAnalyticsDistrictItem
    pawb: MotionsAnalyticsDistrictItem
    other: MotionsAnalyticsDistrictItem


class MotionsAnalyticsByCosType(BaseModel):
    with_notice_of_hearing: int
    without_notice_of_hearing: int
    no: int


class MotionsAnalyticsAvgByTypeItem(BaseModel):
    motion_type: str
    display_name: str
    avg_seconds: float


class MotionsAnalyticsRankingItem(BaseModel):
    motion_type: str
    display_name: str
    category: str  # "motion" | "order"
    completed: int
    total_attempted: int


class MotionsAnalyticsCosRankingItem(BaseModel):
    motion_type: str
    display_name: str
    count: int


class MotionsAnalyticsCosTypeRanking(BaseModel):
    with_notice_of_hearing: list[MotionsAnalyticsCosRankingItem]
    without_notice_of_hearing: list[MotionsAnalyticsCosRankingItem]


class MotionsAnalyticsKpis(BaseModel):
    total: int
    by_status: MotionsAnalyticsKpisByStatus
    success_rate_pct: float
    avg_processing_seconds: Optional[float]
    by_type: MotionsAnalyticsByType
    by_district: MotionsAnalyticsByDistrict
    by_cos_type: MotionsAnalyticsByCosType
    cos_type_ranking: MotionsAnalyticsCosTypeRanking
    motion_type_ranking: list[MotionsAnalyticsRankingItem]
    avg_processing_by_type: list[MotionsAnalyticsAvgByTypeItem]


class MotionAnalyticsItem(BaseModel):
    task_id: str
    session_id: str
    case_number: Optional[str]
    case_name: Optional[str]
    debtor_name: Optional[str]
    district: Optional[str]
    motion_type: str
    display_name: str
    category: str  # "motion" | "order"
    status: str
    cos_type: Optional[str]
    source: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]
    processing_seconds: Optional[float]
    actor_user_id: Optional[str]
    actor_name: Optional[str]


class MotionsAnalyticsPagination(BaseModel):
    page: int
    page_size: int
    total: int


class SessionMotionsPagination(BaseModel):
    page: int
    page_size: int
    total: int


class MotionsAnalyticsResponse(BaseModel):
    kpis: MotionsAnalyticsKpis
    pagination: MotionsAnalyticsPagination
    motions: list[MotionAnalyticsItem]
    date_range: DateRangeInfo


# ---------------------------------------------------------------------------
# Response schemas — GET /analytics/motions/session/{session_id}
# ---------------------------------------------------------------------------

class SessionMotionItem(BaseModel):
    task_id: str
    motion_type: str
    display_name: str
    category: str
    status: str
    cos_type: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]
    processing_seconds: Optional[float]
    actor_user_id: Optional[str]
    actor_name: Optional[str]


class SessionMotionsByTypeItem(BaseModel):
    motion_type: str
    display_name: str
    category: str
    completed: int
    total_attempted: int


class SessionMotionsByType(BaseModel):
    motions: list[SessionMotionsByTypeItem]
    orders: list[SessionMotionsByTypeItem]


class SessionMotionSummaryKpis(BaseModel):
    total_motions_and_orders: int
    total_motions: int
    total_orders: int
    completed: int
    pending: int
    failed: int
    cancelled: int
    avg_processing_seconds: Optional[float]
    total_cos_generated: int
    cos_with_notice_of_hearing: int
    cos_without_notice_of_hearing: int


class SessionMotionsResponse(BaseModel):
    session_id: str
    case_number: Optional[str]
    debtor_name: Optional[str]
    district: Optional[str]
    kpis: SessionMotionSummaryKpis
    by_type: SessionMotionsByType
    pagination: SessionMotionsPagination
    motions: list[SessionMotionItem]


# ---------------------------------------------------------------------------
# Helpers
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


def _category(motion_type: str) -> str:
    return "order" if motion_type in _ORDER_KEYS else "motion"


# ---------------------------------------------------------------------------
# Internal fetch functions — called by _chat_snapshot.py / analytics_insights.py
# ---------------------------------------------------------------------------

async def _fetch_motions_kpi_enriched(start: datetime, end: datetime) -> dict:
    """
    Called by: _fetch_dashboard_snapshot (_chat_snapshot.py)
    Enriched KPIs: success_rate, avg_processing, by_district, cos_type_ranking,
    avg_processing_by_type.
    """
    params = {"start": start, "end": end}
    async with AsyncSessionLocal() as db:
        status_rows = await db.execute(
            text("""
                SELECT status, COUNT(*) AS cnt,
                       AVG(CASE WHEN status = 'completed' AND completed_at IS NOT NULL
                           THEN EXTRACT(EPOCH FROM (completed_at - created_at)) END) AS avg_secs
                FROM motion_draft_logs
                WHERE created_at >= :start AND created_at <= :end
                GROUP BY status
            """),
            params,
        )
        status_counts: dict[str, int] = {}
        global_avg_secs: Optional[float] = None
        for row in status_rows:
            status_counts[row.status] = int(row.cnt)
            if row.avg_secs is not None:
                global_avg_secs = round(float(row.avg_secs), 2)

        completed_cnt = status_counts.get("completed", 0)
        failed_cnt    = status_counts.get("failed", 0)
        denom = completed_cnt + failed_cnt
        success_rate = round(completed_cnt / denom * 100, 1) if denom else 0.0

        avg_type_rows = await db.execute(
            text("""
                SELECT motion_type, AVG(EXTRACT(EPOCH FROM (completed_at - created_at))) AS avg_secs
                FROM motion_draft_logs
                WHERE created_at >= :start AND created_at <= :end
                  AND status = 'completed' AND completed_at IS NOT NULL
                GROUP BY motion_type
                ORDER BY avg_secs DESC
            """),
            params,
        )
        avg_processing_by_type = [
            {
                "motion_type": row.motion_type,
                "display_name": _MOTION_DISPLAY_NAMES.get(row.motion_type, row.motion_type),
                "avg_seconds": round(float(row.avg_secs), 2),
            }
            for row in avg_type_rows
            if row.avg_secs is not None
        ]

        cos_ranking_rows = await db.execute(
            text("""
                SELECT motion_type, cos_type, COUNT(*) AS cnt
                FROM motion_draft_logs
                WHERE created_at >= :start AND created_at <= :end
                  AND cos_type IN ('WithNoticeOfHearing', 'WithoutNoticeOfHearing')
                GROUP BY motion_type, cos_type
                ORDER BY cnt DESC
            """),
            params,
        )
        cos_buckets: dict[str, list] = defaultdict(list)
        for row in cos_ranking_rows:
            cos_buckets[row.cos_type].append({
                "motion_type": row.motion_type,
                "display_name": _MOTION_DISPLAY_NAMES.get(row.motion_type, row.motion_type),
                "count": int(row.cnt),
            })

        district_rows = await db.execute(
            text("""
                SELECT COALESCE(ct.district, 'other') AS district,
                       COUNT(*) AS total_attempted,
                       COUNT(*) FILTER (WHERE m.status = 'completed') AS completed
                FROM motion_draft_logs m
                INNER JOIN sessions s ON s.id = m.session_id
                LEFT JOIN LATERAL (
                    SELECT district FROM chat_threads
                    WHERE session_id = s.id ORDER BY created_at DESC LIMIT 1
                ) ct ON true
                WHERE m.created_at >= :start AND m.created_at <= :end
                GROUP BY COALESCE(ct.district, 'other')
            """),
            params,
        )
        known_districts = {"flnb", "flmb", "flsb", "pawb"}
        district_data: dict[str, dict] = {}
        for row in district_rows:
            key = row.district if row.district in known_districts else "other"
            if key not in district_data:
                district_data[key] = {"total_attempted": 0, "completed": 0}
            district_data[key]["total_attempted"] += int(row.total_attempted)
            district_data[key]["completed"] += int(row.completed)

    return {
        "success_rate_pct": success_rate,
        "avg_processing_seconds": global_avg_secs,
        "by_district": {
            d: district_data.get(d, {"total_attempted": 0, "completed": 0})
            for d in ("flnb", "flmb", "flsb", "pawb", "other")
        },
        "cos_type_ranking": {
            "with_notice_of_hearing": cos_buckets.get("WithNoticeOfHearing", []),
            "without_notice_of_hearing": cos_buckets.get("WithoutNoticeOfHearing", []),
        },
        "avg_processing_by_type": avg_processing_by_type,
    }


async def _query_motions_list(
    start: datetime,
    end: datetime,
    status: Optional[str] = None,
    motion_type: Optional[str] = None,
    category: Optional[str] = None,
    cos_type: Optional[str] = None,
    district: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: str = "created_at",
    limit: int = 20,
) -> dict:
    """
    Called by: _execute_chat_tool (analytics_insights.py)
    Returns total_count (full matching set) and up to 50 rows.
    COUNT(*) OVER () computes the total before LIMIT is applied — one query pass.
    """
    where_clauses = ["m.created_at >= :start", "m.created_at <= :end"]
    params: dict = {"start": start, "end": end}

    if search:
        where_clauses.append(
            "(LOWER(m.case_number) LIKE :search_pat"
            " OR LOWER(ct.title) LIKE :search_pat"
            " OR LOWER(m.session_id) LIKE :search_pat)"
        )
        params["search_pat"] = f"%{search.strip().lower()}%"
    if motion_type:
        where_clauses.append("m.motion_type = :motion_type_filter")
        params["motion_type_filter"] = motion_type
    if category == "order":
        params["type_filter"] = list(_ORDER_KEYS)
        where_clauses.append("m.motion_type = ANY(:type_filter)")
    elif category == "motion":
        params["type_filter"] = list(_ORDER_KEYS)
        where_clauses.append("m.motion_type != ALL(:type_filter)")
    if status:
        where_clauses.append("m.status = :status_filter")
        params["status_filter"] = status
    if cos_type:
        where_clauses.append("m.cos_type = :cos_type_filter")
        params["cos_type_filter"] = cos_type
    if district:
        where_clauses.append("ct.district = :district_filter")
        params["district_filter"] = district

    where_sql = " AND ".join(where_clauses)
    sort_col = "processing_seconds" if sort_by == "processing_seconds" else "m.created_at"

    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            text(f"""
                SELECT
                    m.id AS task_id,
                    m.session_id,
                    m.case_number,
                    m.motion_type,
                    m.status,
                    m.cos_type,
                    m.created_at,
                    EXTRACT(EPOCH FROM (m.completed_at - m.created_at)) AS processing_seconds,
                    ct.title AS debtor_name,
                    COUNT(*) OVER () AS total_count
                FROM motion_draft_logs m
                INNER JOIN sessions s ON s.id = m.session_id
                LEFT JOIN LATERAL (
                    SELECT title, district FROM chat_threads
                    WHERE session_id = s.id ORDER BY created_at DESC LIMIT 1
                ) ct ON true
                WHERE {where_sql}
                ORDER BY {sort_col} DESC NULLS LAST
                LIMIT :limit
            """),
            {**params, "limit": min(limit, 50)},
        )
        all_rows = rows.fetchall()

    total_count = int(all_rows[0].total_count) if all_rows else 0

    return {
        "total_count": total_count,
        "returned": len(all_rows),
        "items": [
            {
                "task_id": str(row.task_id),
                "session_id": str(row.session_id),
                "case_number": row.case_number,
                "debtor_name": row.debtor_name,
                "motion_type": row.motion_type,
                "display_name": _MOTION_DISPLAY_NAMES.get(row.motion_type, row.motion_type),
                "category": "order" if row.motion_type in _ORDER_KEYS else "motion",
                "status": row.status,
                "cos_type": row.cos_type,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "processing_seconds": (
                    round(float(row.processing_seconds), 2)
                    if row.processing_seconds is not None else None
                ),
            }
            for row in all_rows
        ],
    }


# ---------------------------------------------------------------------------
# GET /motions
# ---------------------------------------------------------------------------

@router.get("/motions", response_model=MotionsAnalyticsResponse)
async def get_motions_analytics(
    dr: DateRangeParams = Depends(),
    _user: User = Depends(get_current_firm_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort_by: str = Query(
        "created_at",
        pattern="^(created_at|status|motion_type|processing_seconds)$",
    ),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    search: Optional[str] = Query(None, description="LIKE match on case_number, debtor_name, session_id"),
    motion_type: Optional[str] = Query(None, description="Exact match on motion_type"),
    category: Optional[str] = Query(None, pattern="^(motion|order)$"),
    status: Optional[str] = Query(None, pattern="^(pending|completed|failed|cancelled)$"),
    district: Optional[str] = Query(None),
    source: Optional[str] = Query(None, pattern="^(manual|ecf|gdrive|courtdrive)$"),
    cos_type: Optional[str] = Query(
        None,
        pattern="^(WithNoticeOfHearing|WithoutNoticeOfHearing|No)$",
    ),
):
    """
    Returns motion KPIs (global for the date range) and a filtered, paginated
    motion list. KPIs are never affected by list filters.
    """
    range_params: dict = {"start": dr.start, "end": dr.end}

    sort_col = {
        "created_at":          "m.created_at",
        "status":              "m.status",
        "motion_type":         "m.motion_type",
        "processing_seconds":  "processing_seconds",
    }[sort_by]
    order = "DESC" if sort_dir == "desc" else "ASC"

    # ------------------------------------------------------------------
    # Build list WHERE predicates
    # ------------------------------------------------------------------
    where_clauses: list[str] = [
        "m.created_at >= :start",
        "m.created_at <= :end",
    ]
    list_extra: dict = {}

    if search:
        where_clauses.append(
            "(LOWER(m.case_number) LIKE :search_pat"
            " OR LOWER(ct.title) LIKE :search_pat"
            " OR LOWER(m.session_id) LIKE :search_pat)"
        )
        list_extra["search_pat"] = f"%{search.strip().lower()}%"

    if motion_type:
        where_clauses.append("m.motion_type = :motion_type_filter")
        list_extra["motion_type_filter"] = motion_type

    if category == "order":
        list_extra["type_filter"] = list(_ORDER_KEYS)
        where_clauses.append("m.motion_type = ANY(:type_filter)")
    elif category == "motion":
        list_extra["type_filter"] = list(_ORDER_KEYS)
        where_clauses.append("m.motion_type != ALL(:type_filter)")

    if status:
        where_clauses.append("m.status = :status_filter")
        list_extra["status_filter"] = status

    if district:
        where_clauses.append("ct.district = :district_filter")
        list_extra["district_filter"] = district

    if source:
        where_clauses.append("pd.source = :source_filter")
        list_extra["source_filter"] = source

    if cos_type:
        where_clauses.append("m.cos_type = :cos_type_filter")
        list_extra["cos_type_filter"] = cos_type

    where_sql = " AND ".join(where_clauses)

    async with AsyncSessionLocal() as db:

        # --------------------------------------------------------------
        # KPI 1: status counts + global avg processing (single query)
        # --------------------------------------------------------------
        status_rows = await db.execute(
            text("""
                SELECT status,
                       COUNT(*) AS cnt,
                       AVG(
                           CASE WHEN status = 'completed' AND completed_at IS NOT NULL
                                THEN EXTRACT(EPOCH FROM (completed_at - created_at))
                           END
                       ) AS avg_secs
                FROM motion_draft_logs
                WHERE created_at >= :start AND created_at <= :end
                GROUP BY status
            """),
            range_params,
        )
        status_counts: dict[str, int] = {}
        global_avg_secs: Optional[float] = None
        for row in status_rows:
            status_counts[row.status] = int(row.cnt)
            if row.avg_secs is not None:
                global_avg_secs = round(float(row.avg_secs), 2)

        pending_cnt   = status_counts.get("pending", 0)
        completed_cnt = status_counts.get("completed", 0)
        failed_cnt    = status_counts.get("failed", 0)
        cancelled_cnt = status_counts.get("cancelled", 0)
        total_cnt     = pending_cnt + completed_cnt + failed_cnt + cancelled_cnt

        denom = completed_cnt + failed_cnt
        success_rate = round(completed_cnt / denom * 100, 1) if denom else 0.0

        # --------------------------------------------------------------
        # KPI 2: count by motion_type → split motions vs orders in Python
        # --------------------------------------------------------------
        type_rows = await db.execute(
            text("""
                SELECT motion_type,
                       COUNT(*) AS total_attempted,
                       COUNT(*) FILTER (WHERE status = 'completed') AS completed
                FROM motion_draft_logs
                WHERE created_at >= :start AND created_at <= :end
                GROUP BY motion_type
                ORDER BY completed DESC
            """),
            range_params,
        )
        motion_type_items: list[MotionsAnalyticsByTypeItem] = []
        order_type_items: list[MotionsAnalyticsByTypeItem] = []
        for row in type_rows:
            item = MotionsAnalyticsByTypeItem(
                motion_type=row.motion_type,
                display_name=_MOTION_DISPLAY_NAMES.get(row.motion_type, row.motion_type),
                completed=int(row.completed),
                total_attempted=int(row.total_attempted),
            )
            if row.motion_type in _ORDER_KEYS:
                order_type_items.append(item)
            else:
                motion_type_items.append(item)

        # motion_type_ranking: merge motions + orders, tag category, sort by completed DESC
        motion_set = {it.motion_type for it in motion_type_items}
        motion_type_ranking = [
            MotionsAnalyticsRankingItem(
                motion_type=it.motion_type,
                display_name=it.display_name,
                category="motion" if it.motion_type in motion_set else "order",
                completed=it.completed,
                total_attempted=it.total_attempted,
            )
            for it in sorted(
                motion_type_items + order_type_items,
                key=lambda x: -x.completed,
            )
        ]

        # --------------------------------------------------------------
        # KPI 3: avg processing by type (completed only)
        # --------------------------------------------------------------
        avg_type_rows = await db.execute(
            text("""
                SELECT motion_type,
                       AVG(EXTRACT(EPOCH FROM (completed_at - created_at))) AS avg_secs
                FROM motion_draft_logs
                WHERE created_at >= :start AND created_at <= :end
                  AND status = 'completed' AND completed_at IS NOT NULL
                GROUP BY motion_type
                ORDER BY avg_secs DESC
            """),
            range_params,
        )
        avg_processing_by_type = [
            MotionsAnalyticsAvgByTypeItem(
                motion_type=row.motion_type,
                display_name=_MOTION_DISPLAY_NAMES.get(row.motion_type, row.motion_type),
                avg_seconds=round(float(row.avg_secs), 2),
            )
            for row in avg_type_rows
            if row.avg_secs is not None
        ]

        # --------------------------------------------------------------
        # KPI 4: by_cos_type (completed rows only — cos_type IS NOT NULL)
        # --------------------------------------------------------------
        cos_rows = await db.execute(
            text("""
                SELECT cos_type, COUNT(*) AS cnt
                FROM motion_draft_logs
                WHERE created_at >= :start AND created_at <= :end
                  AND cos_type IS NOT NULL
                GROUP BY cos_type
            """),
            range_params,
        )
        cos_map: dict[str, int] = {row.cos_type: int(row.cnt) for row in cos_rows}
        by_cos_type = MotionsAnalyticsByCosType(
            with_notice_of_hearing=cos_map.get("WithNoticeOfHearing", 0),
            without_notice_of_hearing=cos_map.get("WithoutNoticeOfHearing", 0),
            no=cos_map.get("No", 0),
        )

        # --------------------------------------------------------------
        # KPI 5: cos_type_ranking per motion_type
        # --------------------------------------------------------------
        cos_ranking_rows = await db.execute(
            text("""
                SELECT motion_type, cos_type, COUNT(*) AS cnt
                FROM motion_draft_logs
                WHERE created_at >= :start AND created_at <= :end
                  AND cos_type IN ('WithNoticeOfHearing', 'WithoutNoticeOfHearing')
                GROUP BY motion_type, cos_type
                ORDER BY cnt DESC
            """),
            range_params,
        )
        cos_buckets: dict[str, list] = defaultdict(list)
        for row in cos_ranking_rows:
            cos_buckets[row.cos_type].append(
                MotionsAnalyticsCosRankingItem(
                    motion_type=row.motion_type,
                    display_name=_MOTION_DISPLAY_NAMES.get(row.motion_type, row.motion_type),
                    count=int(row.cnt),
                )
            )
        cos_type_ranking = MotionsAnalyticsCosTypeRanking(
            with_notice_of_hearing=sorted(
                cos_buckets.get("WithNoticeOfHearing", []),
                key=lambda x: -x.count,
            ),
            without_notice_of_hearing=sorted(
                cos_buckets.get("WithoutNoticeOfHearing", []),
                key=lambda x: -x.count,
            ),
        )

        # --------------------------------------------------------------
        # KPI 6: by_district (LATERAL join to latest chat_thread)
        # --------------------------------------------------------------
        district_rows = await db.execute(
            text("""
                SELECT COALESCE(ct.district, 'other') AS district,
                       COUNT(*) AS total_attempted,
                       COUNT(*) FILTER (WHERE m.status = 'completed') AS completed
                FROM motion_draft_logs m
                INNER JOIN sessions s ON s.id = m.session_id
                LEFT JOIN LATERAL (
                    SELECT district FROM chat_threads
                    WHERE session_id = s.id ORDER BY created_at DESC LIMIT 1
                ) ct ON true
                WHERE m.created_at >= :start AND m.created_at <= :end
                GROUP BY COALESCE(ct.district, 'other')
            """),
            range_params,
        )
        known_districts = {"flnb", "flmb", "flsb", "pawb"}
        district_attempted: dict[str, int] = {}
        district_completed: dict[str, int] = {}
        for row in district_rows:
            key = row.district if row.district in known_districts else "other"
            district_attempted[key] = district_attempted.get(key, 0) + int(row.total_attempted)
            district_completed[key] = district_completed.get(key, 0) + int(row.completed)

        def _district_item(key: str) -> MotionsAnalyticsDistrictItem:
            return MotionsAnalyticsDistrictItem(
                completed=district_completed.get(key, 0),
                total_attempted=district_attempted.get(key, 0),
            )

        by_district = MotionsAnalyticsByDistrict(
            flnb=_district_item("flnb"),
            flmb=_district_item("flmb"),
            flsb=_district_item("flsb"),
            pawb=_district_item("pawb"),
            other=_district_item("other"),
        )

        kpis = MotionsAnalyticsKpis(
            total=total_cnt,
            by_status=MotionsAnalyticsKpisByStatus(
                pending=pending_cnt,
                completed=completed_cnt,
                failed=failed_cnt,
                cancelled=cancelled_cnt,
            ),
            success_rate_pct=success_rate,
            avg_processing_seconds=global_avg_secs,
            by_type=MotionsAnalyticsByType(
                motions=motion_type_items,
                orders=order_type_items,
            ),
            by_district=by_district,
            by_cos_type=by_cos_type,
            cos_type_ranking=cos_type_ranking,
            motion_type_ranking=motion_type_ranking,
            avg_processing_by_type=avg_processing_by_type,
        )

        # --------------------------------------------------------------
        # List query — dynamic WHERE, paginated
        # --------------------------------------------------------------
        base_list_sql = f"""
            SELECT
                m.id AS task_id,
                m.session_id,
                m.motion_type,
                m.status,
                m.cos_type,
                m.case_number,
                m.case_name,
                m.created_at,
                m.completed_at,
                EXTRACT(EPOCH FROM (m.completed_at - m.created_at)) AS processing_seconds,
                s.user_id,
                pd.source,
                ct.title    AS debtor_name,
                ct.district
            FROM motion_draft_logs m
            INNER JOIN sessions s ON s.id = m.session_id
            LEFT JOIN LATERAL (
                SELECT title, district FROM chat_threads
                WHERE session_id = s.id ORDER BY created_at DESC LIMIT 1
            ) ct ON true
            LEFT JOIN LATERAL (
                SELECT source FROM pdf_documents
                WHERE session_id = s.id ORDER BY uploaded_at DESC LIMIT 1
            ) pd ON true
            WHERE {where_sql}
        """

        all_params = {**range_params, **list_extra}

        count_result = await db.execute(
            text(f"SELECT COUNT(*) FROM ({base_list_sql}) AS _q"),
            all_params,
        )
        total_filtered: int = count_result.scalar() or 0

        if total_filtered == 0:
            return MotionsAnalyticsResponse(
                kpis=kpis,
                pagination=MotionsAnalyticsPagination(page=page, page_size=page_size, total=0),
                motions=[],
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
    # Resolve actor names — single batch query to user_db
    # ------------------------------------------------------------------
    user_ids: set[str] = {row.user_id for row in list_rows if row.user_id}
    user_name_map = await _fetch_user_names(user_ids)

    motions: list[MotionAnalyticsItem] = [
        MotionAnalyticsItem(
            task_id=row.task_id,
            session_id=row.session_id,
            case_number=row.case_number,
            case_name=row.case_name.replace("\n", " & ") if isinstance(row.case_name, str) else row.case_name,
            debtor_name=row.debtor_name.replace("\n", " & ") if isinstance(row.debtor_name, str) else row.debtor_name,
            district=row.district,
            motion_type=row.motion_type,
            display_name=_MOTION_DISPLAY_NAMES.get(row.motion_type, row.motion_type),
            category=_category(row.motion_type),
            status=row.status,
            cos_type=row.cos_type,
            source=row.source,
            created_at=row.created_at,
            completed_at=row.completed_at,
            processing_seconds=(
                round(float(row.processing_seconds), 2)
                if row.processing_seconds is not None
                else None
            ),
            actor_user_id=row.user_id,
            actor_name=user_name_map.get(row.user_id) if row.user_id else None,
        )
        for row in list_rows
    ]

    return MotionsAnalyticsResponse(
        kpis=kpis,
        pagination=MotionsAnalyticsPagination(
            page=page,
            page_size=page_size,
            total=total_filtered,
        ),
        motions=motions,
        date_range=DateRangeInfo(preset=dr.range, start=dr.start, end=dr.end),
    )


# ---------------------------------------------------------------------------
# GET /motions/session/{session_id}
# ---------------------------------------------------------------------------

@router.get("/motions/sessions/{session_id}", response_model=SessionMotionsResponse)
async def get_session_motions(
    session_id: str,
    _user: User = Depends(get_current_firm_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort_by: str = Query(
        "created_at",
        pattern="^(created_at|status|motion_type|processing_seconds)$",
    ),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    status: Optional[str] = Query(None, pattern="^(pending|completed|failed|cancelled)$"),
    category: Optional[str] = Query(None, pattern="^(motion|order)$"),
    motion_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="ILIKE on case_number"),
):
    """
    Returns motions drafted for a specific case/session with summary KPIs,
    by_type breakdown (motions vs orders), and a filtered, paginated motion list.
    KPIs always reflect all session motions regardless of list filters.
    """
    sort_col = {
        "created_at":         "m.created_at",
        "status":             "m.status",
        "motion_type":        "m.motion_type",
        "processing_seconds": "processing_seconds",
    }[sort_by]
    order = "DESC" if sort_dir == "desc" else "ASC"

    async with AsyncSessionLocal() as db:

        # ------------------------------------------------------------------
        # Case context — latest chat_thread for debtor_name + district
        # ------------------------------------------------------------------
        context_result = await db.execute(
            text("""
                SELECT
                    s.id AS session_id,
                    ct.case_number,
                    ct.title    AS debtor_name,
                    ct.district
                FROM sessions s
                LEFT JOIN LATERAL (
                    SELECT case_number, title, district
                    FROM chat_threads
                    WHERE session_id = s.id ORDER BY created_at DESC LIMIT 1
                ) ct ON true
                WHERE s.id = :sid
            """),
            {"sid": session_id},
        )
        context = context_result.fetchone()
        if context is None:
            raise HTTPException(status_code=404, detail="Session not found")

        # ------------------------------------------------------------------
        # Query A — all motions (unfiltered) for KPIs + by_type
        # ------------------------------------------------------------------
        motions_result = await db.execute(
            text("""
                SELECT m.id, m.motion_type, m.status, m.cos_type, m.created_at, m.completed_at,
                       EXTRACT(EPOCH FROM (m.completed_at - m.created_at)) AS processing_seconds,
                       s.user_id
                FROM motion_draft_logs m
                INNER JOIN sessions s ON s.id = m.session_id
                WHERE m.session_id = :sid
            """),
            {"sid": session_id},
        )
        motion_rows = motions_result.fetchall()

        # ------------------------------------------------------------------
        # Query B — filtered + paginated list
        # ------------------------------------------------------------------
        where_clauses: list[str] = ["m.session_id = :sid"]
        list_params: dict = {"sid": session_id}

        if status:
            where_clauses.append("m.status = :status_filter")
            list_params["status_filter"] = status

        if category == "order":
            list_params["type_keys"] = list(_ORDER_KEYS)
            where_clauses.append("m.motion_type = ANY(:type_keys)")
        elif category == "motion":
            list_params["type_keys"] = list(_ORDER_KEYS)
            where_clauses.append("m.motion_type != ALL(:type_keys)")

        if motion_type:
            where_clauses.append("m.motion_type = :motion_type_filter")
            list_params["motion_type_filter"] = motion_type

        if search:
            where_clauses.append("m.case_number ILIKE :search_pat")
            list_params["search_pat"] = f"%{search.strip()}%"

        where_sql = " AND ".join(where_clauses)

        base_list_sql = f"""
            SELECT m.id, m.motion_type, m.status, m.cos_type, m.created_at, m.completed_at,
                   EXTRACT(EPOCH FROM (m.completed_at - m.created_at)) AS processing_seconds,
                   s.user_id
            FROM motion_draft_logs m
            INNER JOIN sessions s ON s.id = m.session_id
            WHERE {where_sql}
        """

        count_result = await db.execute(
            text(f"SELECT COUNT(*) FROM ({base_list_sql}) AS _q"),
            list_params,
        )
        total_filtered: int = count_result.scalar() or 0

        if total_filtered > 0:
            offset = (page - 1) * page_size
            list_result = await db.execute(
                text(
                    f"{base_list_sql}"
                    f" ORDER BY {sort_col} {order} NULLS LAST"
                    f" LIMIT :limit OFFSET :offset"
                ),
                {**list_params, "limit": page_size, "offset": offset},
            )
            list_rows = list_result.fetchall()
        else:
            list_rows = []

    # ------------------------------------------------------------------
    # Resolve actor names for the paginated list — single batch query
    # ------------------------------------------------------------------
    list_user_ids: set[str] = {r.user_id for r in list_rows if r.user_id}
    user_name_map = await _fetch_user_names(list_user_ids)

    # ------------------------------------------------------------------
    # Build KPIs + by_type from all session rows (unfiltered)
    # ------------------------------------------------------------------
    total_motions_and_orders = len(motion_rows)
    total_motions = sum(1 for r in motion_rows if r.motion_type not in _ORDER_KEYS)
    total_orders  = sum(1 for r in motion_rows if r.motion_type in _ORDER_KEYS)

    completed_cnt = sum(1 for r in motion_rows if r.status == "completed")
    pending_cnt   = sum(1 for r in motion_rows if r.status == "pending")
    failed_cnt    = sum(1 for r in motion_rows if r.status == "failed")
    cancelled_cnt = sum(1 for r in motion_rows if r.status == "cancelled")

    completed_secs = [
        float(r.processing_seconds)
        for r in motion_rows
        if r.status == "completed" and r.processing_seconds is not None
    ]
    avg_processing = round(sum(completed_secs) / len(completed_secs), 2) if completed_secs else None

    total_cos_generated = sum(
        1 for r in motion_rows
        if r.status == "completed"
        and r.cos_type in ("WithNoticeOfHearing", "WithoutNoticeOfHearing")
    )
    cos_with_notice    = sum(
        1 for r in motion_rows
        if r.status == "completed" and r.cos_type == "WithNoticeOfHearing"
    )
    cos_without_notice = sum(
        1 for r in motion_rows
        if r.status == "completed" and r.cos_type == "WithoutNoticeOfHearing"
    )

    # by_type — completed + total_attempted per motion_type, split motions vs orders
    type_attempted: dict[str, int] = defaultdict(int)
    type_completed: dict[str, int] = defaultdict(int)
    for r in motion_rows:
        type_attempted[r.motion_type] += 1
        if r.status == "completed":
            type_completed[r.motion_type] += 1

    all_types = sorted(type_attempted.keys(), key=lambda mt: -type_completed[mt])
    session_motion_items: list[SessionMotionsByTypeItem] = []
    session_order_items: list[SessionMotionsByTypeItem] = []
    for mt in all_types:
        item = SessionMotionsByTypeItem(
            motion_type=mt,
            display_name=_MOTION_DISPLAY_NAMES.get(mt, mt),
            category="order" if mt in _ORDER_KEYS else "motion",
            completed=type_completed[mt],
            total_attempted=type_attempted[mt],
        )
        if mt in _ORDER_KEYS:
            session_order_items.append(item)
        else:
            session_motion_items.append(item)

    motions: list[SessionMotionItem] = [
        SessionMotionItem(
            task_id=r.id,
            motion_type=r.motion_type,
            display_name=_MOTION_DISPLAY_NAMES.get(r.motion_type, r.motion_type),
            category=_category(r.motion_type),
            status=r.status,
            cos_type=r.cos_type,
            created_at=r.created_at,
            completed_at=r.completed_at,
            processing_seconds=(
                round(float(r.processing_seconds), 2)
                if r.processing_seconds is not None
                else None
            ),
            actor_user_id=r.user_id,
            actor_name=user_name_map.get(r.user_id) if r.user_id else None,
        )
        for r in list_rows
    ]

    return SessionMotionsResponse(
        session_id=session_id,
        case_number=context.case_number,
        debtor_name=context.debtor_name,
        district=context.district,
        kpis=SessionMotionSummaryKpis(
            total_motions_and_orders=total_motions_and_orders,
            total_motions=total_motions,
            total_orders=total_orders,
            completed=completed_cnt,
            pending=pending_cnt,
            failed=failed_cnt,
            cancelled=cancelled_cnt,
            avg_processing_seconds=avg_processing,
            total_cos_generated=total_cos_generated,
            cos_with_notice_of_hearing=cos_with_notice,
            cos_without_notice_of_hearing=cos_without_notice,
        ),
        by_type=SessionMotionsByType(
            motions=session_motion_items,
            orders=session_order_items,
        ),
        pagination=SessionMotionsPagination(
            page=page,
            page_size=page_size,
            total=total_filtered,
        ),
        motions=motions,
    )
