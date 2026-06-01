"""Tests for `create_case_from_petition` — Phase 1 of the unfiled-petitions epic.

Covers both lifecycles routed by the LLM's structured output:

  - **filed**  (metadata.case_number is a real string): row created with
    `status='filed'`, UUID id, sanitized-case_number `resource_key`,
    R2 keyed off the resource_key, pgvector collections populated.
  - **unfiled** (metadata.case_number is None): row created with
    `status='unfiled'`, UUID id, NULL collection columns, R2 keyed off the
    UUID, PdfIndexer + EmailIndexer NEVER called.

Also covers duplicate-case_number 409 (both pre-INSERT find probe + the
DB IntegrityError fallback) and SSN extraction wiring.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from src.core.agents.llm.case_ingestion import CaseMetadata
from src.core.components.cases import service as service_module
from src.core.components.cases.service import create_case_from_petition


def _metadata(case_number: str | None = "0:26-bk-10700") -> CaseMetadata:
    return CaseMetadata(
        case_number=case_number,
        debtors=["Sarah Aurea Jensen"],
        chapter=7,
        court_district="S.D. Fla.",
    )


def _patch_agents(monkeypatch, *, metadata: CaseMetadata, ssn=("1879", "found")):
    """Stub the LLM ingestion agent + SSN extractor with fixed outputs."""
    monkeypatch.setattr(
        service_module.CaseIngestionAgent,
        "run",
        AsyncMock(return_value=metadata),
    )
    monkeypatch.setattr(
        service_module, "extract_ssn_last_four", lambda _b: ssn,
    )


def _patch_r2(monkeypatch):
    """Stub R2 so we can assert the key used + skip real network calls."""
    monkeypatch.setattr(
        service_module.r2_service, "upload_file", AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        service_module.r2_service,
        "get_presigned_url",
        AsyncMock(return_value="https://r2.example/petition.pdf"),
    )


def _patch_indexers(monkeypatch):
    """Track whether the indexers are called (must NOT fire on unfiled)."""
    pdf_index = AsyncMock(return_value=12)
    email_index = AsyncMock(return_value=(3, 5))
    monkeypatch.setattr(service_module.PdfIndexer, "index", pdf_index)
    monkeypatch.setattr(service_module.EmailIndexer, "index", email_index)
    return pdf_index, email_index


@pytest.mark.unit
async def test_filed_petition_creates_uuid_id_with_sanitized_resource_key(monkeypatch):
    """Filed petition (LLM returns a case_number) → status='filed', UUID
    id, resource_key derived from sanitized case_number, indexers fire."""
    _patch_agents(monkeypatch, metadata=_metadata("0:26-bk-10700"))
    _patch_r2(monkeypatch)
    pdf_index, email_index = _patch_indexers(monkeypatch)

    created_case = MagicMock()
    create_mock = AsyncMock(return_value=created_case)
    monkeypatch.setattr(service_module.CaseRepository, "create", create_mock)
    monkeypatch.setattr(
        service_module.CaseRepository,
        "get_by_case_number",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        service_module.CaseResponse,
        "from_orm_case",
        lambda c: service_module.CaseResponse(id="any", case_name="x"),
    )

    await create_case_from_petition(
        filename="x.pdf", pdf_bytes=b"%PDF-1.4", firm_id="firm-1",
    )

    # Assertions on CaseRepository.create kwargs:
    call_kwargs = create_mock.await_args.kwargs
    assert call_kwargs["status"] == "filed"
    assert call_kwargs["case_number"] == "26-10700"  # normalized
    assert call_kwargs["case_number_original"] == "0:26-bk-10700"
    assert call_kwargs["resource_key"] == "26_10700"  # sanitized
    assert call_kwargs["firm_id"] == "firm-1"
    assert call_kwargs["ssn_last4"] == "1879"
    assert call_kwargs["ssn_extraction_status"] == "found"
    # id is a UUID, not a sanitized slug:
    case_id = call_kwargs["case_id"]
    assert len(case_id) == 36 and case_id.count("-") == 4
    # Indexers DID fire on filed path, scoped to the same resource_key:
    pdf_index.assert_awaited_once()
    assert pdf_index.await_args.kwargs["resource_key"] == "26_10700"
    email_index.assert_awaited_once()
    assert email_index.await_args.kwargs["resource_key"] == "26_10700"


@pytest.mark.unit
async def test_unfiled_petition_creates_uuid_row_with_null_collections(monkeypatch):
    """Unfiled petition (LLM returns case_number=None) → status='unfiled',
    UUID id, resource_key=None, collection columns stay NULL,
    indexers are NEVER called.
    """
    _patch_agents(monkeypatch, metadata=_metadata(case_number=None))
    _patch_r2(monkeypatch)
    pdf_index, email_index = _patch_indexers(monkeypatch)

    created_case = MagicMock()
    create_mock = AsyncMock(return_value=created_case)
    monkeypatch.setattr(service_module.CaseRepository, "create", create_mock)
    # get_by_case_number must NOT be called on the unfiled path — case_number
    # is None so dedup is meaningless. Wire a tripwire mock.
    get_by_cn = AsyncMock(side_effect=AssertionError("dedup probe must not fire on unfiled"))
    monkeypatch.setattr(service_module.CaseRepository, "get_by_case_number", get_by_cn)
    monkeypatch.setattr(
        service_module.CaseResponse,
        "from_orm_case",
        lambda c: service_module.CaseResponse(id="any", case_name="x"),
    )

    await create_case_from_petition(
        filename="draft.pdf", pdf_bytes=b"%PDF-1.4", firm_id="firm-1",
    )

    call_kwargs = create_mock.await_args.kwargs
    assert call_kwargs["status"] == "unfiled"
    assert call_kwargs["case_number"] is None
    assert call_kwargs["case_number_original"] is None
    assert call_kwargs["resource_key"] is None
    assert call_kwargs["firm_id"] == "firm-1"
    assert call_kwargs["ssn_last4"] == "1879"
    case_id = call_kwargs["case_id"]
    assert len(case_id) == 36 and case_id.count("-") == 4
    # Indexers MUST NOT fire on unfiled:
    pdf_index.assert_not_awaited()
    email_index.assert_not_awaited()


@pytest.mark.unit
async def test_filed_petition_409_when_case_number_already_exists(monkeypatch):
    """find_by_case_number returns a row → 409 before R2 / create touched."""
    _patch_agents(monkeypatch, metadata=_metadata("0:26-bk-10700"))
    _patch_r2(monkeypatch)
    _patch_indexers(monkeypatch)

    monkeypatch.setattr(
        service_module.CaseRepository,
        "get_by_case_number",
        AsyncMock(return_value=MagicMock(id="some-uuid")),
    )
    create_mock = AsyncMock()
    monkeypatch.setattr(service_module.CaseRepository, "create", create_mock)

    with pytest.raises(HTTPException) as exc:
        await create_case_from_petition(
            filename="x.pdf", pdf_bytes=b"%PDF-1.4", firm_id="firm-1",
        )

    assert exc.value.status_code == 409
    create_mock.assert_not_awaited()


@pytest.mark.unit
async def test_filed_petition_409_when_integrity_error_on_race(monkeypatch):
    """Pre-INSERT probe missed, but the partial UNIQUE on case_number
    raised IntegrityError → translated to 409, indexers don't fire."""
    _patch_agents(monkeypatch, metadata=_metadata("0:26-bk-10700"))
    _patch_r2(monkeypatch)
    pdf_index, email_index = _patch_indexers(monkeypatch)

    monkeypatch.setattr(
        service_module.CaseRepository,
        "get_by_case_number",
        AsyncMock(return_value=None),  # probe says "not there"
    )
    monkeypatch.setattr(
        service_module.CaseRepository,
        "create",
        AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("uq_cases_case_number"))),
    )

    with pytest.raises(HTTPException) as exc:
        await create_case_from_petition(
            filename="x.pdf", pdf_bytes=b"%PDF-1.4", firm_id="firm-1",
        )

    assert exc.value.status_code == 409
    pdf_index.assert_not_awaited()
    email_index.assert_not_awaited()


@pytest.mark.unit
async def test_unfiled_petition_persists_petition_pdf_url(monkeypatch):
    """Unfiled rows still get a presigned petition URL — the PDF is uploaded
    so paralegals can view it later, just no pgvector indexing."""
    _patch_agents(monkeypatch, metadata=_metadata(case_number=None))
    _patch_r2(monkeypatch)
    _patch_indexers(monkeypatch)

    created_case = MagicMock()
    monkeypatch.setattr(
        service_module.CaseRepository, "create",
        AsyncMock(return_value=created_case),
    )
    monkeypatch.setattr(
        service_module.CaseResponse,
        "from_orm_case",
        lambda c: service_module.CaseResponse(
            id="any",
            case_name="x",
            petition_pdf_url=c.petition_pdf_url,
        ),
    )

    response = await create_case_from_petition(
        filename="draft.pdf", pdf_bytes=b"%PDF-1.4", firm_id="firm-1",
    )

    # The URL got set on the returned ORM-mock after R2 upload.
    assert created_case.petition_pdf_url == "https://r2.example/petition.pdf"
    assert response.case_file_chunks_indexed == 0
    assert response.gmail_emails_indexed == 0
    assert response.courtdrive_emails_indexed == 0
