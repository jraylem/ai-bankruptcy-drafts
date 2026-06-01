"""Tests for PdfIndexer — petition PDF → chunked pgvector embeddings.

We mock PdfReader so tests don't need real PDF bytes, and mock
index_documents to assert the shape/metadata we'd write to pgvector.
"""

from unittest.mock import AsyncMock

import pytest

from src.core.agents.llm.case_ingestion import CaseMetadata
from src.core.components.cases import pdf_indexer as pdf_indexer_module
from src.core.components.cases.pdf_indexer import PdfIndexer


class _FakePage:
    def __init__(self, text: str | None):
        self._text = text

    def extract_text(self):
        return self._text


class _FakeReader:
    def __init__(self, pages):
        self.pages = pages


@pytest.fixture
def fake_pdf(monkeypatch):
    """Replace PdfReader with a fake that yields caller-specified page texts.

    Usage::

        fake_pdf(["page 1 text", "", "page 3 text"])
    """
    def make_patch(page_texts: list[str | None]):
        pages = [_FakePage(t) for t in page_texts]
        monkeypatch.setattr(
            pdf_indexer_module, "PdfReader", lambda _buf: _FakeReader(pages)
        )

    return make_patch


def _metadata() -> CaseMetadata:
    return CaseMetadata(
        case_number="26-10700",
        debtors=["John Smith"],
        chapter=13,
        court_district="S.D. Fla.",
    )


# ─── .index() ─────────────────────────────────────────────────────────


@pytest.mark.unit
async def test_index_returns_zero_when_all_pages_empty(fake_pdf, monkeypatch):
    fake_pdf(["", "   ", None])
    not_called = AsyncMock(side_effect=AssertionError("should not index empty batch"))
    monkeypatch.setattr(pdf_indexer_module, "index_documents", not_called)

    result = await PdfIndexer.index(
        case_id="26_10700",
        resource_key="26_10700",
        pdf_bytes=b"%PDF-1.4...",
        case_metadata=_metadata(),
    )

    assert result == 0


@pytest.mark.unit
async def test_index_skips_empty_pages_and_indexes_the_rest(fake_pdf, monkeypatch):
    fake_pdf(["In re: John Smith, Debtor.", "", "The Plan is CONFIRMED."])

    captured_docs: list = []

    async def fake_index(collection_name, documents, chunk_size, chunk_overlap):
        captured_docs.extend(documents)
        return len(documents)

    monkeypatch.setattr(pdf_indexer_module, "index_documents", fake_index)

    result = await PdfIndexer.index(
        case_id="26_10700",
        resource_key="26_10700",
        pdf_bytes=b"%PDF-1.4...",
        case_metadata=_metadata(),
    )

    # 2 non-empty pages → 2 documents passed to index_documents
    assert len(captured_docs) == 2
    assert result == 2


@pytest.mark.unit
async def test_index_calls_index_documents_with_chunk_500_overlap_50(fake_pdf, monkeypatch):
    fake_pdf(["some text"])

    captured: dict = {}

    async def fake_index(collection_name, documents, chunk_size, chunk_overlap):
        captured["collection_name"] = collection_name
        captured["chunk_size"] = chunk_size
        captured["chunk_overlap"] = chunk_overlap
        return len(documents)

    monkeypatch.setattr(pdf_indexer_module, "index_documents", fake_index)

    await PdfIndexer.index(
        case_id="26_10700",
        resource_key="26_10700",
        pdf_bytes=b"%PDF-1.4...",
        case_metadata=_metadata(),
    )

    assert captured["collection_name"] == "case_file_26_10700"
    assert captured["chunk_size"] == 500
    assert captured["chunk_overlap"] == 50


@pytest.mark.unit
async def test_index_attaches_case_metadata_and_page_number(fake_pdf, monkeypatch):
    fake_pdf(["page zero", "page one", "page two"])

    captured_docs: list = []

    async def fake_index(collection_name, documents, chunk_size, chunk_overlap):
        captured_docs.extend(documents)
        return len(documents)

    monkeypatch.setattr(pdf_indexer_module, "index_documents", fake_index)

    await PdfIndexer.index(
        case_id="26_10700",
        resource_key="26_10700",
        pdf_bytes=b"%PDF-1.4...",
        case_metadata=_metadata(),
    )

    assert len(captured_docs) == 3
    # Each page preserves its original index as metadata.page
    assert [d.metadata["page"] for d in captured_docs] == [0, 1, 2]

    # Case-scoped metadata applied uniformly
    for d in captured_docs:
        md = d.metadata
        assert md["case_id"] == "26_10700"
        assert md["case_number"] == "26-10700"
        assert md["case_name"] == "John Smith"
        assert md["source"] == "petition.pdf"
        assert md["doc_type"] == "petition_page"


@pytest.mark.unit
async def test_index_preserves_original_page_number_when_skipping_empty_ones(fake_pdf, monkeypatch):
    """If page 1 is empty, page 0 and page 2 should keep their original indices —
    NOT renumber to 0 and 1 in the output. This matters for downstream citation."""
    fake_pdf(["first page", "", "third page"])

    captured_docs: list = []

    async def fake_index(collection_name, documents, chunk_size, chunk_overlap):
        captured_docs.extend(documents)
        return len(documents)

    monkeypatch.setattr(pdf_indexer_module, "index_documents", fake_index)

    await PdfIndexer.index(
        case_id="26_10700",
        resource_key="26_10700",
        pdf_bytes=b"%PDF-1.4...",
        case_metadata=_metadata(),
    )

    pages = [d.metadata["page"] for d in captured_docs]
    assert pages == [0, 2]  # NOT [0, 1]


@pytest.mark.unit
async def test_index_strips_whitespace_from_extracted_text(fake_pdf, monkeypatch):
    fake_pdf(["   \n  page with surrounding whitespace  \n  "])

    captured_docs: list = []

    async def fake_index(collection_name, documents, chunk_size, chunk_overlap):
        captured_docs.extend(documents)
        return len(documents)

    monkeypatch.setattr(pdf_indexer_module, "index_documents", fake_index)

    await PdfIndexer.index(
        case_id="26_10700",
        resource_key="26_10700",
        pdf_bytes=b"%PDF-1.4...",
        case_metadata=_metadata(),
    )

    assert captured_docs[0].page_content == "page with surrounding whitespace"


@pytest.mark.unit
async def test_index_returns_row_count_from_index_documents(fake_pdf, monkeypatch):
    """The return value must be whatever index_documents reported, not the
    source page count — because chunking may fan one page into multiple rows."""
    fake_pdf(["page 1", "page 2"])
    monkeypatch.setattr(
        pdf_indexer_module, "index_documents", AsyncMock(return_value=7)
    )

    result = await PdfIndexer.index(
        case_id="26_10700",
        resource_key="26_10700",
        pdf_bytes=b"%PDF-1.4...",
        case_metadata=_metadata(),
    )

    assert result == 7
