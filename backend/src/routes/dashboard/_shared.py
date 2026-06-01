"""
Shared utilities for all dashboard route modules.

Imported by kpis.py, analytics_users.py, analytics_cases.py,
analytics_motions.py, and activity_log.py — keeps constants and
helpers in one place so they never drift out of sync.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Query
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Date-range dependency
# ---------------------------------------------------------------------------

class DateRangeParams:
    """
    Resolves query params into concrete UTC start/end datetimes.

    Preset   | start                   | end
    ---------|-------------------------|----------
    today    | midnight today          | now
    7d       | 7 days ago              | now
    30d      | 30 days ago (default)   | now
    custom   | ?start=YYYY-MM-DD       | ?end=YYYY-MM-DD (inclusive)
    """

    def __init__(
        self,
        range: str = Query("30d", pattern="^(today|7d|30d|custom)$"),
        start: Optional[date] = Query(None, description="Required when range=custom"),
        end: Optional[date] = Query(None, description="Required when range=custom"),
    ):
        now = datetime.now(timezone.utc)

        if range == "today":
            self.start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            self.end = now
        elif range == "7d":
            self.start = now - timedelta(days=7)
            self.end = now
        elif range == "30d":
            self.start = now - timedelta(days=30)
            self.end = now
        else:  # custom
            if start is None or end is None:
                raise HTTPException(
                    status_code=422,
                    detail="range=custom requires both start and end query parameters (YYYY-MM-DD)",
                )
            if end < start:
                raise HTTPException(status_code=422, detail="end must be >= start")
            self.start = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
            self.end = datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=timezone.utc)

        self.range = range


class DateRangeInfo(BaseModel):
    preset: str
    start: datetime
    end: datetime


# ---------------------------------------------------------------------------
# Base CTE reused by /cases, analytics_cases, and chart endpoints.
#
# Defensive query strategy (guards against known data integrity bugs):
#   BUG 1 — save_pdf_metadata always INSERTs: use DISTINCT ON session_id
#   BUG 3 — mark_pending_acceptance_viewed creates ghost ingestion rows:
#            classify by petition_status on pdf_documents, not ingestion rows
#   BUG 4 — deactivate_session sets is_active=false on denied/archived cases:
#            NEVER filter sessions.is_active=true; use petition_status
#   BUG 5 — POST /sessions creates empty sessions: require at least one PDF
# ---------------------------------------------------------------------------

_BASE_CTE = """
    WITH sessions_with_pdf AS (
        SELECT DISTINCT p.session_id, s.is_active AS session_is_active
        FROM pdf_documents p
        INNER JOIN sessions s ON s.id = p.session_id
        WHERE s.created_at >= :start
          AND s.created_at <= :end
    ),
    -- Sessions that have at least one active thread — mirrors the sidebar filter
    sessions_with_active_thread AS (
        SELECT DISTINCT session_id
        FROM chat_threads
        WHERE is_active = true
    ),
    -- Sessions with a live pending-acceptance ingestion row.
    -- Mirrors the inbox gate in /threads/pending-petitions.
    sessions_with_pending_ingestion AS (
        SELECT DISTINCT session_id
        FROM courtdrive_ingestions
        WHERE ingestion_type = 'pending_acceptance'
          AND status = 'pending_acceptance'
    ),
    -- Most-recent petition_status per session (DISTINCT ON handles BUG 1 duplicates).
    latest_pdf_status AS (
        SELECT DISTINCT ON (p.session_id)
            p.session_id,
            p.petition_status,
            p.inbox_checked_at,
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
    -- Classify each session into one of: active | pending | inactive | other
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
            END AS bucket
        FROM latest_pdf_status
    )
"""

# Same classification logic as _BASE_CTE but without the date filter on
# sessions — used by /cases to return stable global counts regardless of
# the selected date range.
_GLOBAL_CTE = """
    WITH sessions_with_pdf AS (
        SELECT DISTINCT p.session_id, s.is_active AS session_is_active
        FROM pdf_documents p
        INNER JOIN sessions s ON s.id = p.session_id
    ),
    sessions_with_active_thread AS (
        SELECT DISTINCT session_id
        FROM chat_threads
        WHERE is_active = true
    ),
    sessions_with_pending_ingestion AS (
        SELECT DISTINCT session_id
        FROM courtdrive_ingestions
        WHERE ingestion_type = 'pending_acceptance'
          AND status = 'pending_acceptance'
    ),
    latest_pdf_status AS (
        SELECT DISTINCT ON (p.session_id)
            p.session_id,
            p.petition_status,
            p.inbox_checked_at,
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
                WHEN petition_status IN ('denied', 'archived', 'deleted', 'auto_archived')   THEN 'inactive'
                ELSE 'other'
            END AS bucket
        FROM latest_pdf_status
    )
"""


# ---------------------------------------------------------------------------
# Motion display names — used by kpis.py and analytics_motions.py
# ---------------------------------------------------------------------------

_MOTION_DISPLAY_NAMES: dict[str, str] = {
    # Motions
    "extend":             "Motion to Extend Automatic Stay",
    "modify":             "Motion to Modify Plan",
    "value":              "Motion to Value Personal Property",
    "withdraw":           "Motion to Withdraw",
    "waive":              "Motion to Waive",
    "claim":              "Objection to Claim",
    "delay":              "Motion to Delay",
    "reinstate":          "Motion to Reinstate",
    "suggestion":         "Suggestion of Bankruptcy",
    "loe":                "Letter of Explanation",
    "ex-parte-extension": "Ex Parte Extension",
    "notice-withdraw":    "Notice of Withdrawal",
    # Orders
    "objection-sustain":  "Order on Objection to Claim",
    "order-extend":       "Order on Motion to Extend Stay",
    "order-withdraw":     "Order on Motion to Withdraw",
    "order-waive":        "Order on Motion to Waive",
    "order-value":        "Order on Motion to Value",
    "order-reinstate":    "Order on Motion to Reinstate",
    "order-extension":    "Order on Motion for Extension",
    "order-delay":        "Order on Motion to Delay",
}


# ---------------------------------------------------------------------------
# Activity label map and detail builder — used by kpis.py and activity_log.py
# ---------------------------------------------------------------------------

_ACTION_LABELS: dict[str, str] = {
    "login":                    "User logged in",
    "logout":                   "User logged out",
    "register":                 "User registered",
    "upload_pdf":               "PDF uploaded",
    "summon_case":              "Case summoned",
    "accept_case":              "Case accepted",
    "deny_case":                "Case denied",
    "archive_case":             "Case archived",
    "generate_document":        "Document generated",
    "download_motion":          "Motion downloaded",
    "download_petition":        "Petition downloaded",
    "pleading_task_input":      "Pleading input submitted",
    "pleading_task_cancel":     "Pleading task cancelled",
    "pleading_task_regenerate": "Pleading task regenerated",
    "pleading_use_existing":    "Existing pleading selected",
    "review_task_cancel":       "Review task cancelled",
    "others":                   "API call",
}

_SYSTEM_ACTIONS = {"others"}


def _build_activity_detail(action: str, meta: Optional[dict]) -> Optional[str]:
    """
    Build a human-readable detail string from activity_metadata per action type.
    Returns None when there is nothing meaningful to add beyond the label.
    """
    if not meta:
        return None
    parts: list[str] = []
    if action == "draft_motion":
        if meta.get("motion_type"):
            parts.append(meta["motion_type"])
        if meta.get("case_name"):
            parts.append(f"for {meta['case_name']}")
    elif action == "generate_document":
        if meta.get("motion_type"):
            parts.append(meta["motion_type"])
        if meta.get("format"):
            parts.append(f"({meta['format'].upper()})")
    elif action == "upload_pdf":
        if meta.get("filename"):
            parts.append(meta["filename"])
        if meta.get("file_size"):
            kb = round(meta["file_size"] / 1024, 1)
            parts.append(f"({kb} KB)")
    elif action == "summon_case":
        if meta.get("case_number"):
            parts.append(f"Case #{meta['case_number']}")
        if meta.get("source"):
            parts.append(f"via {meta['source']}")
    elif action == "accept_case":
        if meta.get("client_name"):
            parts.append(meta["client_name"])
        if meta.get("case_number"):
            parts.append(f"#{meta['case_number']}")
    elif action == "deny_case":
        if meta.get("case_number"):
            parts.append(f"Case #{meta['case_number']}")
    elif action == "archive_case":
        if meta.get("reason"):
            parts.append(f"Reason: {meta['reason']}")
    elif action in ("login", "logout", "register"):
        if meta.get("email"):
            parts.append(meta["email"])
    elif action == "start_review":
        if meta.get("case_name"):
            parts.append(meta["case_name"])
    elif action == "pleading_task_input":
        if meta.get("motion_type"):
            parts.append(meta["motion_type"])
        if meta.get("case_name"):
            parts.append(f"for {meta['case_name']}")
    elif action in ("download_motion", "download_petition"):
        if meta.get("motion_type"):
            parts.append(meta["motion_type"])
        if meta.get("case_name"):
            parts.append(f"— {meta['case_name']}")
    elif action == "others":
        if meta.get("method") and meta.get("path"):
            parts.append(f"{meta['method']} {meta['path']}")
    return " ".join(parts) if parts else None
