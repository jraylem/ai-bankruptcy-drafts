"""Tests for expand_picks_v2 — covers all 3 pick types and the
raw_context lookup via the envelope."""

import pytest

from src.core.studio_v2.orchestration.picks import expand_picks_v2
from src.core.studio_v2.types.fields import TemplateFieldV2
from src.core.studio_v2.types.pending import (
    PendingChipV2,
    PendingDropdownV2,
    PendingMultiSelectV2,
)
from src.core.studio_v2.types.picks import (
    MultiSelectPickV2,
    SingleValuePickV2,
    SupportingDocsPickV2,
)
from src.core.studio_v2.types.wizard_sources import SourceKind, WizardSourceParams


_FIELD_UUID = "00000000-0000-0000-0000-000000000001"
_TEMPLATE_UUID = "00000000-0000-0000-0000-000000000002"


def _field(name):
    return TemplateFieldV2(
        id=_FIELD_UUID, template_id=_TEMPLATE_UUID,
        template_variable=name,
        params=WizardSourceParams(source=SourceKind.GMAIL),
    )


# ─── SingleValuePickV2 ───────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_single_value_pick_carries_raw_context_from_envelope():
    fields = [_field("creditor")]
    picks = {"creditor": SingleValuePickV2(value="Acme Bank")}
    envelope = PendingDropdownV2(
        label="Pick creditor",
        options=["Acme Bank", "Wells Fargo"],
        raw_contexts=["Acme chunk text", "Wells chunk text"],
    )
    rows = await expand_picks_v2(
        template_fields=fields,
        user_picks=picks,
        pending_inputs={"creditor": envelope},
    )
    assert len(rows) == 1
    assert rows[0].value == "Acme Bank"
    assert rows[0].raw_context == "Acme chunk text"
    assert rows[0].confidence == "high"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_single_value_pick_no_envelope_empty_raw_context():
    fields = [_field("note")]
    picks = {"note": SingleValuePickV2(value="some free text")}
    rows = await expand_picks_v2(template_fields=fields, user_picks=picks)
    assert rows[0].value == "some free text"
    assert rows[0].raw_context == ""


@pytest.mark.unit
@pytest.mark.asyncio
async def test_single_value_pick_with_chip_envelope():
    fields = [_field("basis")]
    picks = {"basis": SingleValuePickV2(value="Lack of documentation")}
    envelope = PendingChipV2(
        label="Pick basis",
        chips=["Lack of documentation", "Untimely filing"],
        raw_contexts=["chunk for lack", "chunk for timely"],
    )
    rows = await expand_picks_v2(
        template_fields=fields,
        user_picks=picks,
        pending_inputs={"basis": envelope},
    )
    assert rows[0].raw_context == "chunk for lack"


# ─── MultiSelectPickV2 ───────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_multi_select_pick_oxford_comma_joins_two():
    fields = [_field("creditors")]
    picks = {"creditors": MultiSelectPickV2(picked_values=["A", "B"])}
    rows = await expand_picks_v2(template_fields=fields, user_picks=picks)
    assert rows[0].value == "A and B"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_multi_select_pick_oxford_comma_joins_three():
    fields = [_field("creditors")]
    picks = {"creditors": MultiSelectPickV2(picked_values=["A", "B", "C"])}
    rows = await expand_picks_v2(template_fields=fields, user_picks=picks)
    assert rows[0].value == "A, B, and C"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_multi_select_pick_dedupes_case_insensitively():
    fields = [_field("x")]
    picks = {"x": MultiSelectPickV2(picked_values=["Foo", "foo", "FOO", "Bar"])}
    rows = await expand_picks_v2(template_fields=fields, user_picks=picks)
    assert rows[0].value == "Foo and Bar"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_multi_select_pick_joins_raw_contexts_from_envelope():
    fields = [_field("creditors")]
    envelope = PendingMultiSelectV2(
        label="Pick",
        options=["Acme", "Wells"],
        raw_contexts=["chunk acme", "chunk wells"],
    )
    picks = {"creditors": MultiSelectPickV2(picked_values=["Acme", "Wells"])}
    rows = await expand_picks_v2(
        template_fields=fields, user_picks=picks,
        pending_inputs={"creditors": envelope},
    )
    assert rows[0].raw_context == "chunk acme\n---\nchunk wells"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_multi_select_empty_picks_returns_empty_row():
    fields = [_field("x")]
    picks = {"x": MultiSelectPickV2(picked_values=[])}
    rows = await expand_picks_v2(template_fields=fields, user_picks=picks)
    assert rows[0].value == ""
    assert rows[0].confidence == "none"


# ─── SupportingDocsPickV2 ────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_supporting_docs_pick_with_case_id_runs_enhancement():
    """Live path (slice F): case_id supplied → validate URLs, download
    files, run ExplanationEnhanceAgentV2."""
    from unittest.mock import AsyncMock as _AsyncMock, patch as _patch
    from src.core.common.documents.supporting_doc_reader import AttachedPdfDoc

    fields = [_field("narrative")]
    picks = {"narrative": SupportingDocsPickV2(
        user_text="lost wages after surgery",
        file_urls=["cases/case-1/supporting_docs/abc.pdf"],
    )}
    with _patch(
        "src.core.studio_v2.orchestration.picks.r2_service.download_file",
        new=_AsyncMock(return_value=b"%PDF-1.4 fake bytes"),
    ), _patch(
        "src.core.studio_v2.orchestration.picks.read_supporting_doc",
        return_value=AttachedPdfDoc(filename="abc.pdf", base64_data="ZmFrZQ=="),
    ), _patch(
        "src.core.studio_v2.orchestration.picks.ExplanationEnhanceAgentV2.run",
        new=_AsyncMock(return_value="The Debtor lost wages after surgery on April 2, 2026."),
    ) as agent_mock:
        rows = await expand_picks_v2(
            template_fields=fields, user_picks=picks, resource_key="case-1",
        )
    agent_mock.assert_awaited_once()
    assert rows[0].value.startswith("The Debtor lost wages")
    assert rows[0].confidence == "high"
    assert "1 of 1 files attached" in rows[0].note


@pytest.mark.unit
@pytest.mark.asyncio
async def test_supporting_docs_pick_without_case_id_degrades():
    """No case_id → can't download; return raw user_text + low confidence."""
    fields = [_field("narrative")]
    picks = {"narrative": SupportingDocsPickV2(
        user_text="The Debtor's income dropped after surgery in April 2026.",
        file_urls=["cases/case-1/supporting_docs/abc.pdf"],
    )}
    rows = await expand_picks_v2(template_fields=fields, user_picks=picks)
    assert "income dropped" in rows[0].value
    assert rows[0].confidence == "low"
    assert "resource_key missing" in rows[0].note


@pytest.mark.unit
@pytest.mark.asyncio
async def test_supporting_docs_pick_rejects_off_prefix_urls():
    """Security: file_urls outside the case's supporting_docs prefix
    are dropped (logged); the agent still runs on what's left."""
    from unittest.mock import AsyncMock as _AsyncMock, patch as _patch

    fields = [_field("narrative")]
    picks = {"narrative": SupportingDocsPickV2(
        user_text="some text",
        file_urls=[
            "cases/case-OTHER/supporting_docs/sneaky.pdf",
            "https://malicious.example.com/data.pdf",
            "/etc/passwd",
        ],
    )}
    with _patch(
        "src.core.studio_v2.orchestration.picks.r2_service.download_file",
        new=_AsyncMock(return_value=b""),
    ) as download_mock, _patch(
        "src.core.studio_v2.orchestration.picks.ExplanationEnhanceAgentV2.run",
        new=_AsyncMock(return_value="polished"),
    ):
        rows = await expand_picks_v2(
            template_fields=fields, user_picks=picks, resource_key="case-1",
        )
    # All 3 urls were off-prefix → no downloads attempted.
    download_mock.assert_not_called()
    # But the enhancement still ran (with 0 supporting docs) on user_text.
    assert rows[0].value == "polished"
    assert "0 of 3 files attached" in rows[0].note


@pytest.mark.unit
@pytest.mark.asyncio
async def test_supporting_docs_pick_download_failure_skips_doc():
    """Per-doc download failure is logged + skipped; agent still runs
    on whatever docs succeeded."""
    from unittest.mock import AsyncMock as _AsyncMock, patch as _patch
    from src.core.common.documents.supporting_doc_reader import AttachedPdfDoc

    fields = [_field("narrative")]
    picks = {"narrative": SupportingDocsPickV2(
        user_text="some text",
        file_urls=[
            "cases/case-1/supporting_docs/good.pdf",
            "cases/case-1/supporting_docs/missing.pdf",
        ],
    )}

    async def fake_download(template_id, filename, prefix):
        if "missing" in filename:
            raise RuntimeError("404 from R2")
        return b"good bytes"

    with _patch(
        "src.core.studio_v2.orchestration.picks.r2_service.download_file",
        new=_AsyncMock(side_effect=fake_download),
    ), _patch(
        "src.core.studio_v2.orchestration.picks.read_supporting_doc",
        return_value=AttachedPdfDoc(filename="good.pdf", base64_data="b2s="),
    ), _patch(
        "src.core.studio_v2.orchestration.picks.ExplanationEnhanceAgentV2.run",
        new=_AsyncMock(return_value="polished"),
    ):
        rows = await expand_picks_v2(
            template_fields=fields, user_picks=picks, resource_key="case-1",
        )
    assert "1 of 2 files attached" in rows[0].note


@pytest.mark.unit
@pytest.mark.asyncio
async def test_supporting_docs_empty_user_text_confidence_none():
    fields = [_field("narrative")]
    picks = {"narrative": SupportingDocsPickV2(user_text="", file_urls=[])}
    rows = await expand_picks_v2(template_fields=fields, user_picks=picks)
    assert rows[0].confidence == "none"


# ─── unknown / missing field defensive paths ─────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pick_for_unknown_field_is_ignored():
    rows = await expand_picks_v2(
        template_fields=[_field("known")],
        user_picks={"unknown": SingleValuePickV2(value="x")},
    )
    assert rows == []
