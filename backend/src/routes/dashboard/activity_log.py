"""
Analytics sub-page: Activity Log (audit-grade timeline).

GET /activity-log         → /api/dashboard/activity-log
GET /activity-log/actions → /api/dashboard/activity-log/actions

Filters applied at SQL level:
  date range, actor_id, action(s), entity_id, search

Filters applied in Python (requires derivation):
  entity_type, status

Search pre-queries user_db for matching actor ids (name/email), then applies
a single OR condition across action, session_id, and key metadata fields.

Status for motion actions is resolved via a batch query to motion_draft_logs
(Option B — most accurate for motion lifecycle tracking).
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text

from ...auth.models import User
from ...common.dependencies import get_current_firm_user
from ...auth.database import UserAsyncSessionLocal
from ...chatbot.database import AsyncSessionLocal
from ._shared import (
    DateRangeParams,
    DateRangeInfo,
    _ACTION_LABELS,
    _build_activity_detail,
    _MOTION_DISPLAY_NAMES,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analytics"])


# ---------------------------------------------------------------------------
# Internal query function — called by analytics_insights.py chat tools
# ---------------------------------------------------------------------------

async def _query_activity_log(
    start: datetime,
    end: datetime,
    action: Optional[str] = None,
    actor_id: Optional[str] = None,
    entity_id: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 20,
    firm_id: Optional[str] = None,
) -> dict:
    """
    Called by: _execute_chat_tool (analytics_insights.py)
    Returns total_count (full matching set) and up to 50 rows with sanitized metadata.
    COUNT(*) OVER () computes the total before LIMIT is applied — one query pass.
    """
    sql_filters = ["created_at >= :start", "created_at <= :end"]
    params: dict = {"start": start, "end": end}
    if firm_id:
        sql_filters.append("firm_id = :firm_id")
        params["firm_id"] = firm_id

    if action:
        sql_filters.append("action = :action_filter")
        params["action_filter"] = action
    if actor_id:
        sql_filters.append("user_id = :actor_id")
        params["actor_id"] = actor_id
    if entity_id:
        sql_filters.append(
            "(activity_metadata->>'case_number' = :entity_id OR session_id = :entity_id)"
        )
        params["entity_id"] = entity_id
    if search:
        sql_filters.append(
            "(action ILIKE :search_q OR session_id ILIKE :search_q"
            " OR activity_metadata->>'case_number' ILIKE :search_q"
            " OR activity_metadata->>'motion_type' ILIKE :search_q)"
        )
        params["search_q"] = f"%{search}%"

    where = " AND ".join(sql_filters)
    capped_limit = min(limit, 50)

    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            text(f"""
                SELECT id, action, user_id, session_id, activity_metadata, created_at,
                       COUNT(*) OVER () AS total_count
                FROM user_activity_logs
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            {**params, "limit": capped_limit},
        )
        all_rows = rows.fetchall()

    total_count = int(all_rows[0].total_count) if all_rows else 0

    unique_user_ids = list({r.user_id for r in all_rows if r.user_id})
    actor_name_map: dict[str, str] = {}
    if unique_user_ids:
        async with UserAsyncSessionLocal() as user_db:
            user_rows = await user_db.execute(
                text("SELECT id, first_name, last_name, email FROM users WHERE id = ANY(:ids)"),
                {"ids": unique_user_ids},
            )
            for ur in user_rows.fetchall():
                first = (ur.first_name or "").strip()
                last = (ur.last_name or "").strip()
                actor_name_map[ur.id] = f"{first} {last}".strip() or ur.email

    return {
        "total_count": total_count,
        "returned": len(all_rows),
        "items": [
            {
                "occurred_at": row.created_at.isoformat() if row.created_at else None,
                "actor_name": actor_name_map.get(row.user_id) if row.user_id else None,
                "action": row.action,
                "label": _ACTION_LABELS.get(row.action, row.action),
                "detail": _build_activity_detail(row.action, row.activity_metadata or {}),
                "session_id": row.session_id,
            }
            for row in all_rows
        ],
    }


# ---------------------------------------------------------------------------
# Entity-type derivation tables
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
_CASE_ACTIONS = frozenset({"accept_case", "deny_case", "archive_case", "summon_case"})
_PDF_ACTIONS = frozenset({"upload_pdf", "download_petition"})
_USER_ACTIONS = frozenset({"login", "logout", "register"})
_SYSTEM_ACTIONS = frozenset({"others"})

_ENTITY_TYPE_TO_ACTIONS: dict[str, frozenset[str]] = {
    "motion": _MOTION_ACTIONS,
    "case":   _CASE_ACTIONS,
    "pdf":    _PDF_ACTIONS,
    "user":   _USER_ACTIONS,
    "system": _SYSTEM_ACTIONS,
}

# Status values that can be derived directly from the action name alone.
_ACTION_DERIVED_STATUS: dict[str, str] = {
    "accept_case":  "accepted",
    "deny_case":    "denied",
    "archive_case": "archived",
    "login":        "success",
    "logout":       "success",
    "register":     "success",
}

_SENSITIVE_KEYS = frozenset({"password", "token", "secret", "hash", "key", "auth"})
_MAX_STR_LEN = 200
_MAX_LIST_LEN = 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitize_metadata(meta: dict | None) -> dict | None:
    """Truncate long strings, redact sensitive keys, cap list lengths."""
    if not meta:
        return None
    out: dict = {}
    for k, v in meta.items():
        if any(s in k.lower() for s in _SENSITIVE_KEYS):
            out[k] = "[redacted]"
        elif isinstance(v, str):
            out[k] = v[:_MAX_STR_LEN] + "\u2026" if len(v) > _MAX_STR_LEN else v
        elif isinstance(v, dict):
            # One level of nesting — flatten without recursion
            out[k] = {
                sk: (
                    "[redacted]"
                    if any(s in sk.lower() for s in _SENSITIVE_KEYS)
                    else (
                        str(sv)[:_MAX_STR_LEN] + "\u2026"
                        if isinstance(sv, str) and len(sv) > _MAX_STR_LEN
                        else sv
                    )
                )
                for sk, sv in v.items()
            }
        elif isinstance(v, list):
            out[k] = (
                v[:_MAX_LIST_LEN] + [f"\u2026 ({len(v) - _MAX_LIST_LEN} more)"]
                if len(v) > _MAX_LIST_LEN
                else v
            )
        else:
            out[k] = v
    return out


def _derive_entity(
    action: str,
    meta: dict | None,
    session_id: str | None,
) -> tuple[str | None, str | None, str | None]:
    """Return (entity_type, entity_id, entity_label) for a log entry."""
    m = meta or {}
    if action in _MOTION_ACTIONS:
        mt = m.get("motion_type")
        return "motion", mt, (_MOTION_DISPLAY_NAMES.get(mt, mt) if mt else None)
    if action in _CASE_ACTIONS:
        cn = m.get("case_number")
        raw_name = m.get("case_name")
        # Joint-filing case names carry a literal `\n` between debtors for
        # docx-soft-break rendering. Flatten to ' & ' for human display.
        display_name = raw_name.replace("\n", " & ") if isinstance(raw_name, str) else raw_name
        label = display_name or (f"Case #{cn}" if cn else None)
        return "case", cn or session_id, label
    if action in _PDF_ACTIONS:
        fn = m.get("filename")
        return "pdf", fn or session_id, fn
    if action in _USER_ACTIONS:
        return "user", None, m.get("email")
    if action in _SYSTEM_ACTIONS:
        path = m.get("path")
        method = m.get("method")
        label = f"{method} {path}" if method and path else path
        return "system", path, label
    return None, session_id, None


def _derive_status(
    action: str,
    meta: dict | None,
    motion_status_map: dict[tuple[str, str], str],
    session_id: str | None,
) -> str | None:
    """
    Derive a display status for a log entry.

    Priority:
      1. Motion actions → look up motion_draft_logs via (session_id, motion_type).
      2. Action-based status (accept_case, deny_case, etc.).
      3. 'others' → HTTP status code from metadata.
    """
    m = meta or {}
    if action in _MOTION_ACTIONS and session_id:
        mt = m.get("motion_type")
        if mt:
            return motion_status_map.get((session_id, mt))
    if action in _ACTION_DERIVED_STATUS:
        return _ACTION_DERIVED_STATUS[action]
    if action == "others":
        sc = m.get("status_code")
        return str(sc) if sc is not None else None
    return None


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class ActorInfo(BaseModel):
    user_id: str
    name: Optional[str]
    email: Optional[str]


class AuditLogEntry(BaseModel):
    id: str
    occurred_at: datetime
    actor: Optional[ActorInfo]
    action: str
    label: str
    detail: Optional[str]
    entity_type: Optional[str]
    entity_id: Optional[str]
    entity_label: Optional[str]
    status: Optional[str]
    duration_ms: Optional[float]
    error_code: Optional[int]
    error_message: Optional[str]
    metadata: Optional[dict]
    session_id: Optional[str]


class AuditLogFiltersApplied(BaseModel):
    date_range: DateRangeInfo
    actor_id: Optional[str]
    actions: Optional[list[str]]
    entity_type: Optional[str]
    entity_id: Optional[str]
    status: Optional[str]
    search: Optional[str]


class ActivityLogKPI(BaseModel):
    total_events: int
    unique_actors: int
    error_rate: float   # 0.0–100.0, percentage of entries with HTTP status >= 400
    avg_duration_ms: Optional[float]


class AuditLogResponse(BaseModel):
    items: list[AuditLogEntry]
    total: int
    limit: int
    offset: int
    filters: AuditLogFiltersApplied
    kpi: ActivityLogKPI


# ---------------------------------------------------------------------------
# GET /activity-log/actions  — action options source for dropdowns/filters
# ---------------------------------------------------------------------------

class ActivityLogActionOption(BaseModel):
    action: str
    label: str
    count: int


class ActivityLogActionsResponse(BaseModel):
    actions: list[ActivityLogActionOption]
    date_range: DateRangeInfo


@router.get("/activity-log/actions", response_model=ActivityLogActionsResponse)
async def get_activity_log_actions(
    dr: DateRangeParams = Depends(),
    current_user: User = Depends(get_current_firm_user),
):
    """
    Returns the distinct action keys that appear in the given date range,
    each with its display label and occurrence count.

    Intended as the data source for action filter dropdowns — scales via a
    single aggregate SQL query regardless of dataset size.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("""
                SELECT action, COUNT(*) AS count
                FROM user_activity_logs
                WHERE created_at >= :start AND created_at <= :end
                  AND firm_id = :firm_id
                GROUP BY action
                ORDER BY count DESC
            """),
            {"start": dr.start, "end": dr.end, "firm_id": current_user.firm_id},
        )
        rows = result.fetchall()

    return ActivityLogActionsResponse(
        actions=[
            ActivityLogActionOption(
                action=row.action,
                label=_ACTION_LABELS.get(row.action, row.action),
                count=row.count,
            )
            for row in rows
        ],
        date_range=DateRangeInfo(preset=dr.range, start=dr.start, end=dr.end),
    )


# ---------------------------------------------------------------------------
# GET /activity-log
# ---------------------------------------------------------------------------

@router.get("/activity-log", response_model=AuditLogResponse)
async def get_activity_log(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    action: Optional[list[str]] = Query(None, description="One or more action keys (multi-value)"),
    actor_id: Optional[str] = Query(None, description="Filter by user_id"),
    entity_type: Optional[str] = Query(
        None,
        pattern="^(motion|case|pdf|user|system)$",
        description="Filter by derived entity type",
    ),
    entity_id: Optional[str] = Query(
        None,
        description="Match case_number in metadata OR session_id",
    ),
    status: Optional[str] = Query(None, description="Filter by derived status"),
    search: Optional[str] = Query(
        None,
        description="Full-text search across action, actor name/email, entity id, and key metadata fields",
    ),
    dr: DateRangeParams = Depends(),
    current_user: User = Depends(get_current_firm_user),
):
    """
    Audit-grade activity timeline with advanced filtering and metadata preview.

    Returns a paginated list of user_activity_logs entries enriched with:
      - Resolved actor identity (name + email, batch-fetched from user_db)
      - Derived entity_type / entity_id / entity_label
      - Derived status (motion status resolved from motion_draft_logs)
      - Sanitised metadata payload for debugging
    """
    # ── Actor pre-lookup for search ────────────────────────────────────────
    # Resolve user_ids whose name or email matches the search term before
    # building the main SQL query, so actor matching is pushed to SQL level.
    search_actor_ids: list[str] = []
    if search:
        async with UserAsyncSessionLocal() as user_db:
            actor_search_result = await user_db.execute(
                text("""
                    SELECT id FROM users
                    WHERE first_name ILIKE :q
                       OR last_name  ILIKE :q
                       OR email      ILIKE :q
                       OR CONCAT(first_name, ' ', last_name) ILIKE :q
                """),
                {"q": f"%{search}%"},
            )
            search_actor_ids = [r.id for r in actor_search_result.fetchall()]

    # ── Translate entity_type → action set ────────────────────────────────
    # entity_type is deterministically mapped to a set of action keys, so we
    # can push it down to SQL rather than filtering in Python.
    effective_actions: Optional[list[str]] = None

    if entity_type:
        type_actions = _ENTITY_TYPE_TO_ACTIONS.get(entity_type, frozenset())
        if action:
            # Intersect: keep only actions that belong to the requested type
            effective_actions = [a for a in action if a in type_actions]
            if not effective_actions:
                # No overlap — short-circuit with an empty result
                return AuditLogResponse(
                    items=[],
                    total=0,
                    limit=limit,
                    offset=offset,
                    filters=AuditLogFiltersApplied(
                        date_range=DateRangeInfo(preset=dr.range, start=dr.start, end=dr.end),
                        actor_id=actor_id,
                        actions=action,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        status=status,
                        search=search,
                    ),
                    kpi=ActivityLogKPI(
                        total_events=0,
                        unique_actors=0,
                        error_rate=0.0,
                        avg_duration_ms=None,
                    ),
                )
        else:
            effective_actions = list(type_actions)
    elif action:
        effective_actions = action

    # ── Build SQL WHERE clause ─────────────────────────────────────────────
    sql_filters: list[str] = ["created_at >= :start", "created_at <= :end", "firm_id = :firm_id"]
    params: dict = {"start": dr.start, "end": dr.end, "firm_id": current_user.firm_id}

    if effective_actions:
        sql_filters.append("action = ANY(:actions)")
        params["actions"] = effective_actions

    if actor_id:
        sql_filters.append("user_id = :actor_id")
        params["actor_id"] = actor_id

    if entity_id:
        # Match either case_number stored in metadata or the session_id column
        sql_filters.append(
            "(activity_metadata->>'case_number' = :entity_id OR session_id = :entity_id)"
        )
        params["entity_id"] = entity_id

    if search:
        # Search across action name, session_id, and the metadata fields that
        # contribute to entity/detail labels.  Actor matching uses the pre-fetched
        # user_ids to avoid a correlated subquery on every row.
        search_clauses = [
            "action ILIKE :search_q",
            "session_id ILIKE :search_q",
            "activity_metadata->>'case_number'  ILIKE :search_q",
            "activity_metadata->>'motion_type'  ILIKE :search_q",
            "activity_metadata->>'filename'     ILIKE :search_q",
            "activity_metadata->>'path'         ILIKE :search_q",
            "activity_metadata->>'email'        ILIKE :search_q",
        ]
        if search_actor_ids:
            search_clauses.append("user_id = ANY(:search_actor_ids)")
            params["search_actor_ids"] = search_actor_ids
        sql_filters.append(f"({' OR '.join(search_clauses)})")
        params["search_q"] = f"%{search}%"

    where = " AND ".join(sql_filters)

    # ── Fetch rows ─────────────────────────────────────────────────────────
    # When a status filter is active, status is a derived (Python-level) value
    # so SQL pagination would produce wrong totals. In that case we fetch all
    # SQL-matching rows and paginate in Python after derivation. For all other
    # cases we use standard SQL LIMIT/OFFSET + COUNT(*).
    status_filter_active = bool(status)

    async with AsyncSessionLocal() as db:
        if status_filter_active:
            rows_result = await db.execute(
                text(f"""
                    SELECT id, action, user_id, session_id, activity_metadata, created_at
                    FROM user_activity_logs
                    WHERE {where}
                    ORDER BY created_at DESC
                """),
                params,
            )
            all_rows = rows_result.fetchall()
            total_sql = len(all_rows)
            # KPI computed in Python after status filtering (below)
            sql_kpi: dict | None = None
        else:
            # Combined count + KPI aggregate in a single query
            kpi_result = await db.execute(
                text(f"""
                    SELECT
                        COUNT(*) AS total_events,
                        COUNT(DISTINCT user_id) AS unique_actors,
                        COALESCE(
                            ROUND(
                                COUNT(*) FILTER (
                                    WHERE (activity_metadata->>'status_code') IS NOT NULL
                                      AND (activity_metadata->>'status_code')::int >= 400
                                ) * 100.0 / NULLIF(COUNT(*), 0),
                                2
                            ),
                            0.0
                        ) AS error_rate,
                        AVG(
                            CASE WHEN activity_metadata->>'duration_ms' IS NOT NULL
                            THEN (activity_metadata->>'duration_ms')::float END
                        ) AS avg_duration_ms
                    FROM user_activity_logs
                    WHERE {where}
                """),
                params,
            )
            kpi_row = kpi_result.fetchone()
            total_sql: int = kpi_row.total_events or 0
            sql_kpi = {
                "total_events": int(kpi_row.total_events or 0),
                "unique_actors": int(kpi_row.unique_actors or 0),
                "error_rate": float(kpi_row.error_rate or 0.0),
                "avg_duration_ms": float(kpi_row.avg_duration_ms) if kpi_row.avg_duration_ms is not None else None,
            }

            rows_result = await db.execute(
                text(f"""
                    SELECT id, action, user_id, session_id, activity_metadata, created_at
                    FROM user_activity_logs
                    WHERE {where}
                    ORDER BY created_at DESC
                    LIMIT :limit OFFSET :offset
                """),
                {**params, "limit": limit, "offset": offset},
            )
            all_rows = rows_result.fetchall()

    # ── Batch-resolve motion statuses from motion_draft_logs (Option B) ────
    # Collect session IDs for all motion-action rows, then fetch the most
    # recent status per (session_id, motion_type) in a single query.
    motion_session_ids: list[str] = [
        row.session_id
        for row in all_rows
        if row.action in _MOTION_ACTIONS and row.session_id
    ]
    motion_status_map: dict[tuple[str, str], str] = {}

    if motion_session_ids:
        async with AsyncSessionLocal() as db:
            mdl_result = await db.execute(
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

    # ── Batch-resolve actor info from user_db ──────────────────────────────
    unique_user_ids = list({row.user_id for row in all_rows if row.user_id})
    actor_map: dict[str, tuple[str | None, str | None]] = {}  # user_id → (name, email)

    if unique_user_ids:
        async with UserAsyncSessionLocal() as user_db:
            user_rows = await user_db.execute(
                text(
                    "SELECT id, first_name, last_name, email "
                    "FROM users WHERE id = ANY(:ids)"
                ),
                {"ids": unique_user_ids},
            )
            for ur in user_rows.fetchall():
                first = (ur.first_name or "").strip()
                last  = (ur.last_name  or "").strip()
                name  = f"{first} {last}".strip() if (first or last) else None
                actor_map[ur.id] = (name, ur.email)

    # ── Build enriched entries ─────────────────────────────────────────────
    entries: list[AuditLogEntry] = []
    for row in all_rows:
        meta = row.activity_metadata or {}
        e_type, e_id, e_label = _derive_entity(row.action, meta, row.session_id)
        row_status = _derive_status(row.action, meta, motion_status_map, row.session_id)

        # Python-level status filter (only active when status param is set)
        if status_filter_active and row_status != status:
            continue

        actor_name, actor_email = actor_map.get(row.user_id, (None, None)) if row.user_id else (None, None)

        raw_sc = meta.get("status_code")
        try:
            sc_int = int(raw_sc) if raw_sc is not None else None
        except (TypeError, ValueError):
            sc_int = None

        raw_dur = meta.get("duration_ms")
        try:
            dur = float(raw_dur) if raw_dur is not None else None
        except (TypeError, ValueError):
            dur = None

        entries.append(AuditLogEntry(
            id=row.id,
            occurred_at=row.created_at,
            actor=ActorInfo(
                user_id=row.user_id,
                name=actor_name,
                email=actor_email,
            ) if row.user_id else None,
            action=row.action,
            label=_ACTION_LABELS.get(row.action, row.action),
            detail=_build_activity_detail(row.action, meta),
            entity_type=e_type,
            entity_id=e_id,
            entity_label=e_label,
            status=row_status,
            duration_ms=dur,
            error_code=sc_int if sc_int is not None and sc_int >= 400 else None,
            error_message=meta.get("error_message") or None,
            metadata=_sanitize_metadata(meta) if meta else None,
            session_id=row.session_id,
        ))

    # ── Paginate (Python path only used when status filter is active) ───────
    if status_filter_active:
        total = len(entries)
        items = entries[offset: offset + limit]
        # Compute KPIs from the Python-filtered entries
        error_entries = sum(1 for e in entries if e.error_code is not None)
        dur_values = [e.duration_ms for e in entries if e.duration_ms is not None]
        unique_actor_ids = {e.actor.user_id for e in entries if e.actor}
        kpi = ActivityLogKPI(
            total_events=total,
            unique_actors=len(unique_actor_ids),
            error_rate=round(error_entries * 100.0 / total, 2) if total else 0.0,
            avg_duration_ms=round(sum(dur_values) / len(dur_values), 1) if dur_values else None,
        )
    else:
        total = total_sql
        items = entries
        kpi = ActivityLogKPI(**sql_kpi)

    return AuditLogResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        filters=AuditLogFiltersApplied(
            date_range=DateRangeInfo(preset=dr.range, start=dr.start, end=dr.end),
            actor_id=actor_id,
            actions=effective_actions,
            entity_type=entity_type,
            entity_id=entity_id,
            status=status,
            search=search,
        ),
        kpi=kpi,
    )
