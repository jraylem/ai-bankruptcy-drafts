"""
Analytics sub-page: User Directory.

GET /analytics/users  →  /api/dashboard/analytics/users

Cross-DB strategy:
  - User identity lives in user_db (auth database).
  - All behavioral data (sessions, motions, activity) lives in chat_db.
  - No SQL JOIN across databases is possible; application-level merge is used:
      1. Fetch all matching user IDs from user_db (search filter applied here).
      2. Compute global KPIs + lightweight sort-key aggregates in chat_db
         for all those user IDs.
      3. Sort by sort key and paginate in Python to get the current page IDs.
      4. Fetch full user identity from user_db for the page only.
      5. Fetch detailed behavioral data (cases, motions, recent_actions, etc.)
         from chat_db for the page only — O(page_size) regardless of total users.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
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
# Internal query function — called by analytics_insights.py chat tools
# ---------------------------------------------------------------------------

async def _query_users_list(
    start: datetime,
    end: datetime,
    search: Optional[str] = None,
    sort_by: str = "last_active",
    limit: int = 20,
) -> dict:
    """
    Called by: _execute_chat_tool (analytics_insights.py)
    Returns total_count (all matching users) and up to 50 rows with activity counts.
    total_count is derived from the full user ID list before the Python-side slice.
    """
    _dt_min = datetime.min.replace(tzinfo=timezone.utc)
    range_params = {"start": start, "end": end}

    async with UserAsyncSessionLocal() as user_db:
        if search:
            id_result = await user_db.execute(
                text("""
                    SELECT id, email, first_name, last_name, created_at FROM users
                    WHERE is_active = true
                      AND (LOWER(email) LIKE :pat
                           OR LOWER(COALESCE(first_name, '') || ' ' || COALESCE(last_name, '')) LIKE :pat)
                """),
                {"pat": f"%{search.lower()}%"},
            )
        else:
            id_result = await user_db.execute(
                text("SELECT id, email, first_name, last_name, created_at FROM users WHERE is_active = true")
            )
        user_rows = id_result.fetchall()

    if not user_rows:
        return {"total_count": 0, "returned": 0, "items": []}

    all_user_ids = [r.id for r in user_rows]
    user_info_map = {r.id: r for r in user_rows}
    created_at_map = {r.id: r.created_at for r in user_rows}

    async with AsyncSessionLocal() as chat_db:
        if sort_by == "last_active":
            sk_result = await chat_db.execute(
                text("""
                    SELECT user_id, MAX(created_at) AS sort_val
                    FROM user_activity_logs WHERE user_id = ANY(:ids)
                    GROUP BY user_id
                """),
                {"ids": all_user_ids},
            )
            sort_key_map: dict = {r.user_id: r.sort_val for r in sk_result}
            default_sort: object = _dt_min
        elif sort_by == "cases_count":
            sk_result = await chat_db.execute(
                text("""
                    WITH lp AS (
                        SELECT DISTINCT ON (session_id) session_id, petition_status
                        FROM pdf_documents ORDER BY session_id, uploaded_at DESC
                    )
                    SELECT s.user_id, COUNT(DISTINCT s.id) AS sort_val
                    FROM sessions s
                    INNER JOIN lp ON lp.session_id = s.id
                    INNER JOIN chat_threads ct ON ct.session_id = s.id AND ct.is_active = true
                    WHERE s.user_id = ANY(:ids) AND s.is_active = true
                      AND s.created_at >= :start AND s.created_at <= :end
                      AND (lp.petition_status IN ('working', 'accepted') OR lp.petition_status IS NULL)
                    GROUP BY s.user_id
                """),
                {"ids": all_user_ids, **range_params},
            )
            sort_key_map = {r.user_id: int(r.sort_val) for r in sk_result}
            default_sort = 0
        elif sort_by == "motions_drafted":
            sk_result = await chat_db.execute(
                text("""
                    SELECT s.user_id, COUNT(m.id) AS sort_val
                    FROM motion_draft_logs m
                    INNER JOIN sessions s ON s.id = m.session_id
                    WHERE s.user_id = ANY(:ids)
                      AND m.created_at >= :start AND m.created_at <= :end
                    GROUP BY s.user_id
                """),
                {"ids": all_user_ids, **range_params},
            )
            sort_key_map = {r.user_id: int(r.sort_val) for r in sk_result}
            default_sort = 0
        else:  # created_at
            sort_key_map = created_at_map
            default_sort = _dt_min

        last_active_result = await chat_db.execute(
            text("""
                SELECT user_id, MAX(created_at) AS last_active_at
                FROM user_activity_logs WHERE user_id = ANY(:ids)
                GROUP BY user_id
            """),
            {"ids": all_user_ids},
        )
        last_active_map: dict[str, datetime] = {r.user_id: r.last_active_at for r in last_active_result}

        cases_result = await chat_db.execute(
            text("""
                WITH lp AS (
                    SELECT DISTINCT ON (session_id) session_id, petition_status
                    FROM pdf_documents ORDER BY session_id, uploaded_at DESC
                )
                SELECT s.user_id, COUNT(DISTINCT s.id) AS cases_count
                FROM sessions s
                INNER JOIN lp ON lp.session_id = s.id
                INNER JOIN chat_threads ct ON ct.session_id = s.id AND ct.is_active = true
                WHERE s.user_id = ANY(:ids) AND s.is_active = true
                  AND s.created_at >= :start AND s.created_at <= :end
                  AND (lp.petition_status IN ('working', 'accepted') OR lp.petition_status IS NULL)
                GROUP BY s.user_id
            """),
            {"ids": all_user_ids, **range_params},
        )
        cases_map: dict[str, int] = {r.user_id: int(r.cases_count) for r in cases_result}

        motions_result = await chat_db.execute(
            text("""
                SELECT s.user_id, COUNT(m.id) AS motions_drafted
                FROM motion_draft_logs m
                INNER JOIN sessions s ON s.id = m.session_id
                WHERE s.user_id = ANY(:ids) AND m.created_at >= :start AND m.created_at <= :end
                GROUP BY s.user_id
            """),
            {"ids": all_user_ids, **range_params},
        )
        motions_map: dict[str, int] = {r.user_id: int(r.motions_drafted) for r in motions_result}

    total_count = len(all_user_ids)
    sorted_ids = sorted(
        all_user_ids,
        key=lambda uid: sort_key_map.get(uid) or default_sort,
        reverse=True,
    )[:min(limit, 50)]

    return {
        "total_count": total_count,
        "returned": len(sorted_ids),
        "items": [
            {
                "user_id": uid,
                "name": (
                    " ".join(filter(None, [user_info_map[uid].first_name, user_info_map[uid].last_name]))
                    or user_info_map[uid].email
                ),
                "email": user_info_map[uid].email,
                "created_at": (
                    user_info_map[uid].created_at.isoformat()
                    if user_info_map[uid].created_at else None
                ),
                "last_active_at": (
                    last_active_map[uid].isoformat() if last_active_map.get(uid) else None
                ),
                "cases_count": cases_map.get(uid, 0),
                "motions_drafted": motions_map.get(uid, 0),
            }
            for uid in sorted_ids
            if uid in user_info_map
        ],
    }


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class UsersAnalyticsKpis(BaseModel):
    total_users: int
    new_in_range: int
    active_in_range: int
    avg_motions_per_user: float


class MotionSummary(BaseModel):
    motion_type: str
    status: str
    created_at: datetime
    completed_at: Optional[datetime]


_METADATA_KEYS = ("motion_type", "case_name", "method", "path", "status_code", "duration_ms")


class RecentAction(BaseModel):
    action: str
    label: str
    detail: Optional[str]
    entity_id: Optional[str]
    timestamp: datetime
    metadata: Optional[dict]


class UserAnalyticsItem(BaseModel):
    user_id: str
    name: str
    email: str
    created_at: datetime
    last_active_at: Optional[datetime]
    cases_count: int
    motions_drafted: int
    avg_draft_time_seconds: Optional[float]
    top_motion_types: list[str]
    recent_actions: list[RecentAction]


class UsersPagination(BaseModel):
    page: int
    page_size: int
    total: int


class UsersAnalyticsResponse(BaseModel):
    kpis: UsersAnalyticsKpis
    pagination: UsersPagination
    users: list[UserAnalyticsItem]
    date_range: DateRangeInfo


# ---------------------------------------------------------------------------
# GET /users
# ---------------------------------------------------------------------------

@router.get("/users", response_model=UsersAnalyticsResponse)
async def get_users_analytics(
    dr: DateRangeParams = Depends(),
    _user: User = Depends(get_current_firm_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort_by: str = Query("last_active", pattern="^(last_active|cases_count|motions_drafted|created_at)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    search: Optional[str] = Query(None, description="Filter by name or email (case-insensitive substring)"),
):
    """
    Returns user directory with per-user KPIs and an aggregate summary.

    Scalable cross-DB strategy:
      1. Fetch all matching user IDs from user_db (search applied here, lightweight).
      2. Compute global KPIs + one sort-key aggregate in chat_db for all IDs.
      3. Sort by key + paginate in Python → page_ids (O(n log n) on IDs only).
      4. Fetch full user identity from user_db for page_ids only.
      5. Fetch all detailed behavioral data from chat_db for page_ids only.

    Detailed queries (recent_actions, top_motions, cases, motions) are always
    O(page_size), not O(total_users).
    """
    range_params = {"start": dr.start, "end": dr.end}
    _dt_min = datetime.min.replace(tzinfo=timezone.utc)

    # ── Step 1: user_db — global KPIs + all matching user IDs ────────────
    async with UserAsyncSessionLocal() as user_db:
        total_result = await user_db.execute(
            text("SELECT COUNT(*) FROM users WHERE is_active = true")
        )
        total_users: int = total_result.scalar() or 0

        new_result = await user_db.execute(
            text("""
                SELECT COUNT(*) FROM users
                WHERE is_active = true
                  AND created_at >= :start AND created_at <= :end
            """),
            range_params,
        )
        new_in_range: int = new_result.scalar() or 0

        if search:
            id_result = await user_db.execute(
                text("""
                    SELECT id, created_at FROM users
                    WHERE is_active = true
                      AND (LOWER(email) LIKE :pat
                           OR LOWER(COALESCE(first_name, '') || ' ' || COALESCE(last_name, '')) LIKE :pat)
                """),
                {"pat": f"%{search.lower()}%"},
            )
        else:
            id_result = await user_db.execute(
                text("SELECT id, created_at FROM users WHERE is_active = true")
            )
        id_rows = id_result.fetchall()

    all_user_ids: list[str] = [r.id for r in id_rows]
    created_at_map: dict[str, datetime] = {r.id: r.created_at for r in id_rows}
    total_filtered = len(all_user_ids)

    if not all_user_ids:
        return UsersAnalyticsResponse(
            kpis=UsersAnalyticsKpis(
                total_users=total_users,
                new_in_range=new_in_range,
                active_in_range=0,
                avg_motions_per_user=0.0,
            ),
            pagination=UsersPagination(page=page, page_size=page_size, total=0),
            users=[],
            date_range=DateRangeInfo(preset=dr.range, start=dr.start, end=dr.end),
        )

    # ── Step 2: chat_db — global KPIs + sort-key aggregate ───────────────
    async with AsyncSessionLocal() as chat_db:
        # Fetch distinct user_ids with activity in range, then intersect with
        # all_user_ids in Python. This avoids ANY(:ids) binding unreliability
        # with raw text() and prevents active_in_range from ever exceeding
        # total_users due to stale/deleted user records in the activity log.
        active_result = await chat_db.execute(
            text("""
                SELECT DISTINCT user_id
                FROM user_activity_logs
                WHERE user_id IS NOT NULL
                  AND created_at >= :start AND created_at <= :end
            """),
            range_params,
        )
        _active_ids_in_range = {r.user_id for r in active_result}
        active_in_range: int = len(_active_ids_in_range & set(all_user_ids))

        total_motions_result = await chat_db.execute(
            text("""
                SELECT COUNT(m.id) AS total
                FROM motion_draft_logs m
                INNER JOIN sessions s ON s.id = m.session_id
                WHERE s.user_id = ANY(:ids)
                  AND m.created_at >= :start AND m.created_at <= :end
            """),
            {"ids": all_user_ids, **range_params},
        )
        total_motions_in_range: int = total_motions_result.scalar() or 0
        avg_motions_per_user = (
            round(total_motions_in_range / active_in_range, 2) if active_in_range > 0 else 0.0
        )

        # Lightweight sort-key aggregate — one query for the chosen sort field
        if sort_by == "last_active":
            sk_result = await chat_db.execute(
                text("""
                    SELECT user_id, MAX(created_at) AS sort_val
                    FROM user_activity_logs WHERE user_id = ANY(:ids)
                    GROUP BY user_id
                """),
                {"ids": all_user_ids},
            )
            sort_key_map: dict = {r.user_id: r.sort_val for r in sk_result}
            default_sort: object = _dt_min
        elif sort_by == "cases_count":
            sk_result = await chat_db.execute(
                text("""
                    WITH lp AS (
                        SELECT DISTINCT ON (session_id) session_id, petition_status
                        FROM pdf_documents ORDER BY session_id, uploaded_at DESC
                    )
                    SELECT s.user_id, COUNT(DISTINCT s.id) AS sort_val
                    FROM sessions s
                    INNER JOIN lp ON lp.session_id = s.id
                    INNER JOIN chat_threads ct ON ct.session_id = s.id AND ct.is_active = true
                    WHERE s.user_id = ANY(:ids) AND s.is_active = true
                      AND s.created_at >= :start AND s.created_at <= :end
                      AND (lp.petition_status IN ('working', 'accepted') OR lp.petition_status IS NULL)
                    GROUP BY s.user_id
                """),
                {"ids": all_user_ids, **range_params},
            )
            sort_key_map = {r.user_id: int(r.sort_val) for r in sk_result}
            default_sort = 0
        elif sort_by == "motions_drafted":
            sk_result = await chat_db.execute(
                text("""
                    SELECT s.user_id, COUNT(m.id) AS sort_val
                    FROM motion_draft_logs m
                    INNER JOIN sessions s ON s.id = m.session_id
                    WHERE s.user_id = ANY(:ids)
                      AND m.created_at >= :start AND m.created_at <= :end
                    GROUP BY s.user_id
                """),
                {"ids": all_user_ids, **range_params},
            )
            sort_key_map = {r.user_id: int(r.sort_val) for r in sk_result}
            default_sort = 0
        else:  # created_at — sort key is already in user_db result
            sort_key_map = created_at_map
            default_sort = _dt_min

    # ── Step 3: sort all IDs by key, paginate to get page IDs ────────────
    reverse = sort_dir == "desc"
    sorted_ids = sorted(
        all_user_ids,
        key=lambda uid: sort_key_map.get(uid) or default_sort,
        reverse=reverse,
    )
    offset = (page - 1) * page_size
    page_ids = sorted_ids[offset: offset + page_size]

    if not page_ids:
        return UsersAnalyticsResponse(
            kpis=UsersAnalyticsKpis(
                total_users=total_users,
                new_in_range=new_in_range,
                active_in_range=active_in_range,
                avg_motions_per_user=avg_motions_per_user,
            ),
            pagination=UsersPagination(page=page, page_size=page_size, total=total_filtered),
            users=[],
            date_range=DateRangeInfo(preset=dr.range, start=dr.start, end=dr.end),
        )

    # ── Step 4: user_db — full identity for page only ────────────────────
    async with UserAsyncSessionLocal() as user_db:
        page_user_rows = await user_db.execute(
            text("""
                SELECT id, email, first_name, last_name, created_at
                FROM users WHERE id = ANY(:ids)
            """),
            {"ids": page_ids},
        )
        page_users_map = {r.id: r for r in page_user_rows.fetchall()}

    # ── Step 5: chat_db — detailed behavioral data for page only ─────────
    async with AsyncSessionLocal() as chat_db:
        last_active_result = await chat_db.execute(
            text("""
                SELECT user_id, MAX(created_at) AS last_active_at
                FROM user_activity_logs WHERE user_id = ANY(:ids)
                GROUP BY user_id
            """),
            {"ids": page_ids},
        )
        last_active_map: dict[str, datetime] = {
            r.user_id: r.last_active_at for r in last_active_result
        }

        cases_result = await chat_db.execute(
            text("""
                WITH lp AS (
                    SELECT DISTINCT ON (session_id) session_id, petition_status
                    FROM pdf_documents ORDER BY session_id, uploaded_at DESC
                )
                SELECT s.user_id, COUNT(DISTINCT s.id) AS cases_count
                FROM sessions s
                INNER JOIN lp ON lp.session_id = s.id
                INNER JOIN chat_threads ct ON ct.session_id = s.id AND ct.is_active = true
                WHERE s.user_id = ANY(:ids) AND s.is_active = true
                  AND s.created_at >= :start AND s.created_at <= :end
                  AND (lp.petition_status IN ('working', 'accepted') OR lp.petition_status IS NULL)
                GROUP BY s.user_id
            """),
            {"ids": page_ids, **range_params},
        )
        cases_map: dict[str, int] = {r.user_id: r.cases_count for r in cases_result}

        motions_result = await chat_db.execute(
            text("""
                SELECT
                    s.user_id,
                    COUNT(m.id) AS motions_drafted,
                    AVG(
                        CASE WHEN m.status = 'completed' AND m.completed_at IS NOT NULL
                        THEN EXTRACT(EPOCH FROM (m.completed_at - m.created_at)) END
                    ) AS avg_draft_time_seconds
                FROM motion_draft_logs m
                INNER JOIN sessions s ON s.id = m.session_id
                WHERE s.user_id = ANY(:ids)
                  AND m.created_at >= :start AND m.created_at <= :end
                GROUP BY s.user_id
            """),
            {"ids": page_ids, **range_params},
        )
        motions_map: dict[str, dict] = {}
        for r in motions_result:
            motions_map[r.user_id] = {
                "drafted": int(r.motions_drafted),
                "avg_seconds": float(r.avg_draft_time_seconds) if r.avg_draft_time_seconds is not None else None,
            }

        top_motions_result = await chat_db.execute(
            text("""
                WITH ranked AS (
                    SELECT
                        s.user_id,
                        m.motion_type,
                        COUNT(*) AS cnt,
                        ROW_NUMBER() OVER (
                            PARTITION BY s.user_id ORDER BY COUNT(*) DESC
                        ) AS rn
                    FROM motion_draft_logs m
                    INNER JOIN sessions s ON s.id = m.session_id
                    WHERE s.user_id = ANY(:ids) AND m.status = 'completed'
                    GROUP BY s.user_id, m.motion_type
                )
                SELECT user_id, motion_type FROM ranked WHERE rn <= 3
                ORDER BY user_id, cnt DESC
            """),
            {"ids": page_ids},
        )
        top_motions_map: dict[str, list[str]] = {}
        for r in top_motions_result:
            top_motions_map.setdefault(r.user_id, []).append(r.motion_type)

        recent_actions_result = await chat_db.execute(
            text("""
                WITH ranked AS (
                    SELECT
                        user_id, session_id, action, activity_metadata, created_at,
                        ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY created_at DESC) AS rn
                    FROM user_activity_logs WHERE user_id = ANY(:ids)
                )
                SELECT user_id, session_id, action, activity_metadata, created_at
                FROM ranked WHERE rn <= 5
                ORDER BY user_id, created_at DESC
            """),
            {"ids": page_ids},
        )
        recent_actions_map: dict[str, list[RecentAction]] = {}
        for row in recent_actions_result:
            meta = row.activity_metadata or {}
            filtered_meta = {k: meta[k] for k in _METADATA_KEYS if meta.get(k) is not None} or None
            recent_actions_map.setdefault(row.user_id, []).append(
                RecentAction(
                    action=row.action,
                    label=_ACTION_LABELS.get(row.action, row.action),
                    detail=_build_activity_detail(row.action, meta),
                    entity_id=row.session_id,
                    timestamp=row.created_at,
                    metadata=filtered_meta,
                )
            )

    # ── Step 6: assemble response in sorted page order ────────────────────
    users: list[UserAnalyticsItem] = []
    for uid in page_ids:
        u = page_users_map.get(uid)
        if not u:
            continue
        name = " ".join(filter(None, [u.first_name, u.last_name])) or u.email
        motion_data = motions_map.get(uid, {})
        users.append(
            UserAnalyticsItem(
                user_id=uid,
                name=name,
                email=u.email,
                created_at=u.created_at,
                last_active_at=last_active_map.get(uid),
                cases_count=cases_map.get(uid, 0),
                motions_drafted=motion_data.get("drafted", 0),
                avg_draft_time_seconds=motion_data.get("avg_seconds"),
                top_motion_types=top_motions_map.get(uid, []),
                recent_actions=recent_actions_map.get(uid, []),
            )
        )

    return UsersAnalyticsResponse(
        kpis=UsersAnalyticsKpis(
            total_users=total_users,
            new_in_range=new_in_range,
            active_in_range=active_in_range,
            avg_motions_per_user=avg_motions_per_user,
        ),
        pagination=UsersPagination(page=page, page_size=page_size, total=total_filtered),
        users=users,
        date_range=DateRangeInfo(preset=dr.range, start=dr.start, end=dr.end),
    )
