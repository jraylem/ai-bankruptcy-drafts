"""
Analytics sub-page: User Detail.

GET /analytics/users/{user_id} → /api/dashboard/analytics/users/{user_id}

Cross-DB strategy (same as analytics_users.py):
  - User identity lives in user_db (auth database).
  - All behavioral data (sessions, motions, activity) lives in chat_db.
  - Application-level merge: user identity fetched first, then chat_db queries.

Sessions table filters are applied in SQL (source, status, search, sort).
Activity table status filter is applied in Python (derived via motion_draft_logs),
all other activity filters and non-derived sorts are applied in SQL.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text

from ...auth.models import User
from ...common.dependencies import get_current_firm_user
from ...auth.database import UserAsyncSessionLocal
from ...chatbot.database import AsyncSessionLocal
from ._shared import DateRangeParams, DateRangeInfo, _ACTION_LABELS, _build_activity_detail

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analytics"])


# ---------------------------------------------------------------------------
# Motion actions that can have a derived status from motion_draft_logs
# (mirrors activity_log.py — kept in sync manually)
# ---------------------------------------------------------------------------

_MOTION_ACTIONS = frozenset({
    "draft_motion",
    "generate_document",
    "download_motion",
    "pleading_task_input",
    "pleading_task_cancel",
    "pleading_task_regenerate",
    "pleading_use_existing",
})

_ACTION_DERIVED_STATUS: dict[str, str] = {
    "accept_case":  "accepted",
    "deny_case":    "denied",
    "archive_case": "archived",
    "login":        "success",
    "logout":       "success",
    "register":     "success",
}


# ---------------------------------------------------------------------------
# Internal query function — called by analytics_insights.py chat tools
# ---------------------------------------------------------------------------

async def _query_user_detail(user_id: str, start: datetime, end: datetime) -> dict:
    """
    Called by: _execute_chat_tool (analytics_insights.py)
    Returns KPI summary, activity trend, top motion types, last 5 sessions,
    and last 10 activity events for a single user.
    No pagination — fixed slices suitable for Claude context injection.
    """
    range_params = {"user_id": user_id, "start": start, "end": end}

    # ── Step 1: user_db — identity ────────────────────────────────────────
    async with UserAsyncSessionLocal() as user_db:
        u_result = await user_db.execute(
            text("""
                SELECT id, email, first_name, last_name, created_at
                FROM users WHERE id = :user_id AND is_active = true
            """),
            {"user_id": user_id},
        )
        u = u_result.fetchone()

    if not u:
        return {"error": f"User {user_id} not found"}

    name = " ".join(filter(None, [u.first_name, u.last_name])) or u.email

    # ── Step 2: chat_db — KPIs, trend, top motion types ──────────────────
    async with AsyncSessionLocal() as chat_db:
        kpi_result = await chat_db.execute(
            text("""
                SELECT
                    COUNT(*) FILTER (WHERE action = 'login')             AS login_count,
                    COUNT(DISTINCT DATE(created_at AT TIME ZONE 'UTC'))  AS active_days,
                    COUNT(*) FILTER (WHERE action = 'generate_document') AS docs_exported
                FROM user_activity_logs
                WHERE user_id = :user_id
                  AND created_at >= :start AND created_at <= :end
            """),
            range_params,
        )
        kpi_row = kpi_result.fetchone()

        last_active_result = await chat_db.execute(
            text("""
                SELECT MAX(created_at) AS last_active_at
                FROM user_activity_logs WHERE user_id = :user_id
            """),
            {"user_id": user_id},
        )
        last_active_at_raw = last_active_result.scalar()

        sess_count_result = await chat_db.execute(
            text("""
                SELECT COUNT(*) AS cnt FROM sessions
                WHERE user_id = :user_id
                  AND created_at >= :start AND created_at <= :end
            """),
            range_params,
        )
        sessions_created = int(sess_count_result.scalar() or 0)

        motions_kpi_result = await chat_db.execute(
            text("""
                SELECT
                    COUNT(*) AS motions_started,
                    COUNT(*) FILTER (WHERE m.status = 'completed') AS motions_completed,
                    AVG(
                        CASE
                            WHEN m.status = 'completed' AND m.completed_at IS NOT NULL
                            THEN EXTRACT(EPOCH FROM (m.completed_at - m.created_at))
                        END
                    ) AS avg_draft_seconds
                FROM motion_draft_logs m
                INNER JOIN sessions s ON s.id = m.session_id
                WHERE s.user_id = :user_id
                  AND m.created_at >= :start AND m.created_at <= :end
            """),
            range_params,
        )
        mk = motions_kpi_result.fetchone()
        motions_started   = int(mk.motions_started or 0)
        motions_completed = int(mk.motions_completed or 0)
        avg_draft_seconds = (
            float(mk.avg_draft_seconds) if mk.avg_draft_seconds is not None else None
        )
        draft_success_rate = (
            round(motions_completed * 100.0 / motions_started, 1)
            if motions_started > 0 else 0.0
        )

        motions_trend_result = await chat_db.execute(
            text("""
                SELECT DATE(m.created_at AT TIME ZONE 'UTC') AS day, COUNT(*) AS motions
                FROM motion_draft_logs m
                INNER JOIN sessions s ON s.id = m.session_id
                WHERE s.user_id = :user_id
                  AND m.created_at >= :start AND m.created_at <= :end
                GROUP BY DATE(m.created_at AT TIME ZONE 'UTC')
            """),
            range_params,
        )
        motions_by_day: dict[date, int] = {r.day: int(r.motions) for r in motions_trend_result}

        activity_trend_result = await chat_db.execute(
            text("""
                SELECT
                    DATE(created_at AT TIME ZONE 'UTC') AS day,
                    COUNT(DISTINCT DATE_TRUNC('minute', created_at))::int AS active_minutes
                FROM user_activity_logs
                WHERE user_id = :user_id
                  AND created_at >= :start AND created_at <= :end
                GROUP BY DATE(created_at AT TIME ZONE 'UTC')
            """),
            range_params,
        )
        active_minutes_by_day: dict[date, int] = {
            r.day: int(r.active_minutes) for r in activity_trend_result
        }

        top_motions_result = await chat_db.execute(
            text("""
                SELECT m.motion_type,
                       COUNT(*) AS drafted,
                       COUNT(*) FILTER (WHERE m.status = 'completed') AS completed
                FROM motion_draft_logs m
                INNER JOIN sessions s ON s.id = m.session_id
                WHERE s.user_id = :user_id
                  AND m.created_at >= :start AND m.created_at <= :end
                GROUP BY m.motion_type
                ORDER BY drafted DESC
                LIMIT 10
            """),
            range_params,
        )
        top_motion_types = [
            {
                "motion_type": r.motion_type,
                "drafted":     int(r.drafted),
                "completed":   int(r.completed),
            }
            for r in top_motions_result
        ]

    # Build trend array — one entry per day in range
    trend: list[dict] = []
    current_day = start.date()
    end_day = end.date()
    while current_day <= end_day:
        trend.append({
            "day":            current_day.isoformat(),
            "motions":        motions_by_day.get(current_day, 0),
            "active_minutes": active_minutes_by_day.get(current_day, 0),
        })
        current_day += timedelta(days=1)

    # ── Step 3: chat_db — recent sessions (last 5, no date filter) ───────
    async with AsyncSessionLocal() as chat_db:
        sess_result = await chat_db.execute(
            text("""
                WITH lp AS (
                    SELECT DISTINCT ON (session_id) session_id, petition_status, source
                    FROM pdf_documents ORDER BY session_id, uploaded_at DESC
                )
                SELECT
                    s.id AS session_id,
                    ct.case_number, ct.title AS debtor_name, ct.district,
                    lp.source, lp.petition_status,
                    COALESCE(sm.motions_count, 0)::int AS motions_count,
                    sla.last_activity_at
                FROM sessions s
                LEFT JOIN LATERAL (
                    SELECT case_number, title, district FROM chat_threads
                    WHERE session_id = s.id AND is_active = true
                    ORDER BY created_at DESC LIMIT 1
                ) ct ON true
                LEFT JOIN lp ON lp.session_id = s.id
                LEFT JOIN LATERAL (
                    SELECT COUNT(*)::int AS motions_count
                    FROM motion_draft_logs WHERE session_id = s.id
                ) sm ON true
                LEFT JOIN LATERAL (
                    SELECT MAX(created_at) AS last_activity_at
                    FROM user_activity_logs WHERE session_id = s.id
                ) sla ON true
                WHERE s.user_id = :user_id AND s.is_active = true
                ORDER BY sla.last_activity_at DESC NULLS LAST
                LIMIT 5
            """),
            {"user_id": user_id},
        )
        recent_sessions = [
            {
                "session_id":      row.session_id,
                "case_number":     row.case_number,
                "debtor_name":     row.debtor_name,
                "district":        row.district,
                "source":          row.source or "manual",
                "petition_status": row.petition_status,
                "motions_count":   int(row.motions_count),
                "last_activity_at": (
                    row.last_activity_at.isoformat() if row.last_activity_at else None
                ),
            }
            for row in sess_result
        ]

    # ── Step 4: chat_db — recent activity (last 10, no date filter) ──────
    async with AsyncSessionLocal() as chat_db:
        act_result = await chat_db.execute(
            text("""
                SELECT id, action, session_id, activity_metadata, created_at
                FROM user_activity_logs
                WHERE user_id = :user_id
                ORDER BY created_at DESC
                LIMIT 10
            """),
            {"user_id": user_id},
        )
        recent_activity = [
            {
                "occurred_at": row.created_at.isoformat() if row.created_at else None,
                "action":      row.action,
                "label":       _ACTION_LABELS.get(row.action, row.action),
                "detail":      _build_activity_detail(row.action, row.activity_metadata or {}),
                "entity_id":   row.session_id,
                "status":      _ACTION_DERIVED_STATUS.get(row.action),
            }
            for row in act_result
        ]

    return {
        "user_id":                str(u.id),
        "name":                   name,
        "email":                  u.email,
        "joined_at":              u.created_at.isoformat() if u.created_at else None,
        "last_active_at":         last_active_at_raw.isoformat() if last_active_at_raw else None,
        "login_count":            int(kpi_row.login_count or 0),
        "active_days":            int(kpi_row.active_days or 0),
        "sessions_created":       sessions_created,
        "motions_started":        motions_started,
        "motions_completed":      motions_completed,
        "draft_success_rate":     draft_success_rate,
        "avg_draft_time_seconds": avg_draft_seconds,
        "documents_exported":     int(kpi_row.docs_exported or 0),
        "trend":                  trend,
        "top_motion_types":       top_motion_types,
        "recent_sessions":        recent_sessions,
        "recent_activity":        recent_activity,
    }


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class TrendDay(BaseModel):
    day: str
    motions: int
    activeMinutes: int


class TopMotionType(BaseModel):
    motion_type: str
    drafted: int
    completed: int


class SessionItem(BaseModel):
    session_id: str
    case_number: Optional[str]
    debtor_name: Optional[str]
    district: Optional[str]
    source: Optional[str]
    petition_status: Optional[str]
    motions_count: int
    last_activity_at: Optional[str]


class ActivityItem(BaseModel):
    id: str
    occurred_at: str
    action: str
    detail: Optional[str]
    entity_id: Optional[str]
    status: Optional[str]
    duration_ms: Optional[float]


class Pagination(BaseModel):
    page: int
    page_size: int
    total: int


class UserDetailResponse(BaseModel):
    user_id: str
    name: str
    email: str
    joined_at: Optional[str]
    last_active_at: Optional[str]

    login_count_30d: int
    active_days_30d: int
    sessions_created_30d: int
    motions_started_30d: int
    motions_completed_30d: int
    draft_success_rate: float
    avg_draft_time_seconds: Optional[float]
    documents_exported_30d: int

    trend_30d: list[TrendDay]
    top_motion_types: list[TopMotionType]

    recent_sessions: list[SessionItem]
    recent_sessions_pagination: Pagination

    recent_activity: list[ActivityItem]
    recent_activity_pagination: Pagination

    date_range: DateRangeInfo


# ---------------------------------------------------------------------------
# GET /users/{user_id}
# ---------------------------------------------------------------------------

@router.get("/users/{user_id}", response_model=UserDetailResponse)
async def get_user_detail(
    user_id: str,
    dr: DateRangeParams = Depends(),
    _user: User = Depends(get_current_firm_user),
    # Sessions table params
    sessions_page: int = Query(1, ge=1),
    sessions_page_size: int = Query(10, ge=1, le=100),
    sessions_search: Optional[str] = Query(None),
    sessions_source: Optional[str] = Query(
        None, pattern="^(manual|ecf|gdrive|courtdrive)$"
    ),
    sessions_status: Optional[str] = Query(
        None, pattern="^(working|accepted|pending_acceptance|archived)$"
    ),
    sessions_sort_by: str = Query(
        "last_activity",
        pattern="^(case|district|source|status|motions|last_activity)$",
    ),
    sessions_sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    # Activity table params
    activity_page: int = Query(1, ge=1),
    activity_page_size: int = Query(10, ge=1, le=100),
    activity_search: Optional[str] = Query(None),
    activity_action: Optional[str] = Query(
        None,
        pattern="^(draft_motion|generate_document|download_motion|upload_pdf|accept_case)$",
    ),
    activity_status: Optional[str] = Query(
        None, pattern="^(completed|pending|failed)$"
    ),
    activity_sort_by: str = Query(
        "occurred",
        pattern="^(action|status|duration|occurred|entity)$",
    ),
    activity_sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
):
    """
    Returns full detail for a single user: KPI summary, 30-day activity trend,
    top motion types by volume, paginated recent sessions, and paginated recent
    activity — all scoped to the requested date range.

    Sessions and activity tables each support independent pagination, filtering,
    and sorting via their respective sessions_* / activity_* query params.
    """
    range_params = {"user_id": user_id, "start": dr.start, "end": dr.end}

    # ── Step 1: user_db — fetch user identity ─────────────────────────────
    async with UserAsyncSessionLocal() as user_db:
        user_result = await user_db.execute(
            text("""
                SELECT id, email, first_name, last_name, created_at
                FROM users WHERE id = :user_id AND is_active = true
            """),
            {"user_id": user_id},
        )
        u = user_result.fetchone()

    if not u:
        raise HTTPException(status_code=404, detail="User not found")

    name = " ".join(filter(None, [u.first_name, u.last_name])) or u.email

    # ── Step 2: chat_db — KPIs, last_active, trend, top motion types ──────
    async with AsyncSessionLocal() as chat_db:
        # Aggregate KPIs from user_activity_logs
        kpi_result = await chat_db.execute(
            text("""
                SELECT
                    COUNT(*) FILTER (WHERE action = 'login')             AS login_count,
                    COUNT(DISTINCT DATE(created_at AT TIME ZONE 'UTC'))  AS active_days,
                    COUNT(*) FILTER (WHERE action = 'generate_document') AS docs_exported
                FROM user_activity_logs
                WHERE user_id = :user_id
                  AND created_at >= :start AND created_at <= :end
            """),
            range_params,
        )
        kpi_row = kpi_result.fetchone()

        # Lifetime last_active_at (not date-range scoped)
        last_active_result = await chat_db.execute(
            text("""
                SELECT MAX(created_at) AS last_active_at
                FROM user_activity_logs
                WHERE user_id = :user_id
            """),
            {"user_id": user_id},
        )
        last_active_at_raw = last_active_result.scalar()

        # Sessions created in range
        sess_created_result = await chat_db.execute(
            text("""
                SELECT COUNT(*) AS cnt
                FROM sessions
                WHERE user_id = :user_id
                  AND created_at >= :start AND created_at <= :end
            """),
            range_params,
        )
        sessions_created_30d = int(sess_created_result.scalar() or 0)

        # Motion KPIs
        motions_kpi_result = await chat_db.execute(
            text("""
                SELECT
                    COUNT(*) AS motions_started,
                    COUNT(*) FILTER (WHERE m.status = 'completed') AS motions_completed,
                    AVG(
                        CASE
                            WHEN m.status = 'completed' AND m.completed_at IS NOT NULL
                            THEN EXTRACT(EPOCH FROM (m.completed_at - m.created_at))
                        END
                    ) AS avg_draft_seconds
                FROM motion_draft_logs m
                INNER JOIN sessions s ON s.id = m.session_id
                WHERE s.user_id = :user_id
                  AND m.created_at >= :start AND m.created_at <= :end
            """),
            range_params,
        )
        mk = motions_kpi_result.fetchone()
        motions_started = int(mk.motions_started or 0)
        motions_completed = int(mk.motions_completed or 0)
        avg_draft_seconds = (
            float(mk.avg_draft_seconds) if mk.avg_draft_seconds is not None else None
        )
        draft_success_rate = (
            round(motions_completed * 100.0 / motions_started, 1)
            if motions_started > 0
            else 0.0
        )

        # Trend: motions per day
        motions_trend_result = await chat_db.execute(
            text("""
                SELECT
                    DATE(m.created_at AT TIME ZONE 'UTC') AS day,
                    COUNT(*)                              AS motions
                FROM motion_draft_logs m
                INNER JOIN sessions s ON s.id = m.session_id
                WHERE s.user_id = :user_id
                  AND m.created_at >= :start AND m.created_at <= :end
                GROUP BY DATE(m.created_at AT TIME ZONE 'UTC')
            """),
            range_params,
        )
        motions_by_day: dict[date, int] = {r.day: int(r.motions) for r in motions_trend_result}

        # Trend: distinct active minutes per day (unique clock-minutes with any event)
        activity_trend_result = await chat_db.execute(
            text("""
                SELECT
                    DATE(created_at AT TIME ZONE 'UTC')                       AS day,
                    COUNT(DISTINCT DATE_TRUNC('minute', created_at))::int     AS active_minutes
                FROM user_activity_logs
                WHERE user_id = :user_id
                  AND created_at >= :start AND created_at <= :end
                GROUP BY DATE(created_at AT TIME ZONE 'UTC')
            """),
            range_params,
        )
        active_minutes_by_day: dict[date, int] = {
            r.day: int(r.active_minutes) for r in activity_trend_result
        }

        # Top motion types
        top_motions_result = await chat_db.execute(
            text("""
                SELECT
                    m.motion_type,
                    COUNT(*)                                           AS drafted,
                    COUNT(*) FILTER (WHERE m.status = 'completed')    AS completed
                FROM motion_draft_logs m
                INNER JOIN sessions s ON s.id = m.session_id
                WHERE s.user_id = :user_id
                  AND m.created_at >= :start AND m.created_at <= :end
                GROUP BY m.motion_type
                ORDER BY drafted DESC
                LIMIT 10
            """),
            range_params,
        )
        top_motion_types = [
            TopMotionType(
                motion_type=r.motion_type,
                drafted=int(r.drafted),
                completed=int(r.completed),
            )
            for r in top_motions_result
        ]

    # Build trend array — one entry per day in the date range
    trend_30d: list[TrendDay] = []
    current_day = dr.start.date()
    end_day = dr.end.date()
    while current_day <= end_day:
        trend_30d.append(TrendDay(
            day=current_day.strftime("%b %-d"),
            motions=motions_by_day.get(current_day, 0),
            activeMinutes=active_minutes_by_day.get(current_day, 0),
        ))
        current_day += timedelta(days=1)

    # ── Step 3: chat_db — sessions table ──────────────────────────────────
    sess_filters = ["s.user_id = :user_id", "s.is_active = true"]
    sess_params: dict = {"user_id": user_id}

    if sessions_source:
        sess_filters.append(
            "(lp.source = :sess_source OR (lp.source IS NULL AND :sess_source = 'manual'))"
        )
        sess_params["sess_source"] = sessions_source

    if sessions_status:
        sess_filters.append("lp.petition_status = :sess_status")
        sess_params["sess_status"] = sessions_status

    if sessions_search:
        sess_filters.append(
            "(LOWER(ct.case_number) LIKE :sess_search"
            " OR LOWER(ct.title)    LIKE :sess_search"
            " OR LOWER(s.id)        LIKE :sess_search"
            " OR LOWER(COALESCE(ct.district, '')) LIKE :sess_search)"
        )
        sess_params["sess_search"] = f"%{sessions_search.lower()}%"

    sess_where = " AND ".join(sess_filters)

    _SESS_SORT_COL: dict[str, str] = {
        "case":          "ct.case_number",
        "district":      "ct.district",
        "source":        "COALESCE(lp.source, 'manual')",
        "status":        "lp.petition_status",
        "motions":       "sm.motions_count",
        "last_activity": "sla.last_activity_at",
    }
    sess_order_col = _SESS_SORT_COL[sessions_sort_by]
    sess_order = f"{sess_order_col} {sessions_sort_dir.upper()} NULLS LAST"
    sess_offset = (sessions_page - 1) * sessions_page_size

    # Shared CTE fragment used by both count and data queries
    _SESS_LP_CTE = """
        WITH lp AS (
            SELECT DISTINCT ON (session_id) session_id, petition_status, source
            FROM pdf_documents
            ORDER BY session_id, uploaded_at DESC
        )
    """
    _SESS_LATERAL_CT = """
        LEFT JOIN LATERAL (
            SELECT case_number, title, district
            FROM chat_threads
            WHERE session_id = s.id
            ORDER BY is_active DESC, created_at DESC LIMIT 1
        ) ct ON true
    """

    async with AsyncSessionLocal() as chat_db:
        sess_count_result = await chat_db.execute(
            text(f"""
                {_SESS_LP_CTE}
                SELECT COUNT(*)
                FROM sessions s
                {_SESS_LATERAL_CT}
                LEFT JOIN lp ON lp.session_id = s.id
                WHERE {sess_where}
            """),
            sess_params,
        )
        sessions_total = int(sess_count_result.scalar() or 0)

        sess_data_result = await chat_db.execute(
            text(f"""
                {_SESS_LP_CTE}
                SELECT
                    s.id                                 AS session_id,
                    ct.case_number,
                    ct.title                             AS debtor_name,
                    ct.district,
                    lp.source,
                    lp.petition_status,
                    COALESCE(sm.motions_count, 0)::int   AS motions_count,
                    sla.last_activity_at
                FROM sessions s
                {_SESS_LATERAL_CT}
                LEFT JOIN lp ON lp.session_id = s.id
                LEFT JOIN LATERAL (
                    SELECT COUNT(*)::int AS motions_count
                    FROM motion_draft_logs
                    WHERE session_id = s.id
                ) sm ON true
                LEFT JOIN LATERAL (
                    SELECT MAX(created_at) AS last_activity_at
                    FROM user_activity_logs
                    WHERE session_id = s.id
                ) sla ON true
                WHERE {sess_where}
                ORDER BY {sess_order}
                LIMIT :limit OFFSET :offset
            """),
            {**sess_params, "limit": sessions_page_size, "offset": sess_offset},
        )

        recent_sessions = [
            SessionItem(
                session_id=row.session_id,
                case_number=row.case_number,
                debtor_name=row.debtor_name,
                district=row.district,
                source=row.source or "manual",
                petition_status=row.petition_status,
                motions_count=int(row.motions_count),
                last_activity_at=(
                    row.last_activity_at.isoformat()
                    if row.last_activity_at else None
                ),
            )
            for row in sess_data_result
        ]

    # ── Step 4: chat_db — activity table ──────────────────────────────────
    act_filters = [
        "user_id = :user_id",
        "created_at >= :start",
        "created_at <= :end",
    ]
    act_params: dict = {"user_id": user_id, "start": dr.start, "end": dr.end}

    if activity_action:
        act_filters.append("action = :act_action")
        act_params["act_action"] = activity_action

    if activity_search:
        act_filters.append(
            "(action ILIKE :act_search"
            " OR session_id ILIKE :act_search"
            " OR activity_metadata->>'motion_type'  ILIKE :act_search"
            " OR activity_metadata->>'case_number'  ILIKE :act_search)"
        )
        act_params["act_search"] = f"%{activity_search}%"

    act_where = " AND ".join(act_filters)

    # Status and duration sorts require Python-level derivation; all others go to SQL
    needs_python_sort = activity_sort_by in ("status", "duration")
    needs_python_filter = bool(activity_status)
    needs_python = needs_python_sort or needs_python_filter

    _ACT_SORT_COL: dict[str, str] = {
        "action":   "action",
        "occurred": "created_at",
        "entity":   "session_id",
    }
    act_order_col = _ACT_SORT_COL.get(activity_sort_by, "created_at")
    act_sql_order = f"{act_order_col} {activity_sort_dir.upper()} NULLS LAST"
    act_offset = (activity_page - 1) * activity_page_size

    async with AsyncSessionLocal() as chat_db:
        if needs_python:
            act_rows_result = await chat_db.execute(
                text(f"""
                    SELECT id, action, session_id, activity_metadata, created_at
                    FROM user_activity_logs
                    WHERE {act_where}
                    ORDER BY created_at DESC
                """),
                act_params,
            )
            all_act_rows = act_rows_result.fetchall()
            activity_total_sql = None
        else:
            act_count_result = await chat_db.execute(
                text(f"SELECT COUNT(*) FROM user_activity_logs WHERE {act_where}"),
                act_params,
            )
            activity_total_sql = int(act_count_result.scalar() or 0)

            act_rows_result = await chat_db.execute(
                text(f"""
                    SELECT id, action, session_id, activity_metadata, created_at
                    FROM user_activity_logs
                    WHERE {act_where}
                    ORDER BY {act_sql_order}
                    LIMIT :limit OFFSET :offset
                """),
                {**act_params, "limit": activity_page_size, "offset": act_offset},
            )
            all_act_rows = act_rows_result.fetchall()

    # Batch-resolve motion statuses from motion_draft_logs
    motion_session_ids = [
        r.session_id
        for r in all_act_rows
        if r.action in _MOTION_ACTIONS and r.session_id
    ]
    motion_status_map: dict[tuple[str, str], str] = {}
    if motion_session_ids:
        async with AsyncSessionLocal() as chat_db:
            mdl_result = await chat_db.execute(
                text("""
                    SELECT DISTINCT ON (session_id, motion_type)
                        session_id, motion_type, status
                    FROM motion_draft_logs
                    WHERE session_id = ANY(:session_ids)
                    ORDER BY session_id, motion_type, created_at DESC
                """),
                {"session_ids": motion_session_ids},
            )
            for r in mdl_result.fetchall():
                motion_status_map[(r.session_id, r.motion_type)] = r.status

    def _derive_status(action: str, meta: dict | None, session_id: str | None) -> Optional[str]:
        m = meta or {}
        if action in _MOTION_ACTIONS and session_id:
            mt = m.get("motion_type")
            if mt:
                return motion_status_map.get((session_id, mt))
        return _ACTION_DERIVED_STATUS.get(action)

    def _get_duration(meta: dict | None) -> Optional[float]:
        raw = (meta or {}).get("duration_ms")
        try:
            return float(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

    # Build activity items, applying Python-level status filter if needed
    activity_items: list[ActivityItem] = []
    for row in all_act_rows:
        meta = row.activity_metadata or {}
        status = _derive_status(row.action, meta, row.session_id)

        if needs_python_filter and status != activity_status:
            continue

        activity_items.append(ActivityItem(
            id=row.id,
            occurred_at=row.created_at.isoformat(),
            action=row.action,
            detail=_build_activity_detail(row.action, meta),
            entity_id=row.session_id,
            status=status,
            duration_ms=_get_duration(meta),
        ))

    # Apply Python-level sort when status or duration sort is requested
    if needs_python_sort:
        reverse = activity_sort_dir == "desc"
        if activity_sort_by == "status":
            activity_items.sort(key=lambda i: (i.status or ""), reverse=reverse)
        else:  # duration
            activity_items.sort(key=lambda i: (i.duration_ms or 0.0), reverse=reverse)

    if needs_python:
        activity_total = len(activity_items)
        page_activity = activity_items[act_offset: act_offset + activity_page_size]
    else:
        activity_total = activity_total_sql  # type: ignore[assignment]
        page_activity = activity_items

    # ── Assemble response ─────────────────────────────────────────────────
    return UserDetailResponse(
        user_id=u.id,
        name=name,
        email=u.email,
        joined_at=u.created_at.isoformat() if u.created_at else None,
        last_active_at=(
            last_active_at_raw.isoformat() if last_active_at_raw else None
        ),

        login_count_30d=int(kpi_row.login_count or 0),
        active_days_30d=int(kpi_row.active_days or 0),
        sessions_created_30d=sessions_created_30d,
        motions_started_30d=motions_started,
        motions_completed_30d=motions_completed,
        draft_success_rate=draft_success_rate,
        avg_draft_time_seconds=avg_draft_seconds,
        documents_exported_30d=int(kpi_row.docs_exported or 0),

        trend_30d=trend_30d,
        top_motion_types=top_motion_types,

        recent_sessions=recent_sessions,
        recent_sessions_pagination=Pagination(
            page=sessions_page,
            page_size=sessions_page_size,
            total=sessions_total,
        ),

        recent_activity=page_activity,
        recent_activity_pagination=Pagination(
            page=activity_page,
            page_size=activity_page_size,
            total=activity_total,
        ),

        date_range=DateRangeInfo(preset=dr.range, start=dr.start, end=dr.end),
    )
