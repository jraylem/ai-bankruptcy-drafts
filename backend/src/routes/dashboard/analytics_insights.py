"""
Analytics sub-page: AI Insights.

GET /analytics/insights → /api/dashboard/analytics/insights

Aggregates dashboard metrics for the selected date range, computes
period-over-period changes vs the prior period of equal length, then
calls Claude to generate natural-language insights and suggested actions.

Caching: module-level TTL dict (5 min) keyed by (start_iso, end_iso).
Claude is called once per unique period; subsequent requests within TTL
return cached data instantly.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import anthropic
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text

from ...ai_models import CLAUDE_MODEL_STANDARD, CLAUDE_TEMPERATURE
from ...auth.database import UserAsyncSessionLocal
from ...auth.models import User
from ...common.dependencies import get_current_firm_user
from ...chatbot.database import AsyncSessionLocal
from ...config import settings
from ._shared import DateRangeInfo, DateRangeParams, _BASE_CTE, _MOTION_DISPLAY_NAMES

# Motion vs order classification — mirrors analytics_motions.py
_ORDER_KEYS: list[str] = [
    k for k in _MOTION_DISPLAY_NAMES
    if k.startswith("order-") or k == "objection-sustain"
]

logger = logging.getLogger(__name__)
router = APIRouter(tags=["analytics"])

# ---------------------------------------------------------------------------
# Module-level TTL cache — avoids repeated Claude calls for the same period
# ---------------------------------------------------------------------------

_CACHE_TTL = 300  # seconds (5 min)
_cache: dict[tuple[str, str], tuple[dict, float]] = {}
_metrics_cache: dict[tuple[str, str], tuple[dict, float]] = {}  # raw metrics for explain endpoint


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class InsightItem(BaseModel):
    type: str   # trend | chart | pie | users | target
    text: str


class PoPMetric(BaseModel):
    pct: Optional[float]       # absolute % change (always positive)
    direction: str             # "up" | "down" | "flat"


class PeriodOverPeriod(BaseModel):
    current_label: str
    prior_label: str
    total_cases: PoPMetric
    motions_drafted: PoPMetric   # motions only (excludes orders)
    orders_drafted: PoPMetric    # orders only
    active_cases: PoPMetric
    new_users: PoPMetric


class InsightsResponse(BaseModel):
    summary_title: str
    insights: list[InsightItem]
    period_over_period: PeriodOverPeriod
    suggested_actions: list[str]
    date_range: DateRangeInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pop_metric(current: int, prior: int) -> PoPMetric:
    """
    Compute period-over-period % change with direction.

    Edge cases:
      prior=0, current=0  → flat (no activity in either period)
      prior=0, current>0  → up, pct=None (new activity, no baseline to divide by)
      prior>0, current=0  → down 100%
      prior>0, current>0  → normal % change
    """
    if prior == 0 and current == 0:
        return PoPMetric(pct=None, direction="flat")
    if prior == 0 and current > 0:
        return PoPMetric(pct=None, direction="up")
    if prior > 0 and current == 0:
        return PoPMetric(pct=100.0, direction="down")
    pct = round((current - prior) / prior * 100, 1)
    direction = "up" if pct > 0 else ("down" if pct < 0 else "flat")
    return PoPMetric(pct=abs(pct), direction=direction)


def _fmt_date(dt: datetime) -> str:
    """Cross-platform short date label, e.g. 'Apr 1'."""
    return dt.strftime("%b") + " " + str(dt.day)


def _fmt_label(start: datetime, end: datetime) -> str:
    return f"{_fmt_date(start)} – {_fmt_date(end)}"


def _summary_title(dr: DateRangeParams) -> str:
    if dr.range == "today":
        return "Trend summary for today"
    if dr.range == "7d":
        return "Trend summary for the last 7 days"
    if dr.range == "30d":
        return "Trend summary for the last 30 days"
    # custom
    return f"Trend summary for {_fmt_date(dr.start)} – {_fmt_date(dr.end)}"


# ---------------------------------------------------------------------------
# SQL helper — fetch all aggregate metrics for a given [start, end]
# ---------------------------------------------------------------------------

async def _fetch_metrics(start: datetime, end: datetime) -> dict:
    """
    Called by: get_analytics_insights → asyncio.gather (current + prior periods)
    """
    params = {"start": start, "end": end}

    async with AsyncSessionLocal() as db:

        # Cases: total, active bucket, archived petition_status
        case_row = (await db.execute(
            text(f"""
                {_BASE_CTE}
                SELECT
                    COUNT(*)                                              AS total,
                    COUNT(*) FILTER (WHERE bucket = 'active')            AS active_count,
                    COUNT(*) FILTER (WHERE petition_status = 'archived') AS archived_count
                FROM session_bucket
            """),
            params,
        )).fetchone()

        total_cases    = int(case_row.total)          if case_row else 0
        active_cases   = int(case_row.active_count)   if case_row else 0
        archived_count = int(case_row.archived_count) if case_row else 0
        archived_pct   = round(archived_count / total_cases * 100, 1) if total_cases else 0.0

        # Motions and orders — count per motion_type (all statuses, created_at window).
        # Split into motions vs orders in Python — mirrors analytics_motions.py pattern
        # to avoid asyncpg issues with ANY()/ALL() array parameters.
        type_rows = (await db.execute(
            text("""
                SELECT motion_type, COUNT(*) AS cnt
                FROM motion_draft_logs
                WHERE created_at >= :start AND created_at <= :end
                GROUP BY motion_type
            """),
            params,
        )).fetchall()
        _order_set = set(_ORDER_KEYS)
        motions_attempted = sum(int(r.cnt) for r in type_rows if r.motion_type not in _order_set)
        orders_attempted  = sum(int(r.cnt) for r in type_rows if r.motion_type in _order_set)

        # Query A — daily motion breakdown (all statuses)
        daily_rows = (await db.execute(
            text("""
                SELECT DATE_TRUNC('day', created_at) AS day, COUNT(*) AS cnt
                FROM motion_draft_logs
                WHERE created_at >= :start AND created_at <= :end
                GROUP BY DATE_TRUNC('day', created_at)
                ORDER BY day ASC
            """),
            params,
        )).fetchall()
        daily_breakdown = [
            {"day": _fmt_date(r.day), "count": int(r.cnt)}
            for r in daily_rows if r.day
        ]

        # Query B — status breakdown split into motions vs orders
        status_rows = (await db.execute(
            text("""
                SELECT motion_type, status, COUNT(*) AS cnt
                FROM motion_draft_logs
                WHERE created_at >= :start AND created_at <= :end
                GROUP BY motion_type, status
            """),
            params,
        )).fetchall()
        motion_status: dict[str, int] = {}
        order_status: dict[str, int] = {}
        for r in status_rows:
            bucket = order_status if r.motion_type in _order_set else motion_status
            bucket[r.status] = bucket.get(r.status, 0) + int(r.cnt)

        # Query C — top 5 motion types by volume (reuses type_rows, no new query)
        top_motion_types = sorted(
            [
                {
                    "motion_type":  r.motion_type,
                    "display_name": _MOTION_DISPLAY_NAMES.get(r.motion_type, r.motion_type),
                    "count":        int(r.cnt),
                }
                for r in type_rows
                if r.motion_type not in _order_set
            ],
            key=lambda x: x["count"],
            reverse=True,
        )[:5]

        # Query D — top 3 sessions by motion count
        session_rows = (await db.execute(
            text("""
                SELECT session_id, COUNT(*) AS cnt
                FROM motion_draft_logs
                WHERE created_at >= :start AND created_at <= :end
                GROUP BY session_id
                ORDER BY cnt DESC
                LIMIT 3
            """),
            params,
        )).fetchall()
        top_sessions_by_motions = [
            {"session_id": str(r.session_id), "count": int(r.cnt)}
            for r in session_rows
        ]

        # Peak motions day — single highest day by completed count
        peak_row = (await db.execute(
            text("""
                SELECT DATE_TRUNC('day', created_at) AS day, COUNT(*) AS cnt
                FROM motion_draft_logs
                WHERE created_at >= :start AND created_at <= :end
                  AND status = 'completed'
                GROUP BY DATE_TRUNC('day', created_at)
                ORDER BY cnt DESC
                LIMIT 1
            """),
            params,
        )).fetchone()
        peak_day   = (_fmt_date(peak_row.day)) if peak_row and peak_row.day else None
        peak_count = int(peak_row.cnt)          if peak_row else 0

        # Most active district by completed motions (LATERAL join to latest chat_thread)
        district_row = (await db.execute(
            text("""
                SELECT COALESCE(ct.district, 'other') AS district, COUNT(*) AS cnt
                FROM motion_draft_logs m
                INNER JOIN sessions s ON s.id = m.session_id
                LEFT JOIN LATERAL (
                    SELECT district FROM chat_threads
                    WHERE session_id = s.id ORDER BY created_at DESC LIMIT 1
                ) ct ON true
                WHERE m.created_at >= :start AND m.created_at <= :end
                  AND m.status = 'completed'
                GROUP BY COALESCE(ct.district, 'other')
                ORDER BY cnt DESC
                LIMIT 1
            """),
            params,
        )).fetchone()
        most_active_district = district_row.district.upper() if district_row else None

        # Primary intake source (latest pdf_document per session, then aggregate)
        source_row = (await db.execute(
            text("""
                SELECT pd.source, COUNT(*) AS cnt
                FROM sessions s
                INNER JOIN LATERAL (
                    SELECT source FROM pdf_documents
                    WHERE session_id = s.id ORDER BY uploaded_at DESC LIMIT 1
                ) pd ON true
                WHERE s.created_at >= :start AND s.created_at <= :end
                GROUP BY pd.source
                ORDER BY cnt DESC
                LIMIT 1
            """),
            params,
        )).fetchone()
        primary_source = source_row.source.capitalize() if source_row and source_row.source else None

        # Active users — distinct users who drafted at least one motion in range
        active_users_row = (await db.execute(
            text("""
                SELECT COUNT(DISTINCT s.user_id) AS active_user_count
                FROM motion_draft_logs m
                INNER JOIN sessions s ON s.id = m.session_id
                WHERE m.created_at >= :start AND m.created_at <= :end
            """),
            params,
        )).fetchone()
        active_user_count = int(active_users_row.active_user_count) if active_users_row else 0

    # New users in range + total users — user_db
    async with UserAsyncSessionLocal() as user_db:
        new_users_row = (await user_db.execute(
            text("""
                SELECT COUNT(*) AS cnt FROM users
                WHERE created_at >= :start AND created_at <= :end
            """),
            params,
        )).fetchone()
        new_users = int(new_users_row.cnt) if new_users_row else 0

        total_users_row = (await user_db.execute(
            text("SELECT COUNT(*) AS cnt FROM users"),
        )).fetchone()
        total_users = int(total_users_row.cnt) if total_users_row else 0

    return {
        "total_cases":            total_cases,
        "active_cases":           active_cases,
        "archived_pct":           archived_pct,
        "motions_attempted":      motions_attempted,
        "orders_attempted":       orders_attempted,
        "peak_day":               peak_day,
        "peak_count":             peak_count,
        "most_active_district":   most_active_district,
        "primary_source":         primary_source,
        "active_user_count":      active_user_count,
        "new_users":              new_users,
        "total_users":            total_users,
        "daily_breakdown":        daily_breakdown,
        "motion_status":          motion_status,
        "order_status":           order_status,
        "top_motion_types":       top_motion_types,
        "top_sessions_by_motions": top_sessions_by_motions,
    }


# ---------------------------------------------------------------------------
# Claude call — direct AsyncAnthropic, no LangGraph, no tools
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an analytics assistant for a bankruptcy legal drafting platform.
You will receive a JSON summary of dashboard metrics for a specific time period.

Return ONLY a JSON object with exactly this structure — no other text, no markdown:

{
  "insights": [
    {"type": "trend",  "text": "..."},
    {"type": "chart",  "text": "..."},
    {"type": "pie",    "text": "..."},
    {"type": "users",  "text": "..."},
    {"type": "target", "text": "..."}
  ],
  "suggested_actions": ["...", "..."]
}

Rules:
- Exactly 5 insights, one per type, in the order shown above.
- Each insight: one concise sentence, maximum 20 words.
- Between 3 and 5 suggested actions. The exact number and content must be driven by
  the actual trends in the data — do not reuse the same actions every time.
  Examples of action types to draw from (pick the most relevant given the metrics):
    "Explain the spike", "Review failed motions", "Investigate drop in active cases",
    "Follow up on pending cases", "Check district activity", "Audit archived cases",
    "Review user inactivity", "Analyze top motion types", "Monitor processing times".
  Generate actions that are specific to what the data shows, not generic placeholders.
- Each suggested action: short noun phrase or imperative, maximum 6 words.
- Use only the metric values provided — do not invent numbers.
- If a metric is null or 0, derive the insight from available data instead.
- Return valid JSON only. No explanation, no extra keys.
"""


def _extract_json(raw: str) -> dict:
    """
    Robustly extract a JSON object from Claude's response.
    Handles cases where Claude wraps output in markdown code fences.
    """
    # Strip markdown code fences if present (```json ... ``` or ``` ... ```)
    stripped = raw.strip()
    if stripped.startswith("```"):
        # Remove opening fence (e.g. ```json\n or ```\n)
        stripped = stripped.split("\n", 1)[-1]
        # Remove closing fence
        if stripped.endswith("```"):
            stripped = stripped[: stripped.rfind("```")]
        stripped = stripped.strip()

    # Try direct parse first
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # Fallback: find the outermost { ... } in the original raw string
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No JSON object found in Claude response: {raw[:200]!r}")
    return json.loads(raw[start : end + 1])


_EXPLAIN_SYSTEM_PROMPT = """\
You are an analytics assistant for a bankruptcy legal drafting platform.
You will receive a JSON summary of dashboard metrics and a specific action
the user wants to investigate. Provide a clear, data-grounded explanation
in 3 sentences or fewer. Use only the numbers in the data — do not speculate or
invent figures. Write in plain English, no markdown formatting.
Never use the word "attorney" — refer to people as "user" or "users" instead.
"""


async def _call_claude(metrics: dict, period_label: str) -> tuple[list[InsightItem], list[str]]:
    """
    Called by: get_analytics_insights
    Sends metric summary to Claude and parses structured JSON response.
    """
    payload = {**metrics, "period": period_label}
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    response = await client.messages.create(
        model=CLAUDE_MODEL_STANDARD,
        max_tokens=512,
        temperature=CLAUDE_TEMPERATURE,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": json.dumps(payload, default=str)}],
    )

    raw = next((b.text for b in response.content if b.type == "text"), None)
    if not raw:
        raise ValueError("Claude returned no text block")

    logger.debug("Claude insights raw response: %s", raw[:500])
    parsed = _extract_json(raw)

    insights = [
        InsightItem(type=item["type"], text=item["text"])
        for item in parsed.get("insights", [])
    ]
    suggested_actions: list[str] = parsed.get("suggested_actions", [])
    return insights, suggested_actions


# ---------------------------------------------------------------------------
# GET /insights/explain  (must be registered BEFORE /insights)
# ---------------------------------------------------------------------------

@router.get("/insights/explain")
async def explain_insight_action(
    action: str = Query(..., min_length=1, max_length=200),
    dr: DateRangeParams = Depends(),
    _user: User = Depends(get_current_firm_user),
):
    """
    Streams a Claude explanation for a clicked suggested action.

    Reuses cached metrics from _metrics_cache (populated by /insights).
    Falls back to _fetch_metrics on cache miss or expiry.

    Called by: frontend AI Insights panel — suggested action chip click
    """
    cache_key = (dr.start.isoformat(), dr.end.isoformat())
    now = time.monotonic()

    if cache_key in _metrics_cache:
        cached_metrics, cached_at = _metrics_cache[cache_key]
        if now - cached_at < _CACHE_TTL:
            metrics = cached_metrics
        else:
            metrics = await _fetch_metrics(dr.start, dr.end)
            _metrics_cache[cache_key] = (metrics, now)
    else:
        metrics = await _fetch_metrics(dr.start, dr.end)
        _metrics_cache[cache_key] = (metrics, now)

    period_label = _summary_title(dr)
    user_message = (
        f"Action: {action}\n\n"
        f"Dashboard data ({period_label}):\n"
        f"{json.dumps(metrics, default=str)}"
    )

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = await client.messages.create(
        model=CLAUDE_MODEL_STANDARD,
        max_tokens=400,
        temperature=CLAUDE_TEMPERATURE,
        system=_EXPLAIN_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    text = next((b.text for b in response.content if b.type == "text"), "")
    return {"explanation": text}


# ---------------------------------------------------------------------------
# GET /insights
# ---------------------------------------------------------------------------

@router.get("/insights", response_model=InsightsResponse)
async def get_analytics_insights(
    dr: DateRangeParams = Depends(),
    _user: User = Depends(get_current_firm_user),
):
    """
    Returns AI-generated insights for the selected date range.

    - Collects aggregate metrics from chat_db and user_db.
    - Computes period-over-period deltas vs the prior period of equal length.
    - Calls Claude (claude-sonnet-4-6) to generate 5 bullet insights and
      2 suggested actions from the metric data.
    - Results are cached 5 minutes per (start, end) pair.

    Called by: frontend dashboard AI Insights panel
    """
    cache_key = (dr.start.isoformat(), dr.end.isoformat())
    now = time.monotonic()
    if cache_key in _cache:
        cached_payload, cached_at = _cache[cache_key]
        if now - cached_at < _CACHE_TTL:
            return InsightsResponse(**cached_payload)

    # Prior period — same duration as current, shifted back
    duration    = dr.end - dr.start
    prior_end   = dr.start
    prior_start = dr.start - duration

    # Fetch current + prior period metrics concurrently
    current_metrics, prior_metrics = await asyncio.gather(
        _fetch_metrics(dr.start, dr.end),
        _fetch_metrics(prior_start, prior_end),
    )
    _metrics_cache[cache_key] = (current_metrics, now)

    # Period-over-period comparison
    pop = PeriodOverPeriod(
        current_label=_fmt_label(dr.start, dr.end),
        prior_label=_fmt_label(prior_start, prior_end),
        total_cases=_pop_metric(
            current_metrics["total_cases"],
            prior_metrics["total_cases"],
        ),
        motions_drafted=_pop_metric(
            current_metrics["motions_attempted"],
            prior_metrics["motions_attempted"],
        ),
        orders_drafted=_pop_metric(
            current_metrics["orders_attempted"],
            prior_metrics["orders_attempted"],
        ),
        active_cases=_pop_metric(
            current_metrics["active_cases"],
            prior_metrics["active_cases"],
        ),
        new_users=_pop_metric(
            current_metrics["new_users"],
            prior_metrics["new_users"],
        ),
    )

    # Claude insights
    title = _summary_title(dr)
    try:
        insights, suggested_actions = await _call_claude(current_metrics, title)
    except Exception as exc:
        logger.error("AI insights Claude call failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail=f"AI insights Claude call failed: {exc}",
        )

    response = InsightsResponse(
        summary_title=title,
        insights=insights,
        period_over_period=pop,
        suggested_actions=suggested_actions,
        date_range=DateRangeInfo(preset=dr.range, start=dr.start, end=dr.end),
    )

    _cache[cache_key] = (response.model_dump(), now)
    return response


# ---------------------------------------------------------------------------
# Dashboard Chat — POST /insights/chat  /  DELETE /insights/chat
# ---------------------------------------------------------------------------

_MAX_HISTORY_MSGS = 20    # cap: 10 exchanges = 20 messages

_CHAT_SYSTEM_PROMPT = """\
You are a dashboard assistant for a bankruptcy legal drafting platform.
Below is a snapshot of the current dashboard data (last 30 days), including a
"today" section with live counters refreshed every minute:
{snapshot_json}

## Snapshot key guide

Each top-level key in the snapshot covers a specific topic:
- motion_metrics — API call counts and processing trends (last 30 days)
- cases_kpi — case totals by status (LIFETIME data, no date filter; use search_cases for date-scoped counts)
- motions_kpi — motion draft counts, success rate, avg processing time (last 30 days)
- motions_kpi_enriched — per-district and per-type motion breakdown (last 30 days);
  motions_kpi_enriched.by_district shape: {{"flnb": {{"total_attempted": N, "completed": N}}, ...}}
- users_kpi — active user and login totals (last 30 days)
- cases_daily — daily new-case counts array for the last 30 days
- motions_daily — daily motion-started counts array for the last 30 days
- motions_by_type — motion draft counts grouped by motion_type (last 30 days)
- users_daily — daily active-user counts array for the last 30 days
- today — live counters refreshed every 60 s:
    date: ISO date string (YYYY-MM-DD)
    activity_by_action: dict of {{action_name: count}} for today (e.g. {{"upload_pdf": 5, "login": 12}})
    total_activities: sum of all activity events today
    motions_by_status: dict of {{status: count}} for motions started today (e.g. {{"completed": 3, "pending": 1}})
    total_motions: total motion drafts started today
    cases_opened: number of new cases opened today

For motion daily trends prefer motions_daily over motion_metrics.daily_breakdown —
both contain daily motion counts but motions_daily aligns with the cases_daily/users_daily time series format.

## Answering rules

### Clarify before acting
- If the question is genuinely ambiguous (e.g. "show me activity" — which type? which range?),
  ask ONE short clarifying question before calling any tools. Do not ask multiple questions at once.
- If the question is clear enough to answer, proceed directly — do not ask for confirmation.

### Context handling
- Treat each message on its own topic FIRST. Only use conversation history if the current
  message contains a clear reference to it (e.g. "those motions", "that user", "what you
  just said"). Otherwise answer the question completely fresh, as if it is the first message.
- Do NOT pull in data from previous answers when the current question is on a different topic.

### Topic focus
- Answer ONLY what the question is about. Do not volunteer unrelated metrics.
  - Question about users/access → surface only user, login, and activity data.
  - Question about motions → surface only motion and drafting data.
  - Question about cases → surface only case and petition data.
  - If the question is broad (e.g. "summarize the dashboard"), then cover all areas.
- For questions about today specifically, use the "today" section in the snapshot first
  before calling a tool.

### Tool use
- Call ALL tools needed to fully answer the question before composing your reply.
- Row-level tools (search_cases, search_motions, search_users, get_activity_log) return
  "total_count" (the real total matching the filters) and "returned" (rows in this page).
  Always report total_count to the user, not just the number of rows shown.
  get_summary_stats, get_case_detail, and get_user_detail do NOT have total_count/returned.
- get_summary_stats returns: {{dataset, group_by, total, groups: [{{value, count}}]}}.
  Report the top groups and the overall total — do not treat it like a row-level result.
- If a tool returns 0 results, try once more with a broader query (e.g. remove a filter,
  widen the date range) before concluding there is no data.
- Tool queries default to the last 30 days — pass start_date and end_date only when
  the user asks for a specific range (e.g. "last 90 days", "all time", "January 2025").
  For all-time data use start_date="2020-01-01" and omit end_date.
- Use get_summary_stats when the user asks for counts grouped by a dimension
  (e.g. "how many API calls by type", "break down motions by status", "top districts").

### Format
- Be as detailed as the question requires. Use clear sections when covering multiple aspects.
  Do not cut off — answer completely.
- Answer ONLY the current question. Never re-answer or expand on questions from earlier
  in the conversation that you think were incomplete — if the user wants more, they will ask.
- Do not invent or speculate on numbers not present in the data or tool results.
- Never use the word "attorney" — refer to people as "user" or "users".
- Write in plain English. No markdown bold/italic/headers — use plain text section labels.\
"""

_CHAT_TOOLS = [
    {
        "name": "search_cases",
        "description": (
            "Search cases filtered by status, district, source, or keyword. "
            "Returns total_count (real total) and up to 50 rows. "
            "Defaults to the last 30 days — pass start_date/end_date for other ranges."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "status":     {"type": "string", "enum": ["active", "pending", "inactive"]},
                "district":   {"type": "string", "enum": ["flnb", "flmb", "flsb", "pawb", "other"]},
                "source":     {"type": "string", "enum": ["manual", "ecf", "gdrive", "courtdrive"]},
                "search":     {"type": "string", "description": "Substring match on case_number or debtor_name"},
                "sort_by":    {"type": "string", "enum": ["created_at", "motions_count", "last_activity_at"], "default": "created_at"},
                "limit":      {"type": "integer", "default": 10, "maximum": 50},
                "start_date": {"type": "string", "description": "Filter start date YYYY-MM-DD. Omit for last 30 days."},
                "end_date":   {"type": "string", "description": "Filter end date YYYY-MM-DD. Omit for today."},
            },
        },
    },
    {
        "name": "search_motions",
        "description": (
            "Search motion draft logs. Use when the user asks about specific motions, "
            "failed drafts, a particular motion type, or orders vs motions. "
            "Returns total_count (real total) and up to 50 rows. "
            "Defaults to the last 30 days — pass start_date/end_date for other ranges."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "status":      {"type": "string", "enum": ["completed", "pending", "failed", "cancelled"]},
                "category":    {"type": "string", "enum": ["motion", "order"]},
                "motion_type": {"type": "string", "description": "e.g. 'extend', 'modify', 'order-extend'"},
                "cos_type":    {"type": "string", "enum": ["WithNoticeOfHearing", "WithoutNoticeOfHearing", "No"]},
                "district":    {"type": "string", "enum": ["flnb", "flmb", "flsb", "pawb", "other"]},
                "search":      {"type": "string", "description": "Substring match on case_number or debtor_name"},
                "sort_by":     {"type": "string", "enum": ["created_at", "processing_seconds"], "default": "created_at"},
                "limit":       {"type": "integer", "default": 10, "maximum": 50},
                "start_date":  {"type": "string", "description": "Filter start date YYYY-MM-DD. Omit for last 30 days."},
                "end_date":    {"type": "string", "description": "Filter end date YYYY-MM-DD. Omit for today."},
            },
        },
    },
    {
        "name": "search_users",
        "description": (
            "Search users by name or email. Returns total_count and activity counts per user. "
            "Defaults to the last 30 days — pass start_date/end_date for other ranges."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "search":     {"type": "string", "description": "Substring match on name or email"},
                "sort_by":    {"type": "string", "enum": ["last_active", "cases_count", "motions_drafted", "created_at"], "default": "last_active"},
                "limit":      {"type": "integer", "default": 10, "maximum": 50},
                "start_date": {"type": "string", "description": "Filter start date YYYY-MM-DD. Omit for last 30 days."},
                "end_date":   {"type": "string", "description": "Filter end date YYYY-MM-DD. Omit for today."},
            },
        },
    },
    {
        "name": "get_activity_log",
        "description": (
            "Fetch activity log entries. Returns total_count (real total) and up to 50 rows. "
            "Use when the user asks what happened, who did something, or wants an audit trail. "
            "Defaults to the last 30 days — pass start_date/end_date for other ranges."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action":     {"type": "string"},
                "actor_id":   {"type": "string", "description": "Filter by a specific user ID"},
                "entity_id":  {"type": "string", "description": "Filter by case number or session_id"},
                "search":     {"type": "string"},
                "limit":      {"type": "integer", "default": 10, "maximum": 50},
                "start_date": {"type": "string", "description": "Filter start date YYYY-MM-DD. Omit for last 30 days."},
                "end_date":   {"type": "string", "description": "Filter end date YYYY-MM-DD. Omit for today."},
            },
        },
    },
    {
        "name": "get_summary_stats",
        "description": (
            "Get aggregated counts grouped by a dimension. Use for questions like "
            "'how many API calls by type', 'break down motions by status', 'top districts', "
            "'what actions happened today'. Much faster than row-level tools for totals. "
            "Returns: {dataset, group_by, total, groups: [{value, count}]} — "
            "report the groups and the overall total, NOT total_count/returned."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dataset":  {
                    "type": "string",
                    "enum": ["activity", "motions", "cases"],
                    "description": "Which dataset to aggregate.",
                },
                "group_by": {
                    "type": "string",
                    "description": (
                        "Dimension to group by. "
                        "activity: action | district (via session join). "
                        "motions: motion_type | status | district | cos_type | category. "
                        "cases: district | source | petition_status."
                    ),
                },
                "start_date":     {"type": "string", "description": "Filter start YYYY-MM-DD. Omit for last 30 days."},
                "end_date":       {"type": "string", "description": "Filter end YYYY-MM-DD. Omit for today."},
                "filter_action":  {"type": "string", "description": "activity only: filter to a specific action value."},
                "filter_status":  {"type": "string", "description": "motions only: filter to a specific status value."},
                "filter_district":{"type": "string", "description": "motions/cases only: filter to a specific district."},
            },
            "required": ["dataset", "group_by"],
        },
    },
    {
        "name": "get_case_detail",
        "description": (
            "Get full detail for a single case: metadata, documents, last 10 motions, "
            "and last 10 timeline events. "
            "Use when the user references a specific case number or session."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "UUID of the session"},
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "get_user_detail",
        "description": (
            "Get full detail for a single user: KPI summary (logins, active days, sessions created, "
            "motions started/completed, draft success rate, avg draft time, documents exported), "
            "daily activity trend, top motion types, last 5 sessions, and last 10 activity events. "
            "Note: recent_sessions (last 5) and recent_activity (last 10) are NOT date-filtered — "
            "they always reflect the user's most recent records regardless of start_date/end_date. "
            "Use when the user asks about a specific person by name, email, or ID. "
            "Call search_users first if you only have a name or email and need the user_id."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id":    {"type": "string", "description": "UUID of the user"},
                "start_date": {"type": "string", "description": "Filter start date YYYY-MM-DD. Omit for last 30 days."},
                "end_date":   {"type": "string", "description": "Filter end date YYYY-MM-DD. Omit for today."},
            },
            "required": ["user_id"],
        },
    },
]


async def _run_summary_stats(
    dataset: str,
    group_by: str,
    start: datetime,
    end: datetime,
    filter_action: Optional[str] = None,
    filter_status: Optional[str] = None,
    filter_district: Optional[str] = None,
) -> dict:
    """
    Called by: _execute_chat_tool
    Returns grouped counts for the requested dataset+dimension.
    """
    params: dict = {"start": start, "end": end}
    filters: list[str] = []

    async with AsyncSessionLocal() as db:
        if dataset == "activity":
            filters = ["created_at >= :start", "created_at <= :end"]
            if filter_action:
                filters.append("action = :filter_action")
                params["filter_action"] = filter_action
            if group_by == "action":
                col = "action"
            else:
                # district requires joining to sessions → chat_threads
                col = "COALESCE(ct.district, 'other')"
            if group_by == "district":
                sql = f"""
                    SELECT {col} AS grp, COUNT(*) AS cnt
                    FROM user_activity_logs al
                    LEFT JOIN sessions s ON s.id = al.session_id
                    LEFT JOIN LATERAL (
                        SELECT district FROM chat_threads
                        WHERE session_id = s.id ORDER BY created_at DESC LIMIT 1
                    ) ct ON true
                    WHERE {' AND '.join(filters)}
                    GROUP BY grp ORDER BY cnt DESC
                """
            else:
                sql = f"""
                    SELECT {col} AS grp, COUNT(*) AS cnt
                    FROM user_activity_logs
                    WHERE {' AND '.join(filters)}
                    GROUP BY grp ORDER BY cnt DESC
                """
            rows = (await db.execute(text(sql), params)).fetchall()

        elif dataset == "motions":
            # Use the same base table as the dashboard KPI (_fetch_motions_kpi):
            # query motion_draft_logs directly without joining sessions so that
            # orphaned motion rows (whose session was deleted) are still counted.
            # Only join sessions + chat_threads when district is needed.
            needs_district = group_by == "district" or bool(filter_district)
            if needs_district:
                filters = ["m.created_at >= :start", "m.created_at <= :end"]
            else:
                filters = ["created_at >= :start", "created_at <= :end"]
            if filter_status:
                col_prefix = "m." if needs_district else ""
                filters.append(f"{col_prefix}status = :filter_status")
                params["filter_status"] = filter_status
            if filter_district:
                filters.append("ct.district = :filter_district")
                params["filter_district"] = filter_district
            col_map = {
                "motion_type": "motion_type",
                "status":      "status",
                "cos_type":    "cos_type",
                "district":    "COALESCE(ct.district, 'other')",
                "category":    (
                    "CASE WHEN motion_type = ANY(:order_keys) "
                    "THEN 'order' ELSE 'motion' END"
                ),
            }
            col = col_map.get(group_by, "motion_type")
            if group_by == "category":
                params["order_keys"] = list(_ORDER_KEYS)

            if needs_district:
                sql = f"""
                    SELECT {col_map.get(group_by, 'm.motion_type')} AS grp, COUNT(*) AS cnt
                    FROM motion_draft_logs m
                    INNER JOIN sessions s ON s.id = m.session_id
                    LEFT JOIN LATERAL (
                        SELECT district FROM chat_threads
                        WHERE session_id = s.id ORDER BY created_at DESC LIMIT 1
                    ) ct ON true
                    WHERE {' AND '.join(filters)}
                    GROUP BY grp ORDER BY cnt DESC
                """
            else:
                sql = f"""
                    SELECT {col} AS grp, COUNT(*) AS cnt
                    FROM motion_draft_logs
                    WHERE {' AND '.join(filters)}
                    GROUP BY grp ORDER BY cnt DESC
                """
            rows = (await db.execute(text(sql), params)).fetchall()

        elif dataset == "cases":
            from ._shared import _BASE_CTE
            col_map = {
                "district":        "cm.district",
                "source":          "cs.source",
                "petition_status": "sb.petition_status",
            }
            col = col_map.get(group_by, "sb.petition_status")
            extra_joins = ""
            if group_by == "district":
                extra_joins = """
                    LEFT JOIN (
                        SELECT DISTINCT ON (session_id) session_id, district
                        FROM chat_threads ORDER BY session_id, created_at DESC
                    ) cm ON cm.session_id = sb.session_id
                """
                col = "COALESCE(cm.district, 'other')"
            elif group_by == "source":
                extra_joins = """
                    LEFT JOIN (
                        SELECT DISTINCT ON (session_id) session_id, source
                        FROM pdf_documents ORDER BY session_id, uploaded_at DESC
                    ) cs ON cs.session_id = sb.session_id
                """
            sql = f"""
                {_BASE_CTE}
                SELECT {col} AS grp, COUNT(*) AS cnt
                FROM session_bucket sb
                {extra_joins}
                WHERE sb.bucket != 'other'
                GROUP BY grp ORDER BY cnt DESC
            """
            rows = (await db.execute(text(sql), params)).fetchall()

        else:
            return {"error": f"Unknown dataset: {dataset}"}

    groups = [{"value": str(r.grp) if r.grp else "unknown", "count": int(r.cnt)} for r in rows]
    return {
        "dataset":   dataset,
        "group_by":  group_by,
        "total":     sum(g["count"] for g in groups),
        "groups":    groups,
    }


async def _execute_chat_tool(name: str, inputs: dict) -> list | dict:
    """
    Called by: dashboard_chat, dashboard_chat_stream (analytics_insights.py)
    Dispatches Claude tool_use blocks to the appropriate internal query function.
    Date range defaults to last 30 days; Claude passes start_date/end_date when
    the user asks for a specific range (e.g. "last 90 days", "all time").
    Errors are returned as {"error": "..."} so Claude can respond gracefully.
    """
    from .analytics_cases import _query_cases_list, _query_case_detail
    from .analytics_motions import _query_motions_list
    from .analytics_users import _query_users_list
    from .analytics_users_detail import _query_user_detail
    from .activity_log import _query_activity_log

    # Make a mutable copy so we can pop date keys before forwarding to query functions
    inputs = dict(inputs)

    now = datetime.now(timezone.utc)
    start_str = inputs.pop("start_date", None)
    end_str   = inputs.pop("end_date", None)

    if start_str:
        start_parsed = datetime.fromisoformat(start_str)
        start = start_parsed.replace(tzinfo=timezone.utc)
    else:
        start = now - timedelta(days=30)

    if end_str:
        end_parsed = datetime.fromisoformat(end_str)
        # Date-only string (no "T" or " " separator) → use end-of-day 23:59:59
        # to be inclusive, matching DateRangeParams behaviour for custom ranges.
        if "T" not in end_str and " " not in end_str:
            end_parsed = end_parsed.replace(hour=23, minute=59, second=59)
        end = end_parsed.replace(tzinfo=timezone.utc)
    else:
        end = now

    if name == "search_cases":
        return await _query_cases_list(start, end, **inputs)
    if name == "search_motions":
        return await _query_motions_list(start, end, **inputs)
    if name == "search_users":
        return await _query_users_list(start, end, **inputs)
    if name == "get_activity_log":
        return await _query_activity_log(start, end, **inputs)
    if name == "get_summary_stats":
        return await _run_summary_stats(start=start, end=end, **inputs)
    if name == "get_case_detail":
        return await _query_case_detail(**inputs)
    if name == "get_user_detail":
        return await _query_user_detail(start=start, end=end, **inputs)
    return {"error": f"Unknown tool: {name}"}


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


class ChatHistoryMessage(BaseModel):
    role: str
    content: str


class ChatHistoryResponse(BaseModel):
    messages: list[ChatHistoryMessage]


# ---------------------------------------------------------------------------
# DB helpers — replace in-memory _chat_history dict
# ---------------------------------------------------------------------------

async def _load_chat_history(user_id: str, range_key: str, limit: int = 20) -> list[dict]:
    """
    Called by: dashboard_chat, get_chat_history
    Fetches the last `limit` messages from DB, returned oldest-first
    (correct order for the Claude messages array).
    """
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            text("""
                SELECT role, content FROM dashboard_chat_messages
                WHERE user_id = :uid AND range_key = :rk
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            {"uid": user_id, "rk": range_key, "limit": limit},
        )).fetchall()
    return [{"role": r.role, "content": r.content} for r in reversed(rows)]


_MAX_STORED_MSGS = 40   # 2× the Claude context cap — older rows are never read

async def _append_chat_messages(
    user_id: str, user_email: str, range_key: str, messages: list[dict]
) -> None:
    """
    Called by: dashboard_chat
    Persists a list of {role, content} dicts to the DB, then prunes any rows
    beyond _MAX_STORED_MSGS for this user+range so the table stays bounded.
    Pruning is scoped strictly to (user_id, range_key) — other users are untouched.
    user_email is stored as a denormalised field for auditability —
    the auth DB is a separate connection so a JOIN is not possible.
    """
    import uuid as _uuid
    async with AsyncSessionLocal() as db:
        for msg in messages:
            await db.execute(
                text("""
                    INSERT INTO dashboard_chat_messages
                        (id, user_id, user_email, range_key, role, content)
                    VALUES (:id, :uid, :email, :rk, :role, :content)
                """),
                {
                    "id":      str(_uuid.uuid4()),
                    "uid":     user_id,
                    "email":   user_email,
                    "rk":      range_key,
                    "role":    msg["role"],
                    "content": msg["content"],
                },
            )

        # Prune rows beyond the cap for this user+range only
        await db.execute(
            text("""
                DELETE FROM dashboard_chat_messages
                WHERE user_id = :uid AND range_key = :rk
                  AND id NOT IN (
                    SELECT id FROM dashboard_chat_messages
                    WHERE user_id = :uid AND range_key = :rk
                    ORDER BY created_at DESC
                    LIMIT :keep
                  )
            """),
            {"uid": user_id, "rk": range_key, "keep": _MAX_STORED_MSGS},
        )

        await db.commit()


async def _delete_chat_history(user_id: str, range_key: str) -> None:
    """
    Called by: clear_chat_history
    Hard-deletes all messages for this user + range.
    """
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("DELETE FROM dashboard_chat_messages WHERE user_id = :uid AND range_key = :rk"),
            {"uid": user_id, "rk": range_key},
        )
        await db.commit()


# ---------------------------------------------------------------------------
# GET /insights/chat — load prior history on page open
# ---------------------------------------------------------------------------

@router.get("/insights/chat", response_model=ChatHistoryResponse)
async def get_chat_history(
    user: User = Depends(get_current_firm_user),
):
    """
    Returns prior chat messages for this user.
    Chat history is no longer scoped to a date range — one history per user.
    Called by: frontend dashboard AI chat panel on mount.
    """
    messages = await _load_chat_history(str(user.id), "all", limit=_MAX_HISTORY_MSGS)
    return ChatHistoryResponse(messages=[ChatHistoryMessage(**m) for m in messages])


@router.delete("/insights/chat")
async def clear_chat_history(
    user: User = Depends(get_current_firm_user),
):
    """
    Deletes persisted chat history for the current user.
    Called by: frontend dashboard AI chat panel (clear button)
    """
    await _delete_chat_history(str(user.id), "all")
    return {"cleared": True}


@router.post("/insights/chat", response_model=ChatResponse)
async def dashboard_chat(
    body: ChatRequest,
    user: User = Depends(get_current_firm_user),
):
    """
    Freeform chat about dashboard data.

    - Injects a last-30-day KPI + chart snapshot into the system prompt (cached 5 min).
    - Chat is not tied to any date range — one history per user.
    - Calls Claude with tool_use support for on-demand DB lookups.
    - Tools default to last 30 days; Claude passes start_date/end_date when the user
      asks for a specific range (e.g. "last 90 days", "all time").
    - No streaming — consistent with /insights/explain behavior.

    Called by: frontend dashboard AI chat panel
    """
    if len(body.message) > 500:
        raise HTTPException(status_code=422, detail="Message too long (max 500 chars)")

    from ._chat_snapshot import _fetch_dashboard_snapshot

    snapshot = await _fetch_dashboard_snapshot()

    # Load stored history for DB persistence; limit Claude's context to last 6 messages
    # (3 exchanges) to prevent old topic context from bleeding into unrelated questions.
    history = await _load_chat_history(str(user.id), "all", limit=_MAX_HISTORY_MSGS)
    recent_history = history[-6:] if len(history) > 6 else list(history)

    # Wrap current message with a topic-boundary signal for Claude.
    # This tells Claude to treat the current question independently from prior topics
    # unless the message itself references them. The original message is stored to DB.
    claude_message = (
        f"[NEW QUESTION — answer this independently. "
        f"Only use prior conversation context if this question explicitly references it "
        f"(e.g. 'those motions', 'that user', 'what you said').]\n\n{body.message}"
    )
    trimmed = recent_history + [{"role": "user", "content": claude_message}]

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    system_prompt = _CHAT_SYSTEM_PROMPT.format(
        snapshot_json=json.dumps(snapshot, default=str),
    )

    while True:
        response = await client.messages.create(
            model=CLAUDE_MODEL_STANDARD,
            max_tokens=1500,
            system=system_prompt,
            tools=_CHAT_TOOLS,
            messages=trimmed,
        )

        if response.stop_reason == "tool_use":
            tool_blocks = [b for b in response.content if b.type == "tool_use"]
            # Execute all tools from this response in parallel
            raw_results = await asyncio.gather(
                *[_execute_chat_tool(b.name, dict(b.input)) for b in tool_blocks],
                return_exceptions=True,
            )
            tool_results = []
            for block, result in zip(tool_blocks, raw_results):
                if isinstance(result, Exception):
                    logger.error("Tool %s failed: %s", block.name, result, exc_info=result)
                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     json.dumps({"error": str(result)}),
                        "is_error":    True,
                    })
                else:
                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     json.dumps(result, default=str),
                    })
            trimmed.append({"role": "assistant", "content": response.content})
            trimmed.append({"role": "user", "content": tool_results})
        else:
            reply = next((b.text for b in response.content if b.type == "text"), "")
            await _append_chat_messages(str(user.id), user.email, "all", [
                {"role": "user",      "content": body.message},
                {"role": "assistant", "content": reply},
            ])
            return ChatResponse(reply=reply)


# ---------------------------------------------------------------------------
# POST /insights/chat/stream — SSE streaming variant
# ---------------------------------------------------------------------------

@router.post("/insights/chat/stream")
async def dashboard_chat_stream(
    body: ChatRequest,
    user: User = Depends(get_current_firm_user),
):
    """
    Streaming version of dashboard_chat using Server-Sent Events.

    Event types emitted:
      {"type": "tool_status", "name": "<tool>", "status": "running"|"done"}
      {"type": "text_chunk",  "chunk": "<partial text>"}
      {"type": "done"}
      {"type": "error",       "message": "<error text>"}

    Tool calls run in parallel and non-streaming (we need full results before
    continuing the conversation). The final Claude reply is streamed as text_chunk
    events so the user sees text appear progressively.

    Called by: frontend dashboard AI chat panel (streaming mode)
    """
    if len(body.message) > 500:
        raise HTTPException(status_code=422, detail="Message too long (max 500 chars)")

    async def generate():
        try:
            from ._chat_snapshot import _fetch_dashboard_snapshot

            snapshot = await _fetch_dashboard_snapshot()
            history = await _load_chat_history(str(user.id), "all", limit=_MAX_HISTORY_MSGS)
            recent_history = history[-6:] if len(history) > 6 else list(history)

            claude_message = (
                f"[NEW QUESTION — answer this independently. "
                f"Only use prior conversation context if this question explicitly references it "
                f"(e.g. 'those motions', 'that user', 'what you said').]\n\n{body.message}"
            )
            messages: list[dict] = recent_history + [{"role": "user", "content": claude_message}]

            client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
            system_prompt = _CHAT_SYSTEM_PROMPT.format(
                snapshot_json=json.dumps(snapshot, default=str),
            )

            full_reply = ""

            while True:
                # Stream each Claude response — text chunks are yielded live;
                # tool_use blocks are collected via get_final_message() after streaming.
                reply_chunks: list[str] = []

                async with client.messages.stream(
                    model=CLAUDE_MODEL_STANDARD,
                    max_tokens=1500,
                    system=system_prompt,
                    tools=_CHAT_TOOLS,
                    messages=messages,
                ) as stream:
                    async for event in stream:
                        if (
                            hasattr(event, "type")
                            and event.type == "content_block_delta"
                            and hasattr(event.delta, "text")
                        ):
                            chunk = event.delta.text
                            reply_chunks.append(chunk)
                            yield f"data: {json.dumps({'type': 'text_chunk', 'chunk': chunk})}\n\n"

                    final = await stream.get_final_message()

                if final.stop_reason == "tool_use":
                    tool_blocks = [b for b in final.content if b.type == "tool_use"]

                    # Signal each tool is running
                    for block in tool_blocks:
                        yield f"data: {json.dumps({'type': 'tool_status', 'name': block.name, 'status': 'running'})}\n\n"

                    # Execute all tools in parallel
                    raw_results = await asyncio.gather(
                        *[_execute_chat_tool(b.name, dict(b.input)) for b in tool_blocks],
                        return_exceptions=True,
                    )

                    tool_results = []
                    for block, result in zip(tool_blocks, raw_results):
                        yield f"data: {json.dumps({'type': 'tool_status', 'name': block.name, 'status': 'done'})}\n\n"
                        if isinstance(result, Exception):
                            logger.error("Tool %s failed: %s", block.name, result, exc_info=result)
                            tool_results.append({
                                "type":        "tool_result",
                                "tool_use_id": block.id,
                                "content":     json.dumps({"error": str(result)}),
                                "is_error":    True,
                            })
                        else:
                            tool_results.append({
                                "type":        "tool_result",
                                "tool_use_id": block.id,
                                "content":     json.dumps(result, default=str),
                            })

                    messages.append({"role": "assistant", "content": final.content})
                    messages.append({"role": "user",      "content": tool_results})

                else:
                    full_reply = "".join(reply_chunks)
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    await _append_chat_messages(str(user.id), user.email, "all", [
                        {"role": "user",      "content": body.message},
                        {"role": "assistant", "content": full_reply},
                    ])
                    break

        except Exception as exc:
            logger.error("dashboard_chat_stream error: %s", exc, exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
