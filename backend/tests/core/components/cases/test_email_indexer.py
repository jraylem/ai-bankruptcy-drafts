"""Tests for EmailIndexer — backfills Gmail + Court Drive emails into
per-case pgvector collections.

Mocks:
  - ToolBox.query_email (external Gmail API)
  - index_documents (pgvector write)

What matters:
  1. Both sources are indexed in one .index() call
  2. Counts are returned as (gmail, courtdrive)
  3. query_email exceptions do NOT propagate — logged + 0 returned for that source
  4. Emails are converted to Documents with case-scoped metadata
  5. Empty results short-circuit without calling index_documents
  6. chunk_size=None (one email → one embedding row)
"""

from unittest.mock import AsyncMock

import pytest

from src.core.common.services.email import EmailType
from src.core.common.toolbox import ToolBox
from src.core.components.cases import email_indexer as email_indexer_module
from src.core.components.cases.email_indexer import EmailIndexer
from tests.core.factories import make_email, make_email_search_result


# ─── .index() ─────────────────────────────────────────────────────────


@pytest.mark.unit
async def test_index_returns_zero_counts_when_no_emails_match(monkeypatch):
    monkeypatch.setattr(
        ToolBox,
        "query_email",
        AsyncMock(return_value=make_email_search_result(emails=[])),
    )
    # index_documents should not be called when there are no emails; if it is,
    # the test fails loudly.
    monkeypatch.setattr(
        email_indexer_module,
        "index_documents",
        AsyncMock(side_effect=AssertionError("should not index empty batch")),
    )

    gmail, courtdrive = await EmailIndexer.index(case_id="26_10700", resource_key="26_10700", case_number="26-10700")

    assert (gmail, courtdrive) == (0, 0)


@pytest.mark.unit
async def test_index_writes_documents_for_both_sources(monkeypatch):
    # Make the search return different email counts per source
    async def fake_query_email(email_type: EmailType, **kwargs):
        if email_type == EmailType.GMAIL:
            return make_email_search_result(
                emails=[make_email(id="g1"), make_email(id="g2")],
                source=EmailType.GMAIL,
            )
        return make_email_search_result(
            emails=[make_email(id="cd1")],
            source=EmailType.COURT_DRIVE,
        )

    monkeypatch.setattr(ToolBox, "query_email", fake_query_email)

    indexed_calls: list[dict] = []

    async def fake_index(collection_name, documents, chunk_size):
        indexed_calls.append({
            "collection_name": collection_name,
            "n_docs": len(documents),
            "chunk_size": chunk_size,
        })
        return len(documents)

    monkeypatch.setattr(email_indexer_module, "index_documents", fake_index)

    gmail, courtdrive = await EmailIndexer.index(case_id="26_10700", resource_key="26_10700", case_number="26-10700")

    assert (gmail, courtdrive) == (2, 1)
    # Two calls — one per source — with case-scoped collection names and
    # chunk_size=None (one email → one row).
    assert len(indexed_calls) == 2
    assert {c["collection_name"] for c in indexed_calls} == {
        "gmail_emails_26_10700",
        "courtdrive_emails_26_10700",
    }
    assert all(c["chunk_size"] is None for c in indexed_calls)


@pytest.mark.unit
async def test_index_attaches_case_scoped_metadata_to_documents(monkeypatch):
    monkeypatch.setattr(
        ToolBox,
        "query_email",
        AsyncMock(return_value=make_email_search_result(
            emails=[make_email(id="msg_1", subject="Docket 42")],
            source=EmailType.GMAIL,
        )),
    )

    captured_docs: list = []

    async def fake_index(collection_name, documents, chunk_size):
        captured_docs.extend(documents)
        return len(documents)

    monkeypatch.setattr(email_indexer_module, "index_documents", fake_index)

    await EmailIndexer.index(case_id="26_10700", resource_key="26_10700", case_number="26-10700")

    # First non-empty call populated captured_docs. Grab the gmail one.
    gmail_doc = next(d for d in captured_docs if d.metadata["source"] == "gmail")
    md = gmail_doc.metadata
    assert md["case_id"] == "26_10700"
    assert md["case_number"] == "26-10700"
    assert md["email_id"] == "msg_1"
    assert md["subject"] == "Docket 42"
    assert md["doc_type"] == "email"


@pytest.mark.unit
async def test_index_court_drive_documents_tagged_court_email(monkeypatch):
    """CourtDrive path uses doc_type='court_email' (different from gmail's 'email')."""
    async def fake_query_email(email_type: EmailType, **kwargs):
        if email_type == EmailType.GMAIL:
            return make_email_search_result(emails=[], source=EmailType.GMAIL)
        return make_email_search_result(
            emails=[make_email(id="cd1")],
            source=EmailType.COURT_DRIVE,
        )

    monkeypatch.setattr(ToolBox, "query_email", fake_query_email)

    captured_docs: list = []

    async def fake_index(collection_name, documents, chunk_size):
        captured_docs.extend(documents)
        return len(documents)

    monkeypatch.setattr(email_indexer_module, "index_documents", fake_index)

    await EmailIndexer.index(case_id="26_10700", resource_key="26_10700", case_number="26-10700")

    assert len(captured_docs) == 1
    assert captured_docs[0].metadata["source"] == "court_drive"
    assert captured_docs[0].metadata["doc_type"] == "court_email"


@pytest.mark.unit
async def test_index_does_not_propagate_query_email_exceptions(monkeypatch):
    """If Gmail API raises for one source, that source returns 0 but the
    OTHER source still gets indexed."""

    async def fake_query_email(email_type: EmailType, **kwargs):
        if email_type == EmailType.GMAIL:
            raise RuntimeError("gmail api flaked")
        return make_email_search_result(
            emails=[make_email(id="cd1")],
            source=EmailType.COURT_DRIVE,
        )

    monkeypatch.setattr(ToolBox, "query_email", fake_query_email)
    monkeypatch.setattr(
        email_indexer_module, "index_documents", AsyncMock(return_value=1)
    )

    gmail, courtdrive = await EmailIndexer.index(case_id="26_10700", resource_key="26_10700", case_number="26-10700")

    assert gmail == 0
    assert courtdrive == 1


@pytest.mark.unit
async def test_index_formats_email_body_with_headers(monkeypatch):
    """Document.page_content should include Subject/From/Date headers above body."""
    monkeypatch.setattr(
        ToolBox,
        "query_email",
        AsyncMock(return_value=make_email_search_result(
            emails=[
                make_email(
                    id="m1",
                    subject="Order of Dismissal",
                    sender="clerk@ecf.example",
                    date="Wed, 3 Apr 2026 14:02:00 -0500",
                    body="The case is dismissed without prejudice.",
                ),
            ],
            source=EmailType.GMAIL,
        )),
    )

    captured_docs: list = []

    async def fake_index(collection_name, documents, chunk_size):
        captured_docs.extend(documents)
        return len(documents)

    monkeypatch.setattr(email_indexer_module, "index_documents", fake_index)

    await EmailIndexer.index(case_id="26_10700", resource_key="26_10700", case_number="26-10700")

    gmail_doc = next(d for d in captured_docs if d.metadata["source"] == "gmail")
    content = gmail_doc.page_content
    assert "Subject: Order of Dismissal" in content
    assert "From: clerk@ecf.example" in content
    assert "Date: Wed, 3 Apr 2026" in content
    assert "The case is dismissed without prejudice." in content


@pytest.mark.unit
async def test_index_passes_max_results_to_query_email(monkeypatch):
    captured_kwargs = {}

    async def fake_query_email(**kwargs):
        captured_kwargs.update(kwargs)
        return make_email_search_result(emails=[], source=kwargs["email_type"])

    monkeypatch.setattr(ToolBox, "query_email", fake_query_email)
    monkeypatch.setattr(
        email_indexer_module, "index_documents", AsyncMock(return_value=0)
    )

    await EmailIndexer.index(case_id="26_10700", resource_key="26_10700", case_number="26-10700")

    # The module's _BACKFILL_MAX_RESULTS is 100; ensure it's threaded through.
    assert captured_kwargs["max_results"] == 100
    assert captured_kwargs["case_number"] == "26-10700"
