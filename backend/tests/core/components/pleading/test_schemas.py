"""Pydantic shape sanity for the v2 pleading schemas.

The shapes back the Redis records, the FE-facing API, and the SSE envelopes
— bad-shape regressions would silently break the whole pipeline, so they're
worth a thin smoke test even though they're "just types".
"""

from datetime import datetime, timezone

import pytest

from src.core.components.engines.draft.schemas import (
    DraftChildResult,
    DraftResponse,
    DraftValidation,
)
from src.core.components.pleading.schemas import (
    ACTIVE_STATES,
    TERMINAL_STATES,
    BundleChildLog,
    CaseGenerationLogResponse,
    ChildPresignedEntry,
    CompletedDocumentEnvelope,
    StartTemplateDraftRequest,
    StartTemplateDraftResponse,
    SubmitInputRequest,
    V2TemplateDraftEvent,
    V2TemplateDraftTaskRecord,
    V2TemplateDraftTaskResponse,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─── State machine constants ──────────────────────────────────────────


@pytest.mark.unit
def test_active_and_terminal_states_partition_the_state_machine():
    assert ACTIVE_STATES.isdisjoint(TERMINAL_STATES)
    # Every status referenced by the Literal in V2TemplateDraftTaskRecord lands
    # in exactly one of the two sets — no orphan that the rest of the system
    # would forget about.
    all_known = ACTIVE_STATES | TERMINAL_STATES
    assert all_known == {
        "QUEUED",
        "PENDING",
        "CHECKING_EXISTING",
        "EXISTING_FOUND",
        "DRAFTING",
        "AWAITING_INPUT",
        "COMPLETED",
        "FAILED",
        "CANCELLED",
    }


@pytest.mark.unit
def test_active_states_contains_in_flight_and_pause_statuses():
    assert "PENDING" in ACTIVE_STATES
    assert "DRAFTING" in ACTIVE_STATES
    assert "AWAITING_INPUT" in ACTIVE_STATES
    assert "EXISTING_FOUND" in ACTIVE_STATES
    assert "QUEUED" in ACTIVE_STATES
    assert "COMPLETED" not in ACTIVE_STATES
    assert "FAILED" not in ACTIVE_STATES
    assert "CANCELLED" not in ACTIVE_STATES


# ─── Records ──────────────────────────────────────────────────────────


@pytest.mark.unit
def test_v2_task_record_round_trips_through_json():
    """Redis state.py persists records by serializing JSON; deserialization
    must yield an equal record so SSE consumers see the same fields."""
    now = _now()
    record = V2TemplateDraftTaskRecord(
        task_id="task-1",
        user_id="user-1",
        case_id="26_10700",
        template_id="tpl-A",
        template_name="Motion to Extend",
        status="DRAFTING",
        bundle_picks={"0": "Yes"},
        log_id="log-1",
        existing_log_id=None,
        result=None,
        error=None,
        created_at=now,
        updated_at=now,
    )
    payload = record.model_dump_json()
    rebuilt = V2TemplateDraftTaskRecord.model_validate_json(payload)
    assert rebuilt == record


@pytest.mark.unit
def test_v2_task_record_rejects_unknown_status():
    with pytest.raises(Exception):
        V2TemplateDraftTaskRecord(
            task_id="t",
            user_id="u",
            case_id="c",
            template_id="tpl",
            template_name="",
            status="MADE_UP",  # type: ignore[arg-type]
            bundle_picks=None,
            created_at=_now(),
            updated_at=_now(),
        )


@pytest.mark.unit
def test_task_response_from_record_mirrors_fields():
    """`from_record` is how the BE shapes the Redis record into the FE-facing
    response. Drop a field on the record and the response should follow."""
    now = _now()
    record = V2TemplateDraftTaskRecord(
        task_id="task-2",
        user_id="user-1",
        case_id="case",
        template_id="tpl",
        template_name="snapshot name",
        status="EXISTING_FOUND",
        bundle_picks=None,
        existing_log_id="log-existing",
        created_at=now,
        updated_at=now,
    )
    response = V2TemplateDraftTaskResponse.from_record(record)
    assert response.task_id == "task-2"
    assert response.status == "EXISTING_FOUND"
    assert response.existing_log_id == "log-existing"
    assert response.template_name == "snapshot name"


# ─── Requests / responses ─────────────────────────────────────────────


@pytest.mark.unit
def test_start_draft_request_skip_existing_check_defaults_false():
    req = StartTemplateDraftRequest(template_id="tpl-1", case_id="case-1")
    assert req.skip_existing_check is False
    assert req.bundle_picks is None


@pytest.mark.unit
def test_start_draft_response_wraps_a_task():
    now = _now()
    task = V2TemplateDraftTaskResponse(
        task_id="t",
        user_id="u",
        case_id="c",
        template_id="tpl",
        template_name="",
        status="PENDING",
        bundle_picks=None,
        created_at=now,
        updated_at=now,
    )
    res = StartTemplateDraftResponse(task=task)
    assert res.task.task_id == "t"


@pytest.mark.unit
def test_submit_input_request_requires_user_picks():
    """Empty `user_picks` is fine (idempotent resume); missing the key is not."""
    SubmitInputRequest(user_picks={})
    with pytest.raises(Exception):
        SubmitInputRequest()  # type: ignore[call-arg]


# ─── Bundle child + completed envelope ────────────────────────────────


@pytest.mark.unit
def test_bundle_child_log_carries_durable_key_not_url():
    """BundleChildLog is the JSONB shape persisted on case_generation_logs.
    It MUST hold the raw R2 key — never a presigned URL — so re-signing on
    read produces a fresh URL with a non-stale signature."""
    child = BundleChildLog(
        template_id="tpl-child",
        template_name="Cover Sheet",
        companion_label="Always",
        r2_object_key="cases/case_id/draft/child-uuid.docx",
    )
    assert child.r2_object_key.startswith("cases/")


@pytest.mark.unit
def test_completed_document_envelope_supports_no_children():
    """Single-template tasks return an envelope with `children=[]`."""
    env = CompletedDocumentEnvelope(
        log_id="log-1",
        parent_template_id="tpl",
        parent_url="https://r2.example/parent.docx?sig=foo",
    )
    assert env.children == []


@pytest.mark.unit
def test_completed_document_envelope_serializes_children():
    env = CompletedDocumentEnvelope(
        log_id="log-1",
        parent_template_id="tpl-parent",
        parent_url="https://r2.example/parent.docx?sig=p",
        children=[
            ChildPresignedEntry(
                template_id="tpl-child",
                template_name="Cover Sheet",
                companion_label="Always",
                url="https://r2.example/child.docx?sig=c",
            ),
        ],
    )
    dumped = env.model_dump()
    assert dumped["children"][0]["companion_label"] == "Always"
    assert dumped["children"][0]["url"].endswith("sig=c")


# ─── History list response ────────────────────────────────────────────


@pytest.mark.unit
def test_case_generation_log_response_handles_nullable_updated_at():
    """Brand-new log rows may not yet have an `updated_at` (server_default
    `onupdate` only fires on UPDATE). The response shape must allow None."""
    CaseGenerationLogResponse(
        id="log-1",
        user_id="u",
        case_id="c",
        draft_template_id="tpl",
        template_name=None,
        status="PENDING",
        task_id=None,
        error=None,
        created_at=_now(),
        updated_at=None,
    )


# ─── SSE envelope ─────────────────────────────────────────────────────


@pytest.mark.unit
def test_v2_template_draft_event_envelope_supports_snapshot_and_singletask():
    now = _now()
    one = V2TemplateDraftTaskResponse(
        task_id="t",
        user_id="u",
        case_id="c",
        template_id="tpl",
        template_name="",
        status="DRAFTING",
        bundle_picks=None,
        created_at=now,
        updated_at=now,
    )
    snapshot_evt = V2TemplateDraftEvent(type="snapshot", tasks=[one])
    assert snapshot_evt.task is None
    assert len(snapshot_evt.tasks or []) == 1

    update_evt = V2TemplateDraftEvent(type="status_changed", task=one)
    assert update_evt.tasks is None
    assert update_evt.task is not None and update_evt.task.task_id == "t"


# ─── Draft engine shapes propagated from v2 ───────────────────────────


@pytest.mark.unit
def test_draft_response_now_requires_r2_object_key():
    """The v2 worker reads `result.r2_object_key` to persist case_generation_logs.
    A regression that drops the field would silently break the audit trail."""
    with pytest.raises(Exception):
        DraftResponse(  # type: ignore[call-arg]
            template_id="tpl",
            case_id="case",
            resolved_values=[],
            generated_doc_url="https://r2.example/file.docx",
            validation=DraftValidation(valid=True, errors=[], warnings=[]),
        )


@pytest.mark.unit
def test_draft_child_result_now_requires_r2_object_key():
    with pytest.raises(Exception):
        DraftChildResult(  # type: ignore[call-arg]
            template_id="tpl-child",
            template_name="Cover Sheet",
            companion_label="Always",
            generated_doc_url="https://r2.example/child.docx",
            resolved_values=[],
        )
