"""
Dashboard chat snapshot aggregator.

Fetches all KPI + chart data needed for the AI chat context in one concurrent
gather call. Always covers the last 30 days. Results are cached 5 minutes.

Also provides a lightweight today mini-snapshot (cached 60 s) so Claude can
answer "what happened today?" questions without calling a tool.

Called by: POST /insights/chat, POST /insights/chat/stream (analytics_insights.py)
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from ...chatbot.database import AsyncSessionLocal
from .kpis import (
    _fetch_cases_kpi_global,
    _fetch_motions_kpi,
    _fetch_users_kpi,
    _fetch_cases_daily,
    _fetch_motions_daily,
    _fetch_motions_by_type,
    _fetch_users_daily,
)
from .analytics_motions import _fetch_motions_kpi_enriched
from .analytics_insights import _fetch_metrics

_SNAPSHOT_TTL = 300  # 5 min
_TODAY_TTL    = 60   # 1 min — today counters refresh faster
_snapshot_cache: dict[str, tuple[dict, float]] = {}
_today_cache:    dict[str, tuple[dict, float]] = {}


async def _fetch_today_snapshot() -> dict:
    """
    Lightweight today counters — activity by action, motions by status,
    cases opened today. Cached 60 s so "what happened today?" answers stay fresh.
    Called by: _fetch_dashboard_snapshot
    """
    cache_key = "today"
    now_mono = time.monotonic()

    if cache_key in _today_cache:
        cached, cached_at = _today_cache[cache_key]
        if now_mono - cached_at < _TODAY_TTL:
            return cached

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    async def _activity():
        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                text("""
                    SELECT action, COUNT(*) AS cnt
                    FROM user_activity_logs
                    WHERE created_at >= :start
                    GROUP BY action
                    ORDER BY cnt DESC
                """),
                {"start": today_start},
            )
            return {r.action: int(r.cnt) for r in rows.fetchall()}

    async def _motions():
        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                text("""
                    SELECT status, COUNT(*) AS cnt
                    FROM motion_draft_logs
                    WHERE created_at >= :start
                    GROUP BY status
                """),
                {"start": today_start},
            )
            return {r.status: int(r.cnt) for r in rows.fetchall()}

    async def _cases():
        async with AsyncSessionLocal() as db:
            row = await db.execute(
                text("""
                    SELECT COUNT(DISTINCT p.session_id) AS cnt
                    FROM pdf_documents p
                    INNER JOIN sessions s ON s.id = p.session_id
                    WHERE s.created_at >= :start
                """),
                {"start": today_start},
            )
            return int(row.scalar() or 0)

    activity_by_action, motions_by_status, cases_today = await asyncio.gather(
        _activity(), _motions(), _cases()
    )

    result = {
        "date":              today_start.date().isoformat(),
        "activity_by_action": activity_by_action,
        "total_activities":  sum(activity_by_action.values()),
        "motions_by_status": motions_by_status,
        "total_motions":     sum(motions_by_status.values()),
        "cases_opened":      cases_today,
    }
    _today_cache[cache_key] = (result, now_mono)
    return result


async def _fetch_dashboard_snapshot() -> dict:
    """
    Aggregates KPI + chart data for Claude context injection.
    Always covers the last 30 days (cached 5 min) plus a today mini-snapshot
    (cached 60 s).
    Called by: POST /insights/chat, POST /insights/chat/stream (analytics_insights.py)
    """
    cache_key = "snapshot_30d"
    now = time.monotonic()

    if cache_key in _snapshot_cache:
        cached, cached_at = _snapshot_cache[cache_key]
        if now - cached_at < _SNAPSHOT_TTL:
            # Today snapshot always refreshes independently
            cached["today"] = await _fetch_today_snapshot()
            return cached

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=30)

    (
        motion_metrics,
        cases_kpi,
        motions_kpi,
        motions_kpi_enriched,
        users_kpi,
        cases_daily,
        motions_daily,
        motions_by_type,
        users_daily,
        today,
    ) = await asyncio.gather(
        _fetch_metrics(start, end),
        _fetch_cases_kpi_global(),
        _fetch_motions_kpi(start, end),
        _fetch_motions_kpi_enriched(start, end),
        _fetch_users_kpi(start, end),
        _fetch_cases_daily(start, end),
        _fetch_motions_daily(start, end),
        _fetch_motions_by_type(start, end),
        _fetch_users_daily(start, end),
        _fetch_today_snapshot(),
    )

    snapshot = {
        "motion_metrics":       motion_metrics,
        "cases_kpi":            cases_kpi,
        "motions_kpi":          motions_kpi,
        "motions_kpi_enriched": motions_kpi_enriched,
        "users_kpi":            users_kpi,
        "cases_daily":          cases_daily,
        "motions_daily":        motions_daily,
        "motions_by_type":      motions_by_type,
        "users_daily":          users_daily,
        "today":                today,
    }

    _snapshot_cache[cache_key] = (snapshot, now)
    return snapshot
