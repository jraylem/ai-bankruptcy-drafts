"""
Dashboard KPI routes — migrated from src/routes/dashboard.py.

All URL paths are preserved:
  GET /cases
  GET /users
  GET /motions
  GET /charts/motions-daily
  GET /charts/cases-daily
  GET /charts/motions-by-type
  GET /charts/users-daily
  GET /system/status
  GET /kpis/api-calls
  GET /activity/feed
"""

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import text

from ...config import settings
from ...auth.models import User
from ...common.dependencies import get_current_firm_user
from ...auth.database import UserAsyncSessionLocal
from ...chatbot.database import AsyncSessionLocal
from ...gmail.drive_service import list_archived_petition_filenames
from ...tasks.task_state import task_state, ACTIVE_STATUSES as PLEADING_ACTIVE_STATUSES
from ...tasks.review_task_state import review_task_state, ACTIVE_STATUSES as REVIEW_ACTIVE_STATUSES
from ._shared import (
    DateRangeParams,
    DateRangeInfo,
    _BASE_CTE,
    _GLOBAL_CTE,
    _MOTION_DISPLAY_NAMES,
    _ACTION_LABELS,
    _SYSTEM_ACTIONS,
    _build_activity_detail,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dashboard"])


# ---------------------------------------------------------------------------
# Internal fetch functions — called by _chat_snapshot.py
# ---------------------------------------------------------------------------

async def _fetch_cases_kpi_global() -> dict:
    """
    Called by: _fetch_dashboard_snapshot (_chat_snapshot.py)
    Global bucket counts using _GLOBAL_CTE (all-time, no date filter) —
    matches the dashboard /cases KPI card which shows TOTAL CASES / ACTIVE CASES
    across all time, not just the 30-day window.
    """
    async with AsyncSessionLocal() as db:
        bucket_rows = await db.execute(
            text(f"""
                {_GLOBAL_CTE}
                SELECT bucket, petition_status, COUNT(*) AS cnt
                FROM session_bucket
                GROUP BY bucket, petition_status
            """),
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

        entry_rows = await db.execute(
            text(f"""
                {_GLOBAL_CTE},
                active_sessions AS (
                    SELECT session_id FROM session_bucket WHERE bucket = 'active'
                ),
                latest_source AS (
                    SELECT DISTINCT ON (p.session_id) p.session_id, p.source
                    FROM pdf_documents p
                    INNER JOIN active_sessions a ON a.session_id = p.session_id
                    ORDER BY p.session_id, p.uploaded_at DESC
                ),
                session_entry AS (
                    SELECT session_id,
                        CASE
                            WHEN source IN ('gdrive', 'courtdrive') THEN 'summoned'
                            WHEN source = 'ecf'                     THEN 'from_pending'
                            ELSE 'manual'
                        END AS entry_type
                    FROM latest_source
                )
                SELECT entry_type, COUNT(*) AS cnt FROM session_entry GROUP BY entry_type
            """),
        )
        entry_counts = {row.entry_type: int(row.cnt) for row in entry_rows}

        district_rows = await db.execute(
            text(f"""
                {_GLOBAL_CTE},
                active_sessions AS (
                    SELECT session_id FROM session_bucket WHERE bucket = 'active'
                ),
                latest_district AS (
                    SELECT DISTINCT ON (ct.session_id) ct.session_id, ct.district
                    FROM chat_threads ct
                    INNER JOIN active_sessions a ON a.session_id = ct.session_id
                    WHERE ct.district IS NOT NULL
                    ORDER BY ct.session_id, ct.created_at DESC
                )
                SELECT COALESCE(ld.district, 'other') AS district, COUNT(*) AS cnt
                FROM active_sessions a
                LEFT JOIN latest_district ld ON ld.session_id = a.session_id
                GROUP BY COALESCE(ld.district, 'other')
            """),
        )
        district_counts = {row.district: int(row.cnt) for row in district_rows}

    return {
        "active": {
            "sum": active_sum,
            "manual": entry_counts.get("manual", 0),
            "summoned": entry_counts.get("summoned", 0),
            "from_pending": entry_counts.get("from_pending", 0),
        },
        "inactive": {"sum": denied + deleted, "denied": denied, "deleted": deleted},
        "district": {
            "flnb": district_counts.get("flnb", 0),
            "flmb": district_counts.get("flmb", 0),
            "flsb": district_counts.get("flsb", 0),
            "pawb": district_counts.get("pawb", 0),
            "other": district_counts.get("other", 0),
        },
    }


async def _fetch_motions_kpi(start: datetime, end: datetime) -> dict:
    """
    Called by: _fetch_dashboard_snapshot (_chat_snapshot.py)
    """
    params = {"start": start, "end": end}
    async with AsyncSessionLocal() as db:
        status_rows = await db.execute(
            text("""
                SELECT status, COUNT(*) AS cnt
                FROM motion_draft_logs
                WHERE created_at >= :start AND created_at <= :end
                GROUP BY status
            """),
            params,
        )
        status_counts: dict[str, int] = {row.status: int(row.cnt) for row in status_rows}
        total = sum(status_counts.values())

        type_rows = await db.execute(
            text("""
                SELECT motion_type, COUNT(*) AS cnt
                FROM motion_draft_logs
                WHERE created_at >= :start AND created_at <= :end
                GROUP BY motion_type
                ORDER BY cnt DESC
            """),
            params,
        )
        by_type = [
            {
                "motion_type": row.motion_type,
                "display_name": _MOTION_DISPLAY_NAMES.get(row.motion_type, row.motion_type),
                "count": int(row.cnt),
            }
            for row in type_rows
        ]

    return {
        "total": total,
        "by_status": {
            "pending": status_counts.get("pending", 0),
            "completed": status_counts.get("completed", 0),
            "failed": status_counts.get("failed", 0),
            "cancelled": status_counts.get("cancelled", 0),
        },
        "by_type": by_type,
    }


async def _fetch_users_kpi(start: datetime, end: datetime) -> dict:
    """
    Called by: _fetch_dashboard_snapshot (_chat_snapshot.py)
    """
    params = {"start": start, "end": end}
    async with UserAsyncSessionLocal() as user_db:
        total_result = await user_db.execute(
            text("SELECT COUNT(*) FROM users WHERE is_active = true")
        )
        total: int = total_result.scalar() or 0

        new_result = await user_db.execute(
            text("""
                SELECT COUNT(*) FROM users
                WHERE is_active = true AND created_at >= :start AND created_at <= :end
            """),
            params,
        )
        new_in_range: int = new_result.scalar() or 0

        all_active_result = await user_db.execute(
            text("SELECT id FROM users WHERE is_active = true")
        )
        _active_user_ids: set[str] = {r.id for r in all_active_result}

    async with AsyncSessionLocal() as chat_db:
        active_result = await chat_db.execute(
            text("""
                SELECT DISTINCT user_id FROM user_activity_logs
                WHERE user_id IS NOT NULL AND created_at >= :start AND created_at <= :end
            """),
            params,
        )
        _activity_ids = {r.user_id for r in active_result}
        active_in_range: int = len(_activity_ids & _active_user_ids)

    return {"total": total, "new_in_range": new_in_range, "active_in_range": active_in_range}


async def _fetch_cases_daily(start: datetime, end: datetime) -> list[dict]:
    """
    Called by: _fetch_dashboard_snapshot (_chat_snapshot.py)
    """
    params = {"start": start, "end": end}
    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            text(f"""
                {_BASE_CTE},
                daily_buckets AS (
                    SELECT DATE(s.created_at AT TIME ZONE 'UTC') AS day, sb.bucket
                    FROM session_bucket sb
                    INNER JOIN sessions s ON s.id = sb.session_id
                )
                SELECT day, bucket, COUNT(*) AS cnt
                FROM daily_buckets
                GROUP BY day, bucket
                ORDER BY day
            """),
            params,
        )
        daily: dict[str, dict[str, int]] = {}
        for row in rows:
            day_str = row.day.isoformat()
            if day_str not in daily:
                daily[day_str] = {}
            daily[day_str][row.bucket] = int(row.cnt)

    return [
        {
            "date": day_str,
            "total":   counts.get("active", 0) + counts.get("pending", 0) + counts.get("inactive", 0),
            "active":  counts.get("active", 0),
            "pending": counts.get("pending", 0),
            "inactive": counts.get("inactive", 0),
        }
        for day_str, counts in sorted(daily.items())
    ]


async def _fetch_motions_daily(start: datetime, end: datetime) -> list[dict]:
    """
    Called by: _fetch_dashboard_snapshot (_chat_snapshot.py)
    """
    params = {"start": start, "end": end}
    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            text("""
                SELECT DATE(created_at AT TIME ZONE 'UTC') AS day, status, COUNT(*) AS cnt
                FROM motion_draft_logs
                WHERE created_at >= :start AND created_at <= :end
                GROUP BY day, status
                ORDER BY day
            """),
            params,
        )
        daily: dict[str, dict[str, int]] = {}
        for row in rows:
            day_str = row.day.isoformat()
            if day_str not in daily:
                daily[day_str] = {}
            daily[day_str][row.status] = int(row.cnt)

    return [
        {
            "date": day_str,
            "total": sum(counts.values()),
            "completed": counts.get("completed", 0),
            "pending": counts.get("pending", 0),
            "failed": counts.get("failed", 0),
            "cancelled": counts.get("cancelled", 0),
        }
        for day_str, counts in sorted(daily.items())
    ]


async def _fetch_motions_by_type(start: datetime, end: datetime) -> list[dict]:
    """
    Called by: _fetch_dashboard_snapshot (_chat_snapshot.py)
    Per-type aggregate (NOT daily). Sorted descending by total.
    """
    params = {"start": start, "end": end}
    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            text("""
                SELECT motion_type, status, COUNT(*) AS cnt
                FROM motion_draft_logs
                WHERE created_at >= :start AND created_at <= :end
                GROUP BY motion_type, status
                ORDER BY motion_type
            """),
            params,
        )
        by_type: dict[str, dict[str, int]] = {}
        for row in rows:
            if row.motion_type not in by_type:
                by_type[row.motion_type] = {}
            by_type[row.motion_type][row.status] = int(row.cnt)

    return sorted(
        [
            {
                "motion_type": mt,
                "display_name": _MOTION_DISPLAY_NAMES.get(mt, mt),
                "total": sum(counts.values()),
                "completed": counts.get("completed", 0),
                "pending": counts.get("pending", 0),
                "failed": counts.get("failed", 0),
                "cancelled": counts.get("cancelled", 0),
            }
            for mt, counts in by_type.items()
        ],
        key=lambda p: p["total"],
        reverse=True,
    )


async def _fetch_users_daily(start: datetime, end: datetime) -> list[dict]:
    """
    Called by: _fetch_dashboard_snapshot (_chat_snapshot.py)
    Zero-filled daily series: active_users, motions_drafted, new_users.
    """
    params = {"start": start, "end": end}

    spine: list[str] = []
    cur: date = start.date()
    end_date: date = end.date()
    while cur <= end_date:
        spine.append(cur.isoformat())
        cur += timedelta(days=1)

    async def _query_user_db() -> dict[str, int]:
        async with UserAsyncSessionLocal() as db:
            rows = await db.execute(
                text("""
                    SELECT DATE(created_at AT TIME ZONE 'UTC') AS day, COUNT(*) AS cnt
                    FROM users
                    WHERE is_active = true AND created_at >= :start AND created_at <= :end
                    GROUP BY day
                """),
                params,
            )
            return {row.day.isoformat(): int(row.cnt) for row in rows}

    async def _query_chat_db() -> tuple[dict[str, int], dict[str, int]]:
        async with AsyncSessionLocal() as db:
            active_rows = await db.execute(
                text("""
                    SELECT DATE(created_at AT TIME ZONE 'UTC') AS day, COUNT(DISTINCT user_id) AS cnt
                    FROM user_activity_logs
                    WHERE user_id IS NOT NULL AND created_at >= :start AND created_at <= :end
                    GROUP BY day
                """),
                params,
            )
            active_map: dict[str, int] = {row.day.isoformat(): int(row.cnt) for row in active_rows}

            motions_rows = await db.execute(
                text("""
                    SELECT DATE(created_at AT TIME ZONE 'UTC') AS day, COUNT(*) AS cnt
                    FROM motion_draft_logs
                    WHERE created_at >= :start AND created_at <= :end
                    GROUP BY day
                """),
                params,
            )
            motions_map: dict[str, int] = {row.day.isoformat(): int(row.cnt) for row in motions_rows}
        return active_map, motions_map

    new_users_map, (active_map, motions_map) = await asyncio.gather(
        _query_user_db(),
        _query_chat_db(),
    )

    return [
        {
            "date": day,
            "active_users": active_map.get(day, 0),
            "motions_drafted": motions_map.get(day, 0),
            "new_users": new_users_map.get(day, 0),
        }
        for day in spine
    ]


# ---------------------------------------------------------------------------
# Response schemas — /cases
# ---------------------------------------------------------------------------

class ActiveCases(BaseModel):
    sum: int
    manual: int
    summoned: int
    from_pending: int


class InactiveCases(BaseModel):
    sum: int
    denied: int
    archived: int
    deleted: int


class DistrictBreakdown(BaseModel):
    sum: int
    flnb: int
    flmb: int
    flsb: int
    pawb: int
    other: int


class CasesDelta(BaseModel):
    new_in_range: int
    closed_in_range: int
    net_change: int


class CasesKpiResponse(BaseModel):
    total: int
    active_cases: ActiveCases
    pending_cases: int
    inactive_cases: InactiveCases
    by_district_active: DistrictBreakdown
    delta: CasesDelta
    date_range: DateRangeInfo



def _zero_response(dr: DateRangeParams) -> CasesKpiResponse:
    return CasesKpiResponse(
        total=0,
        active_cases=ActiveCases(sum=0, manual=0, summoned=0, from_pending=0),
        pending_cases=0,
        inactive_cases=InactiveCases(sum=0, denied=0, archived=0, deleted=0),
        by_district_active=DistrictBreakdown(sum=0, flnb=0, flmb=0, flsb=0, pawb=0, other=0),
        delta=CasesDelta(new_in_range=0, closed_in_range=0, net_change=0),
        date_range=DateRangeInfo(preset=dr.range, start=dr.start, end=dr.end),
    )


# ---------------------------------------------------------------------------
# Shared helper — global cases snapshot (no date filter)
# Used by both GET /cases and GET /charts/cases-daily so their totals match.
# ---------------------------------------------------------------------------

async def _fetch_global_cases_snapshot(db, user_id: str) -> dict:
    """
    Returns the same total that the /cases KPI card displays:
      active_sum + pending_cases(user-scoped) + denied + archived(DB+GDrive) + deleted
    """
    bucket_rows = await db.execute(
        text(f"""
            {_GLOBAL_CTE}
            SELECT bucket, petition_status, COUNT(*) AS cnt
            FROM session_bucket
            GROUP BY bucket, petition_status
        """),
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

    pending_result = await db.execute(
        text("""
            WITH user_latest_pdf AS (
                SELECT DISTINCT ON (p.session_id)
                    p.session_id,
                    p.petition_status,
                    p.inbox_checked_at,
                    (p.filename ~ '^Bankruptcy_Petition_') AS is_inbox_file
                FROM pdf_documents p
                INNER JOIN sessions s ON s.id = p.session_id
                WHERE s.user_id = :user_id
                  AND s.is_active = true
                ORDER BY p.session_id, p.uploaded_at DESC
            )
            SELECT COUNT(*) AS cnt
            FROM user_latest_pdf ulp
            INNER JOIN courtdrive_ingestions ci
                ON ci.session_id = ulp.session_id
               AND ci.ingestion_type = 'pending_acceptance'
               AND ci.status = 'pending_acceptance'
            WHERE ulp.petition_status = 'pending_acceptance'
              AND ulp.inbox_checked_at IS NULL
              AND ulp.is_inbox_file = true
        """),
        {"user_id": user_id},
    )
    pending_cases: int = pending_result.scalar() or 0

    archived_db_rows = await db.execute(
        text(f"""
            {_GLOBAL_CTE},
            archived_sessions AS (
                SELECT session_id FROM session_bucket
                WHERE bucket = 'inactive' AND petition_status = 'archived'
            )
            SELECT DISTINCT ON (p.session_id) p.filename
            FROM pdf_documents p
            INNER JOIN archived_sessions a ON a.session_id = p.session_id
            ORDER BY p.session_id, p.uploaded_at DESC
        """),
    )
    db_archived_filenames = {
        Path(row.filename).stem.lower() for row in archived_db_rows if row.filename
    }
    drive_filenames_raw: list[str] = await asyncio.get_event_loop().run_in_executor(
        None, list_archived_petition_filenames
    )
    drive_archived_filenames = {
        Path(name).stem.lower() for name in drive_filenames_raw if name
    }
    archived = len(db_archived_filenames | drive_archived_filenames)

    return {
        "total": active_sum + pending_cases + denied + archived + deleted,
        "active_sum": active_sum,
        "pending_cases": pending_cases,
        "denied": denied,
        "archived": archived,
        "deleted": deleted,
    }


# ---------------------------------------------------------------------------
# GET /cases
# ---------------------------------------------------------------------------

@router.get("/cases", response_model=CasesKpiResponse)
async def get_cases_kpi(
    dr: DateRangeParams = Depends(),
    user: User = Depends(get_current_firm_user),
):
    """
    Returns global case counts (date-range independent) plus a delta showing
    how many cases were opened/closed within the selected date range.

    Global fields (total, active_cases, pending_cases, inactive_cases,
    by_district_active) always reflect the current state of all cases — they
    do not change when the user switches between today / 7d / 30d.

    delta.new_in_range    — sessions created within the date range
    delta.closed_in_range — cases explicitly denied or archived in the range
                            (sourced from user_activity_logs; auto-archived
                            cases are not included)
    delta.net_change      — new_in_range minus closed_in_range
    """
    async with AsyncSessionLocal() as db:

        # ------------------------------------------------------------------
        # Global snapshot — via shared helper (same logic as cases-daily)
        # ------------------------------------------------------------------

        # Sync stale pending sessions with disk state before counting so the
        # dashboard matches the inbox list (which checks file existence in Python).
        try:
            from ...gmail.workflow_services import CaseAcceptanceService
            asyncio.create_task(CaseAcceptanceService().auto_archive_stale_pending_cases())
        except Exception:
            pass

        snapshot = await _fetch_global_cases_snapshot(db, user.id)
        total        = snapshot["total"]
        active_sum   = snapshot["active_sum"]
        pending_cases= snapshot["pending_cases"]
        denied       = snapshot["denied"]
        archived     = snapshot["archived"]
        deleted      = snapshot["deleted"]

        # Entry type breakdown — global active sessions
        entry_rows = await db.execute(
            text(f"""
                {_GLOBAL_CTE},
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
        )
        entry_counts: dict[str, int] = {row.entry_type: row.cnt for row in entry_rows}

        # District breakdown — global active sessions
        district_rows = await db.execute(
            text(f"""
                {_GLOBAL_CTE},
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
        )
        district_counts: dict[str, int] = {row.district: row.cnt for row in district_rows}

        # ------------------------------------------------------------------
        # Delta — date-scoped
        # ------------------------------------------------------------------
        delta_params = {"start": dr.start, "end": dr.end}

        # new_in_range: summoned + manually uploaded (sessions created in range,
        # non-inbox source) + accepted from pending Inbox (accept_case actions in range).
        summoned_manual_result = await db.execute(
            text("""
                WITH sessions_in_range AS (
                    SELECT DISTINCT ON (p.session_id) p.session_id
                    FROM pdf_documents p
                    INNER JOIN sessions s ON s.id = p.session_id
                    WHERE s.created_at >= :start
                      AND s.created_at <= :end
                      AND (p.filename ~ '^Bankruptcy_Petition_' OR p.petition_status IS NOT NULL)
                      AND p.source != 'ecf'
                    ORDER BY p.session_id, p.uploaded_at DESC
                )
                SELECT COUNT(*) AS cnt FROM sessions_in_range
            """),
            delta_params,
        )
        summoned_manual: int = summoned_manual_result.scalar() or 0

        accepted_result = await db.execute(
            text("""
                SELECT COUNT(DISTINCT session_id) AS cnt
                FROM user_activity_logs
                WHERE action = 'accept_case'
                  AND created_at >= :start
                  AND created_at <= :end
                  AND session_id IS NOT NULL
            """),
            delta_params,
        )
        accepted_from_inbox: int = accepted_result.scalar() or 0

        new_in_range: int = summoned_manual + accepted_from_inbox

        # closed_in_range: user-deleted cases.
        # Two sources combined to handle both pre-logging deletions and future ones:
        #   1. delete_case log entries in range (accurate timestamp, works even if session
        #      was created outside the range)
        #   2. sessions created in range whose petition_status is currently 'deleted'
        #      (backward-compat fallback for cases deleted before logging was added)
        closed_result = await db.execute(
            text(f"""
                {_BASE_CTE},
                petition_sessions AS (
                    SELECT DISTINCT session_id
                    FROM pdf_documents
                    WHERE filename ~ '^Bankruptcy_Petition_'
                       OR petition_status IS NOT NULL
                ),
                deleted_by_log AS (
                    SELECT session_id
                    FROM user_activity_logs
                    WHERE action = 'delete_case'
                      AND created_at >= :start
                      AND created_at <= :end
                      AND session_id IS NOT NULL
                ),
                deleted_by_status AS (
                    SELECT sb.session_id
                    FROM session_bucket sb
                    INNER JOIN sessions s ON s.id = sb.session_id
                    INNER JOIN petition_sessions ps ON ps.session_id = sb.session_id
                    WHERE sb.petition_status = 'deleted'
                      AND s.created_at >= :start
                      AND s.created_at <= :end
                )
                SELECT COUNT(DISTINCT session_id) AS cnt
                FROM (
                    SELECT session_id FROM deleted_by_log
                    UNION
                    SELECT session_id FROM deleted_by_status
                ) combined
            """),
            delta_params,
        )
        closed_in_range: int = closed_result.scalar() or 0

    return CasesKpiResponse(
        total=total,
        active_cases=ActiveCases(
            sum=active_sum,
            manual=entry_counts.get("manual", 0),
            summoned=entry_counts.get("summoned", 0),
            from_pending=entry_counts.get("from_pending", 0),
        ),
        pending_cases=pending_cases,
        inactive_cases=InactiveCases(
            sum=denied + archived + deleted,
            denied=denied,
            archived=archived,
            deleted=deleted,
        ),
        by_district_active=DistrictBreakdown(
            sum=sum(district_counts.get(d, 0) for d in ("flnb", "flmb", "flsb", "pawb", "other")),
            flnb=district_counts.get("flnb", 0),
            flmb=district_counts.get("flmb", 0),
            flsb=district_counts.get("flsb", 0),
            pawb=district_counts.get("pawb", 0),
            other=district_counts.get("other", 0),
        ),
        delta=CasesDelta(
            new_in_range=new_in_range,
            closed_in_range=closed_in_range,
            net_change=new_in_range - closed_in_range,
        ),
        date_range=DateRangeInfo(preset=dr.range, start=dr.start, end=dr.end),
    )


# ---------------------------------------------------------------------------
# GET /users
# ---------------------------------------------------------------------------

class UsersKpiResponse(BaseModel):
    total: int
    new_in_range: int
    active_in_range: int
    date_range: DateRangeInfo


@router.get("/users", response_model=UsersKpiResponse)
async def get_users_kpi(
    dr: DateRangeParams = Depends(),
    _user: User = Depends(get_current_firm_user),
):
    """
    Returns user counts: total registered, newly registered, and active within
    the date range.

    'active_in_range' is derived from user_activity_logs (distinct user_ids
    who performed at least one explicit action within the window).
    """
    params = {"start": dr.start, "end": dr.end}

    async with UserAsyncSessionLocal() as user_db:
        total_result = await user_db.execute(
            text("SELECT COUNT(*) FROM users WHERE is_active = true")
        )
        total: int = total_result.scalar() or 0

        new_result = await user_db.execute(
            text("""
                SELECT COUNT(*) FROM users
                WHERE is_active = true
                  AND created_at >= :start
                  AND created_at <= :end
            """),
            params,
        )
        new_in_range: int = new_result.scalar() or 0

        # Fetch active user IDs so we can bound active_in_range to real users only.
        all_active_ids_result = await user_db.execute(
            text("SELECT id FROM users WHERE is_active = true")
        )
        _active_user_ids: set[str] = {r.id for r in all_active_ids_result}

    async with AsyncSessionLocal() as chat_db:
        # Fetch distinct user_ids with activity in range, then intersect with
        # active users from user_db. Prevents deactivated/deleted user activity
        # from inflating active_in_range above total.
        active_result = await chat_db.execute(
            text("""
                SELECT DISTINCT user_id
                FROM user_activity_logs
                WHERE user_id IS NOT NULL
                  AND created_at >= :start
                  AND created_at <= :end
            """),
            params,
        )
        _activity_user_ids = {r.user_id for r in active_result}
        active_in_range: int = len(_activity_user_ids & _active_user_ids)

    return UsersKpiResponse(
        total=total,
        new_in_range=new_in_range,
        active_in_range=active_in_range,
        date_range=DateRangeInfo(preset=dr.range, start=dr.start, end=dr.end),
    )


# ---------------------------------------------------------------------------
# GET /motions
# ---------------------------------------------------------------------------

class MotionTypeCount(BaseModel):
    motion_type: str
    display_name: str
    count: int


class MotionsByStatus(BaseModel):
    pending: int
    completed: int
    failed: int
    cancelled: int


class MotionsKpiResponse(BaseModel):
    total: int
    by_status: MotionsByStatus
    by_type: list[MotionTypeCount]
    date_range: DateRangeInfo


@router.get("/motions", response_model=MotionsKpiResponse)
async def get_motions_kpi(
    dr: DateRangeParams = Depends(),
    _user: User = Depends(get_current_firm_user),
):
    """
    Returns motion/order draft counts by status and type within the date range.
    Source: motion_draft_logs.
    """
    params = {"start": dr.start, "end": dr.end}

    async with AsyncSessionLocal() as db:
        status_rows = await db.execute(
            text("""
                SELECT status, COUNT(*) AS cnt
                FROM motion_draft_logs
                WHERE created_at >= :start
                  AND created_at <= :end
                GROUP BY status
            """),
            params,
        )
        status_counts: dict[str, int] = {row.status: row.cnt for row in status_rows}

        total = sum(status_counts.values())
        by_status = MotionsByStatus(
            pending=status_counts.get("pending", 0),
            completed=status_counts.get("completed", 0),
            failed=status_counts.get("failed", 0),
            cancelled=status_counts.get("cancelled", 0),
        )

        type_rows = await db.execute(
            text("""
                SELECT motion_type, COUNT(*) AS cnt
                FROM motion_draft_logs
                WHERE created_at >= :start
                  AND created_at <= :end
                GROUP BY motion_type
                ORDER BY cnt DESC
            """),
            params,
        )
        by_type = [
            MotionTypeCount(
                motion_type=row.motion_type,
                display_name=_MOTION_DISPLAY_NAMES.get(row.motion_type, row.motion_type),
                count=row.cnt,
            )
            for row in type_rows
        ]

    return MotionsKpiResponse(
        total=total,
        by_status=by_status,
        by_type=by_type,
        date_range=DateRangeInfo(preset=dr.range, start=dr.start, end=dr.end),
    )


# ---------------------------------------------------------------------------
# GET /charts/motions-daily
# ---------------------------------------------------------------------------

class DailyMotionPoint(BaseModel):
    date: str
    total: int
    completed: int
    pending: int
    failed: int
    cancelled: int


class MotionsDailyResponse(BaseModel):
    data: list[DailyMotionPoint]
    date_range: DateRangeInfo


@router.get("/charts/motions-daily", response_model=MotionsDailyResponse)
async def get_motions_daily(
    dr: DateRangeParams = Depends(),
    _user: User = Depends(get_current_firm_user),
):
    """
    Returns per-day motion/order draft counts for trend charting.
    Only days with activity are returned (no zero-fill).
    """
    params = {"start": dr.start, "end": dr.end}

    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            text("""
                SELECT
                    DATE(created_at AT TIME ZONE 'UTC') AS day,
                    status,
                    COUNT(*) AS cnt
                FROM motion_draft_logs
                WHERE created_at >= :start
                  AND created_at <= :end
                GROUP BY day, status
                ORDER BY day
            """),
            params,
        )

        daily: dict[str, dict[str, int]] = {}
        for row in rows:
            day_str = row.day.isoformat()
            if day_str not in daily:
                daily[day_str] = {}
            daily[day_str][row.status] = row.cnt

        data = [
            DailyMotionPoint(
                date=day_str,
                total=sum(counts.values()),
                completed=counts.get("completed", 0),
                pending=counts.get("pending", 0),
                failed=counts.get("failed", 0),
                cancelled=counts.get("cancelled", 0),
            )
            for day_str, counts in sorted(daily.items())
        ]

    return MotionsDailyResponse(
        data=data,
        date_range=DateRangeInfo(preset=dr.range, start=dr.start, end=dr.end),
    )


# ---------------------------------------------------------------------------
# GET /charts/cases-daily
# ---------------------------------------------------------------------------

class DailyCasePoint(BaseModel):
    date: str
    total: int
    active: int
    pending: int
    inactive: int


class CasesDailyResponse(BaseModel):
    data: list[DailyCasePoint]
    date_range: DateRangeInfo


@router.get("/charts/cases-daily", response_model=CasesDailyResponse)
async def get_cases_daily(
    dr: DateRangeParams = Depends(),
    _user: User = Depends(get_current_firm_user),
):
    """
    Returns per-day cumulative case counts by status bucket for trend charting.
    Each day shows the running count of active/pending/inactive cases as of that day.
    Only days with activity are returned (no zero-fill).
    """
    params = {"start": dr.start, "end": dr.end}

    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            text(f"""
                {_BASE_CTE},
                daily_buckets AS (
                    SELECT
                        DATE(s.created_at AT TIME ZONE 'UTC') AS day,
                        sb.bucket
                    FROM session_bucket sb
                    INNER JOIN sessions s ON s.id = sb.session_id
                )
                SELECT day, bucket, COUNT(*) AS cnt
                FROM daily_buckets
                GROUP BY day, bucket
                ORDER BY day
            """),
            params,
        )

        daily: dict[str, dict[str, int]] = {}
        for row in rows:
            day_str = row.day.isoformat()
            if day_str not in daily:
                daily[day_str] = {}
            daily[day_str][row.bucket] = row.cnt

        data = [
            DailyCasePoint(
                date=day_str,
                total=counts.get("active", 0) + counts.get("pending", 0) + counts.get("inactive", 0),
                active=counts.get("active", 0),
                pending=counts.get("pending", 0),
                inactive=counts.get("inactive", 0),
            )
            for day_str, counts in sorted(daily.items())
        ]

    return CasesDailyResponse(
        data=data,
        date_range=DateRangeInfo(preset=dr.range, start=dr.start, end=dr.end),
    )


# ---------------------------------------------------------------------------
# GET /charts/motions-by-type
# ---------------------------------------------------------------------------

class MotionTypeChartPoint(BaseModel):
    motion_type: str
    display_name: str
    total: int
    completed: int
    pending: int
    failed: int
    cancelled: int


class MotionsByTypeResponse(BaseModel):
    data: list[MotionTypeChartPoint]
    date_range: DateRangeInfo


@router.get("/charts/motions-by-type", response_model=MotionsByTypeResponse)
async def get_motions_by_type(
    dr: DateRangeParams = Depends(),
    _user: User = Depends(get_current_firm_user),
):
    """
    Returns motion/order draft counts grouped by motion type for bar/donut charting.
    Sorted descending by total count.
    """
    params = {"start": dr.start, "end": dr.end}

    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            text("""
                SELECT motion_type, status, COUNT(*) AS cnt
                FROM motion_draft_logs
                WHERE created_at >= :start
                  AND created_at <= :end
                GROUP BY motion_type, status
                ORDER BY motion_type
            """),
            params,
        )

        by_type: dict[str, dict[str, int]] = {}
        for row in rows:
            if row.motion_type not in by_type:
                by_type[row.motion_type] = {}
            by_type[row.motion_type][row.status] = row.cnt

        data = sorted(
            [
                MotionTypeChartPoint(
                    motion_type=mt,
                    display_name=_MOTION_DISPLAY_NAMES.get(mt, mt),
                    total=sum(counts.values()),
                    completed=counts.get("completed", 0),
                    pending=counts.get("pending", 0),
                    failed=counts.get("failed", 0),
                    cancelled=counts.get("cancelled", 0),
                )
                for mt, counts in by_type.items()
            ],
            key=lambda p: p.total,
            reverse=True,
        )

    return MotionsByTypeResponse(
        data=data,
        date_range=DateRangeInfo(preset=dr.range, start=dr.start, end=dr.end),
    )


# ---------------------------------------------------------------------------
# GET /system/status
# ---------------------------------------------------------------------------

class TaskQueueStatus(BaseModel):
    active: int
    pending: int


class ErrorsStatus(BaseModel):
    count_24h: int
    delta_from_yesterday: int


class AvgResponseStatus(BaseModel):
    avg_ms: Optional[float]
    p95_ms: Optional[float]


class PollWorkerStatus(BaseModel):
    enabled: bool
    running: bool
    interval_seconds: int
    last_run_at: Optional[str]
    last_result: Optional[dict]


class SystemStatusResponse(BaseModel):
    task_queue: TaskQueueStatus
    errors: ErrorsStatus
    avg_response: AvgResponseStatus
    poll_worker: PollWorkerStatus
    checked_at: str


@router.get("/system/status", response_model=SystemStatusResponse)
async def get_system_status(
    request: Request,
    _user: User = Depends(get_current_firm_user),
):
    """
    Returns a point-in-time system health snapshot for the dashboard.
    """
    try:
        return await asyncio.wait_for(_get_system_status_inner(request), timeout=25.0)
    except asyncio.TimeoutError:
        logger.warning("system/status timed out after 25 s")
        raise HTTPException(status_code=503, detail="System status check timed out")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("system/status failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch system status")


_SYSTEM_STATUS_CACHE_KEY = "dashboard:system_status:v1"
_SYSTEM_STATUS_CACHE_TTL = 300  # 5 min — long enough to bridge bursts of slow requests
_REDIS_SCAN_COUNT = 200
_REDIS_MAX_SCAN_BATCHES = 10
_REDIS_MAX_TASK_KEYS_PER_PREFIX = 1000


async def _get_system_status_inner(request: Request) -> SystemStatusResponse:
    import json as _json
    from ...tasks.redis_client import make_sync_redis

    # /system/status uses tighter timeouts than the shared default — this
    # endpoint is a probe path and must fail fast on a Redis brownout.
    _r = make_sync_redis(socket_timeout=2, socket_connect_timeout=3)

    # Cache hot path — dashboard refreshes every 60 s, so a 30 s TTL means
    # ~half of requests hit Redis instead of the (slow on staging) Postgres queries.
    try:
        cached = _r.get(_SYSTEM_STATUS_CACHE_KEY)
        if cached:
            _r.close()
            return SystemStatusResponse.model_validate_json(cached)
    except Exception:
        pass

    def _scan_keys_limited(match: str, max_keys: int) -> list[str]:
        keys: list[str] = []
        cursor = 0
        batches = 0
        while True:
            cursor, batch = _r.scan(
                cursor=cursor,
                match=match,
                count=_REDIS_SCAN_COUNT,
            )
            batches += 1
            keys.extend(batch[: max_keys - len(keys)])
            if cursor == 0 or len(keys) >= max_keys or batches >= _REDIS_MAX_SCAN_BATCHES:
                break
        return keys

    def _count_task_statuses(keys: list[str], active_statuses: set[str]) -> dict[str, int]:
        active = pending = 0
        for start in range(0, len(keys), _REDIS_SCAN_COUNT):
            with _r.pipeline() as pipe:
                for key in keys[start:start + _REDIS_SCAN_COUNT]:
                    pipe.get(key)
                values = pipe.execute()

            for data in values:
                if not data:
                    continue
                status = _json.loads(data).get("status")
                if status == "PENDING":
                    pending += 1
                elif status in active_statuses:
                    active += 1

        return {"active": active, "pending": pending}

    def _get_task_queue_counts() -> dict[str, int]:
        try:
            pleading_counts = _count_task_statuses(
                _scan_keys_limited(
                    f"{task_state.TASK_PREFIX}*",
                    _REDIS_MAX_TASK_KEYS_PER_PREFIX,
                ),
                {s.value for s in PLEADING_ACTIVE_STATUSES} - {"PENDING"},
            )
            review_counts = _count_task_statuses(
                _scan_keys_limited(
                    f"{review_task_state.TASK_PREFIX}*",
                    _REDIS_MAX_TASK_KEYS_PER_PREFIX,
                ),
                {s.value for s in REVIEW_ACTIVE_STATUSES} - {"PENDING"},
            )
        except Exception as exc:
            logger.warning("system/status task queue Redis scan failed: %s", exc)
            return {"active": 0, "pending": 0}

        return {
            "active": pleading_counts["active"] + review_counts["active"],
            "pending": pleading_counts["pending"] + review_counts["pending"],
        }

    def _get_poll_worker_state() -> dict:
        try:
            raw = _r.get("poll_worker:court_mail:last_run")
            if raw:
                return _json.loads(raw)
        except Exception:
            pass
        return {}

    loop = asyncio.get_running_loop()
    task_counts, poll_redis = await asyncio.gather(
        loop.run_in_executor(None, _get_task_queue_counts),
        loop.run_in_executor(None, _get_poll_worker_state),
    )

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=24)
    prev_window_start = now - timedelta(hours=48)

    # All three DB queries are run in PARALLEL via asyncio.gather. Each has its
    # own session and its own tight statement_timeout, and each has its own
    # try/except so one slow query can't kill the others. Worst-case total is
    # max(5, 5, 6) = 6 s for the DB stage instead of the 21 s sum if sequential.

    async def _stats_query() -> tuple[int, int, Optional[float]]:
        try:
            async with AsyncSessionLocal() as db:
                await db.execute(text("SET LOCAL statement_timeout = '5000'"))
                row = await db.execute(
                    text("""
                        SELECT
                            COUNT(*) FILTER (
                                WHERE created_at >= :window_start
                                  AND (activity_metadata->>'status_code')::int >= 400
                            ) AS errors_today,
                            COUNT(*) FILTER (
                                WHERE created_at >= :prev_start
                                  AND created_at < :window_start
                                  AND (activity_metadata->>'status_code')::int >= 400
                            ) AS errors_yesterday,
                            ROUND(
                                (
                                    AVG((activity_metadata->>'duration_ms')::float)
                                    FILTER (
                                        WHERE created_at >= :window_start
                                          AND activity_metadata->>'duration_ms' IS NOT NULL
                                    )
                                )::numeric,
                                1
                            ) AS avg_ms
                        FROM user_activity_logs
                        WHERE created_at >= :prev_start
                    """),
                    {"window_start": window_start, "prev_start": prev_window_start},
                )
                r = row.fetchone()
                return (
                    r.errors_today or 0,
                    r.errors_yesterday or 0,
                    float(r.avg_ms) if r.avg_ms is not None else None,
                )
        except Exception as exc:
            logger.warning("system/status stats query failed: %s", exc)
            return 0, 0, None

    async def _p95_query() -> Optional[float]:
        try:
            async with AsyncSessionLocal() as db:
                await db.execute(text("SET LOCAL statement_timeout = '5000'"))
                row = await db.execute(
                    text("""
                        SELECT
                            ROUND(
                                (
                                    PERCENTILE_CONT(0.95) WITHIN GROUP (
                                        ORDER BY (activity_metadata->>'duration_ms')::float
                                    )
                                )::numeric,
                                1
                            ) AS p95_ms
                        FROM user_activity_logs
                        WHERE created_at >= :window_start
                          AND activity_metadata->>'duration_ms' IS NOT NULL
                    """),
                    {"window_start": window_start},
                )
                r = row.fetchone()
                return float(r.p95_ms) if r.p95_ms is not None else None
        except Exception as exc:
            logger.warning("system/status p95 query failed: %s", exc)
            return None

    async def _mail_metrics_query() -> tuple[int, int, int]:
        try:
            async with AsyncSessionLocal() as db:
                await db.execute(text("SET LOCAL statement_timeout = '6000'"))
                row = await db.execute(
                    text("""
                        WITH active_triggers AS (
                            SELECT COUNT(*) AS trigger_count
                            FROM courtdrive_ingestions
                            WHERE ingestion_type = 'court_mail_trigger'
                              AND status = 'active'
                        ),
                        gmail_activity AS (
                            SELECT
                                COALESCE(SUM(
                                    CASE
                                        WHEN COALESCE(activity_metadata->>'emails_scanned', '') ~ '^[0-9]+$'
                                        THEN (activity_metadata->>'emails_scanned')::int
                                        ELSE 0
                                    END
                                ), 0) AS emails_scanned,
                                COALESCE(SUM(
                                    CASE
                                        WHEN COALESCE(activity_metadata->>'documents_stored', '') ~ '^[0-9]+$'
                                        THEN (activity_metadata->>'documents_stored')::int
                                        ELSE 0
                                    END
                                ), 0) AS documents_stored
                            FROM user_activity_logs
                            WHERE action = 'gmail_ingest'
                              AND created_at >= NOW() - INTERVAL '30 days'
                        ),
                        accepted_pending AS (
                            SELECT
                                COALESCE(SUM(
                                    CASE
                                        WHEN COALESCE((result::jsonb -> 'existing_court_mail' ->> 'emails_scanned'), '') ~ '^[0-9]+$'
                                        THEN (result::jsonb -> 'existing_court_mail' ->> 'emails_scanned')::int
                                        ELSE 0
                                    END
                                ), 0) AS emails_scanned,
                                COALESCE(SUM(
                                    CASE
                                        WHEN COALESCE((result::jsonb -> 'existing_court_mail' ->> 'documents_stored'), '') ~ '^[0-9]+$'
                                        THEN (result::jsonb -> 'existing_court_mail' ->> 'documents_stored')::int
                                        ELSE 0
                                    END
                                ), 0) AS documents_stored
                            FROM courtdrive_ingestions
                            WHERE ingestion_type = 'pending_acceptance'
                              AND status = 'accepted'
                              AND created_at >= NOW() - INTERVAL '30 days'
                        )
                        SELECT
                            active_triggers.trigger_count AS trigger_count,
                            gmail_activity.emails_scanned + accepted_pending.emails_scanned AS emails_scanned,
                            gmail_activity.documents_stored + accepted_pending.documents_stored AS documents_stored
                        FROM active_triggers, gmail_activity, accepted_pending
                    """)
                )
                r = row.fetchone()
                return (
                    r.trigger_count or 0,
                    r.emails_scanned or 0,
                    r.documents_stored or 0,
                )
        except Exception as exc:
            logger.warning("system/status mail_metrics query failed: %s", exc)
            return 0, 0, 0

    (errors_today, errors_yesterday, avg_ms), p95_ms, (trigger_count, total_emails_scanned, total_documents_stored) = await asyncio.gather(
        _stats_query(),
        _p95_query(),
        _mail_metrics_query(),
    )

    worker_instance = getattr(request.app.state, "court_mail_poll_worker", None)
    last_run_at = poll_redis.get("last_run_at") or (
        worker_instance.last_run_at if worker_instance else None
    )
    last_result = dict(poll_redis.get("last_result") or (
        worker_instance.last_result if worker_instance else None
    ) or {})

    if "triggers_polled" in last_result:
        last_result["last_poll_triggers_polled"] = last_result.get("triggers_polled", 0)
    if "emails_scanned" in last_result:
        last_result["last_poll_emails_scanned"] = last_result.get("emails_scanned", 0)
    if "documents_stored" in last_result:
        last_result["last_poll_documents_stored"] = last_result.get("documents_stored", 0)

    last_result["total_triggers_registered"] = trigger_count
    last_result["total_emails_scanned"] = total_emails_scanned
    last_result["total_documents_stored"] = total_documents_stored

    response = SystemStatusResponse(
        task_queue=TaskQueueStatus(
            active=task_counts["active"],
            pending=task_counts["pending"],
        ),
        errors=ErrorsStatus(
            count_24h=errors_today,
            delta_from_yesterday=errors_today - errors_yesterday,
        ),
        avg_response=AvgResponseStatus(avg_ms=avg_ms, p95_ms=p95_ms),
        poll_worker=PollWorkerStatus(
            enabled=bool(settings.COURT_MAIL_POLL_WORKER_ENABLED),
            running=bool(worker_instance.is_running) if worker_instance else False,
            interval_seconds=settings.COURT_MAIL_POLL_INTERVAL_SECONDS,
            last_run_at=last_run_at,
            last_result=last_result,
        ),
        checked_at=now.isoformat(),
    )

    try:
        _r.setex(_SYSTEM_STATUS_CACHE_KEY, _SYSTEM_STATUS_CACHE_TTL, response.model_dump_json())
    except Exception:
        pass
    finally:
        _r.close()

    return response


# ---------------------------------------------------------------------------
# GET /kpis/api-calls
# ---------------------------------------------------------------------------

KNOWN_ACTIONS = [
    "register", "login", "logout", "chat_message", "gmail_ingest",
    "upload_pdf", "summon_case", "accept_case", "deny_case", "archive_case", "delete_case",
    "draft_motion", "generate_document", "start_review", "download_motion",
    "download_petition", "pleading_task_input", "pleading_task_cancel",
    "pleading_task_regenerate", "pleading_use_existing", "review_task_cancel",
    "others",
]


class ActionCount(BaseModel):
    action: str
    count: int
    error_count: int


class DailyActivityPoint(BaseModel):
    date: str
    count: int
    error_count: int
    by_action: dict[str, int]


class ApiCallsKpiResponse(BaseModel):
    total: int
    error_total: int
    by_action: list[ActionCount]
    by_user: list[dict]
    daily: list[DailyActivityPoint]
    filters: dict
    date_range: DateRangeInfo


@router.get("/kpis/api-calls", response_model=ApiCallsKpiResponse)
async def get_api_calls_kpi(
    dr: DateRangeParams = Depends(),
    _user: User = Depends(get_current_firm_user),
    action: Optional[str] = Query(None, description="Filter by action key"),
    user_id: Optional[str] = Query(None, description="Filter by user_id"),
    session_id: Optional[str] = Query(None, description="Filter by session_id"),
):
    """
    Returns activity counts from user_activity_logs with optional filters.
    """
    params: dict = {"start": dr.start, "end": dr.end}
    filters_applied: dict = {"range": dr.range}

    extra_where = ""
    if action:
        extra_where += " AND action = :action"
        params["action"] = action
        filters_applied["action"] = action
    if user_id:
        extra_where += " AND user_id = :user_id"
        params["user_id"] = user_id
        filters_applied["user_id"] = user_id
    if session_id:
        extra_where += " AND session_id = :session_id"
        params["session_id"] = session_id
        filters_applied["session_id"] = session_id

    base_filter = f"""
        WHERE created_at >= :start
          AND created_at <= :end
          {extra_where}
    """

    async with AsyncSessionLocal() as db:
        totals_row = await db.execute(
            text(f"""
                SELECT
                    COUNT(*) AS cnt,
                    COUNT(*) FILTER (
                        WHERE (activity_metadata->>'status_code')::int >= 400
                    ) AS error_cnt
                FROM user_activity_logs
                {base_filter}
            """),
            params,
        )
        totals = totals_row.fetchone()
        total = totals.cnt or 0
        error_total = totals.error_cnt or 0

        action_rows = await db.execute(
            text(f"""
                SELECT
                    action,
                    COUNT(*) AS cnt,
                    COUNT(*) FILTER (
                        WHERE (activity_metadata->>'status_code')::int >= 400
                    ) AS error_cnt
                FROM user_activity_logs
                {base_filter}
                GROUP BY action
                ORDER BY cnt DESC
            """),
            params,
        )
        by_action = [
            ActionCount(action=row.action, count=row.cnt, error_count=row.error_cnt or 0)
            for row in action_rows
        ]

        user_rows = await db.execute(
            text(f"""
                SELECT user_id, COUNT(*) AS cnt
                FROM user_activity_logs
                {base_filter}
                  AND user_id IS NOT NULL
                GROUP BY user_id
                ORDER BY cnt DESC
                LIMIT 20
            """),
            params,
        )
        by_user = [{"user_id": row.user_id, "count": row.cnt} for row in user_rows]

        daily_rows = await db.execute(
            text(f"""
                SELECT
                    DATE(created_at AT TIME ZONE 'UTC') AS day,
                    action,
                    COUNT(*) AS cnt,
                    COUNT(*) FILTER (
                        WHERE (activity_metadata->>'status_code')::int >= 400
                    ) AS error_cnt
                FROM user_activity_logs
                {base_filter}
                GROUP BY day, action
                ORDER BY day
            """),
            params,
        )

        daily_map: dict[str, dict] = {}
        for row in daily_rows:
            day_str = row.day.isoformat()
            if day_str not in daily_map:
                daily_map[day_str] = {"by_action": {}, "error_count": 0}
            daily_map[day_str]["by_action"][row.action] = row.cnt
            daily_map[day_str]["error_count"] += row.error_cnt or 0

        daily = [
            DailyActivityPoint(
                date=day_str,
                count=sum(d["by_action"].values()),
                error_count=d["error_count"],
                by_action=d["by_action"],
            )
            for day_str, d in sorted(daily_map.items())
        ]

    return ApiCallsKpiResponse(
        total=total,
        error_total=error_total,
        by_action=by_action,
        by_user=by_user,
        daily=daily,
        filters=filters_applied,
        date_range=DateRangeInfo(preset=dr.range, start=dr.start, end=dr.end),
    )


# ---------------------------------------------------------------------------
# GET /activity/feed
# ---------------------------------------------------------------------------

class ActivityFeedItem(BaseModel):
    id: str
    action: str
    label: str
    detail: Optional[str]
    actor_name: Optional[str]
    user_id: Optional[str]
    session_id: Optional[str]
    metadata: Optional[dict]
    occurred_at: str


class ActivityFeedResponse(BaseModel):
    items: list[ActivityFeedItem]
    total: int
    limit: int
    offset: int
    date_range: DateRangeInfo


@router.get("/activity/feed", response_model=ActivityFeedResponse)
async def get_activity_feed(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    action: Optional[str] = Query(None, description="Filter by action key"),
    user_id: Optional[str] = Query(None),
    include_system: bool = Query(False, description="Include low-signal 'others' entries"),
    dr: DateRangeParams = Depends(),
    _user: User = Depends(get_current_firm_user),
):
    """
    Paginated recent-events feed sourced from user_activity_logs.
    Excludes low-signal 'others' entries by default.
    """
    async with AsyncSessionLocal() as db:
        filters: list[str] = ["created_at >= :start", "created_at <= :end"]
        params: dict = {"start": dr.start, "end": dr.end, "limit": limit, "offset": offset}

        if not include_system and not action:
            filters.append("action != :excluded_action")
            params["excluded_action"] = "others"

        if action:
            filters.append("action = :action")
            params["action"] = action

        if user_id:
            filters.append("user_id = :user_id")
            params["user_id"] = user_id

        where_clause = " AND ".join(filters)

        count_row = await db.execute(
            text(f"SELECT COUNT(*) FROM user_activity_logs WHERE {where_clause}"),
            params,
        )
        total = count_row.scalar() or 0

        rows = await db.execute(
            text(f"""
                SELECT id, action, user_id, session_id, activity_metadata, created_at
                FROM user_activity_logs
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """),
            params,
        )
        rows = rows.fetchall()

    user_ids = list({row.user_id for row in rows if row.user_id})
    actor_map: dict[str, str] = {}
    if user_ids:
        async with UserAsyncSessionLocal() as user_db:
            name_rows = await user_db.execute(
                text("SELECT id, first_name, last_name, email FROM users WHERE id = ANY(:ids)"),
                {"ids": user_ids},
            )
            for nr in name_rows.fetchall():
                first = (nr.first_name or "").strip()
                last = (nr.last_name or "").strip()
                actor_map[nr.id] = f"{first} {last}".strip() if (first or last) else nr.email

    items = [
        ActivityFeedItem(
            id=row.id,
            action=row.action,
            label=_ACTION_LABELS.get(row.action, row.action),
            detail=_build_activity_detail(row.action, row.activity_metadata),
            actor_name=actor_map.get(row.user_id) if row.user_id else None,
            user_id=row.user_id,
            session_id=row.session_id,
            metadata=row.activity_metadata,
            occurred_at=row.created_at.isoformat(),
        )
        for row in rows
    ]

    return ActivityFeedResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        date_range=DateRangeInfo(preset=dr.range, start=dr.start, end=dr.end),
    )


# ---------------------------------------------------------------------------
# GET /charts/users-daily
# ---------------------------------------------------------------------------

class DailyUserPoint(BaseModel):
    date: str
    active_users: int
    motions_drafted: int
    new_users: int


class UsersDailyResponse(BaseModel):
    data: list[DailyUserPoint]
    date_range: DateRangeInfo


@router.get("/charts/users-daily", response_model=UsersDailyResponse)
async def get_users_daily(
    dr: DateRangeParams = Depends(),
    _user: User = Depends(get_current_firm_user),
):
    """
    Returns per-day user activity trend for charting.

    Three series, all zero-filled so every day in the range has a point:
      active_users    — distinct users who logged any activity action that day
      motions_drafted — motion_draft_logs entries created that day (all statuses)
      new_users       — users registered that day (user_db)

    Cross-DB strategy: new_users is queried from user_db; active_users and
    motions_drafted come from chat_db. Results are merged in Python.
    """
    params = {"start": dr.start, "end": dr.end}

    # Build the full date spine for zero-filling
    spine: list[str] = []
    cur: date = dr.start.date()
    end_date: date = dr.end.date()
    while cur <= end_date:
        spine.append(cur.isoformat())
        cur += timedelta(days=1)

    # Run both DB queries concurrently
    async def _query_user_db() -> dict[str, int]:
        async with UserAsyncSessionLocal() as db:
            rows = await db.execute(
                text("""
                    SELECT
                        DATE(created_at AT TIME ZONE 'UTC') AS day,
                        COUNT(*) AS cnt
                    FROM users
                    WHERE is_active = true
                      AND created_at >= :start
                      AND created_at <= :end
                    GROUP BY day
                """),
                params,
            )
            return {row.day.isoformat(): int(row.cnt) for row in rows}

    async def _query_chat_db() -> tuple[dict[str, int], dict[str, int]]:
        async with AsyncSessionLocal() as db:
            active_rows = await db.execute(
                text("""
                    SELECT
                        DATE(created_at AT TIME ZONE 'UTC') AS day,
                        COUNT(DISTINCT user_id) AS cnt
                    FROM user_activity_logs
                    WHERE user_id IS NOT NULL
                      AND created_at >= :start
                      AND created_at <= :end
                    GROUP BY day
                """),
                params,
            )
            active_map: dict[str, int] = {row.day.isoformat(): int(row.cnt) for row in active_rows}

            motions_rows = await db.execute(
                text("""
                    SELECT
                        DATE(created_at AT TIME ZONE 'UTC') AS day,
                        COUNT(*) AS cnt
                    FROM motion_draft_logs
                    WHERE created_at >= :start
                      AND created_at <= :end
                    GROUP BY day
                """),
                params,
            )
            motions_map: dict[str, int] = {row.day.isoformat(): int(row.cnt) for row in motions_rows}

        return active_map, motions_map

    new_users_map, (active_map, motions_map) = await asyncio.gather(
        _query_user_db(),
        _query_chat_db(),
    )

    data = [
        DailyUserPoint(
            date=day,
            active_users=active_map.get(day, 0),
            motions_drafted=motions_map.get(day, 0),
            new_users=new_users_map.get(day, 0),
        )
        for day in spine
    ]

    return UsersDailyResponse(
        data=data,
        date_range=DateRangeInfo(preset=dr.range, start=dr.start, end=dr.end),
    )
