"""Tests for the v3 dry-run router endpoints.

We use FastAPI's TestClient + patch the service layer so we exercise:
- Path → body template_id mismatch returns 400
- cost_attribution wraps every call (semantic_id_kind="pleading_run_v2")
- Pending response surfaces as 200 with AwaitingInputResponseV2
- Completed response surfaces as 200 with DryRunResponseV2
- Resume endpoint route + same cost-attribution discriminator
- pending_inputs payload is validated through Pydantic discrimination
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.studio_v2.router import router as studio_v2_router
from src.core.studio_v2.types.orchestration import (
    AwaitingInputResponseV2,
    DryRunResponseV2,
)
from src.core.studio_v2.types.pending import PendingAuthorTextV2


_TEMPLATE_UUID = "00000000-0000-0000-0000-000000000099"


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(studio_v2_router, prefix="/api/v3")
    return TestClient(app)


def _spec_body():
    return {"template_id": _TEMPLATE_UUID, "fields": []}


def _dry_run_body(**overrides):
    body = {
        "template_id": _TEMPLATE_UUID,
        "case_id": "case-1",
        "template_spec": _spec_body(),
    }
    body.update(overrides)
    return body


def _resume_body(**overrides):
    body = {
        "template_id": _TEMPLATE_UUID,
        "case_id": "case-1",
        "template_spec": _spec_body(),
        "resolved_values": [],
        "user_picks": {},
    }
    body.update(overrides)
    return body


# ─── /dry-run ────────────────────────────────────────────────────────


@pytest.mark.unit
def test_dry_run_path_body_id_mismatch_400(client):
    body = _dry_run_body(template_id="different-uuid")
    resp = client.post(
        f"/api/v3/studio/templates/{_TEMPLATE_UUID}/dry-run",
        json=body,
    )
    assert resp.status_code == 400
    assert "mismatch" in resp.json()["detail"]


@pytest.mark.unit
def test_dry_run_returns_awaiting_input(client):
    pending_resp = AwaitingInputResponseV2(
        run_id="r-1", template_id=_TEMPLATE_UUID, case_id="case-1",
        pending_inputs={"x": PendingAuthorTextV2(label="x")},
    )
    with patch(
        "src.core.studio_v2.api.dry_run_router.execute_dry_run_v2",
        new=AsyncMock(return_value=pending_resp),
    ):
        resp = client.post(
            f"/api/v3/studio/templates/{_TEMPLATE_UUID}/dry-run",
            json=_dry_run_body(),
        )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "awaiting_input"
    assert "pending_inputs" in payload


@pytest.mark.unit
def test_dry_run_returns_completed(client):
    completed = DryRunResponseV2(
        run_id="r-1", template_id=_TEMPLATE_UUID, case_id="case-1",
        generated_doc_url="https://r2/x.docx",
        r2_object_key="cases/case-1/dry_run/x.docx",
    )
    with patch(
        "src.core.studio_v2.api.dry_run_router.execute_dry_run_v2",
        new=AsyncMock(return_value=completed),
    ):
        resp = client.post(
            f"/api/v3/studio/templates/{_TEMPLATE_UUID}/dry-run",
            json=_dry_run_body(),
        )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "completed"
    assert payload["generated_doc_url"] == "https://r2/x.docx"


@pytest.mark.unit
def test_dry_run_wraps_in_cost_attribution(client):
    """The route MUST call `cost_attribution` with the v2 bucket label
    so v2 dry-run LLM spend lands in the right Costs panel."""
    completed = DryRunResponseV2(
        run_id="r-1", template_id=_TEMPLATE_UUID, case_id="case-1",
        generated_doc_url="x", r2_object_key="x",
    )
    captured_kwargs: list[dict] = []
    from contextlib import contextmanager

    @contextmanager
    def fake_cost_attribution(**kwargs):
        captured_kwargs.append(kwargs)
        yield

    with patch(
        "src.core.studio_v2.api.dry_run_router.execute_dry_run_v2",
        new=AsyncMock(return_value=completed),
    ), patch(
        "src.core.studio_v2.api.dry_run_router.cost_attribution",
        side_effect=fake_cost_attribution,
    ):
        resp = client.post(
            f"/api/v3/studio/templates/{_TEMPLATE_UUID}/dry-run",
            json=_dry_run_body(),
        )
    assert resp.status_code == 200
    assert len(captured_kwargs) == 1
    assert captured_kwargs[0]["semantic_id_kind"] == "pleading_run_v2"
    assert captured_kwargs[0]["case_id"] == "case-1"
    assert captured_kwargs[0]["semantic_id"]  # synthetic UUID present


# ─── /dry-run/resume ────────────────────────────────────────────────


@pytest.mark.unit
def test_resume_path_body_id_mismatch_400(client):
    body = _resume_body(template_id="different")
    resp = client.post(
        f"/api/v3/studio/templates/{_TEMPLATE_UUID}/dry-run/resume",
        json=body,
    )
    assert resp.status_code == 400
    assert "mismatch" in resp.json()["detail"]


@pytest.mark.unit
def test_resume_returns_completed(client):
    completed = DryRunResponseV2(
        run_id="r-2", template_id=_TEMPLATE_UUID, case_id="case-1",
        generated_doc_url="https://r2/done.docx",
        r2_object_key="cases/case-1/dry_run/done.docx",
    )
    with patch(
        "src.core.studio_v2.api.dry_run_router.resume_dry_run_v2",
        new=AsyncMock(return_value=completed),
    ):
        resp = client.post(
            f"/api/v3/studio/templates/{_TEMPLATE_UUID}/dry-run/resume",
            json=_resume_body(),
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


@pytest.mark.unit
def test_resume_wraps_in_cost_attribution_with_v2_bucket(client):
    """Resume MUST roll into the SAME pleading_run_v2 bucket."""
    completed = DryRunResponseV2(
        run_id="r-2", template_id=_TEMPLATE_UUID, case_id="case-1",
        generated_doc_url="x", r2_object_key="x",
    )
    captured: list[dict] = []
    from contextlib import contextmanager

    @contextmanager
    def fake_cost_attribution(**kwargs):
        captured.append(kwargs)
        yield

    with patch(
        "src.core.studio_v2.api.dry_run_router.resume_dry_run_v2",
        new=AsyncMock(return_value=completed),
    ), patch(
        "src.core.studio_v2.api.dry_run_router.cost_attribution",
        side_effect=fake_cost_attribution,
    ):
        resp = client.post(
            f"/api/v3/studio/templates/{_TEMPLATE_UUID}/dry-run/resume",
            json=_resume_body(),
        )
    assert resp.status_code == 200
    assert captured[0]["semantic_id_kind"] == "pleading_run_v2"


@pytest.mark.unit
def test_resume_validates_pending_inputs_payload(client):
    """The pending_inputs raw dict must validate against the
    discriminated union; nonsense returns 400."""
    body = _resume_body(pending_inputs={"x": {"kind": "not-a-real-kind"}})
    completed = DryRunResponseV2(
        run_id="r-2", template_id=_TEMPLATE_UUID, case_id="case-1",
        generated_doc_url="x", r2_object_key="x",
    )
    with patch(
        "src.core.studio_v2.api.dry_run_router.resume_dry_run_v2",
        new=AsyncMock(return_value=completed),
    ):
        resp = client.post(
            f"/api/v3/studio/templates/{_TEMPLATE_UUID}/dry-run/resume",
            json=body,
        )
    assert resp.status_code == 400
    assert "pending_inputs failed to validate" in resp.json()["detail"]


@pytest.mark.unit
def test_resume_accepts_valid_pending_inputs(client):
    body = _resume_body(pending_inputs={
        "narrative": {"kind": "author_text", "label": "Type it"},
    })
    completed = DryRunResponseV2(
        run_id="r-2", template_id=_TEMPLATE_UUID, case_id="case-1",
        generated_doc_url="x", r2_object_key="x",
    )
    captured_pending: list = []

    async def fake_resume(**kwargs):
        captured_pending.append(kwargs["pending_inputs"])
        return completed

    with patch(
        "src.core.studio_v2.api.dry_run_router.resume_dry_run_v2",
        new=AsyncMock(side_effect=fake_resume),
    ):
        resp = client.post(
            f"/api/v3/studio/templates/{_TEMPLATE_UUID}/dry-run/resume",
            json=body,
        )
    assert resp.status_code == 200
    # pending_inputs got discriminated through to the right Pydantic type.
    pending = captured_pending[0]
    assert "narrative" in pending
    assert pending["narrative"].kind == "author_text"
