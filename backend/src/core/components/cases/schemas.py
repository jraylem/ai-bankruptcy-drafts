"""HTTP response schemas for the /cases endpoints."""

from pydantic import BaseModel

from src.core.common.storage.database import Case


class CaseResponse(BaseModel):
    """Pydantic mirror of the Case ORM row for API responses.

    `case_number` and the three `*_collection` fields are nullable to
    support unfiled cases (no docket number yet → no resource_key → no
    pgvector collections). `status` discriminates filed vs unfiled so
    the FE can decide what to render.
    """
    id: str
    firm_id: str | None = None
    legacy_id: str | None = None
    case_name: str
    case_number: str | None = None
    case_number_original: str | None = None
    court_district: str | None = None
    chapter: int | None = None
    petition_pdf_url: str | None = None
    case_file_collection: str | None = None
    gmail_collection: str | None = None
    courtdrive_collection: str | None = None
    ssn_last4: str | None = None
    ssn_extraction_status: str = "not_found"
    status: str = "filed"

    @classmethod
    def from_orm_case(cls, case: Case) -> "CaseResponse":
        """Build a CaseResponse from a Case ORM row."""
        return cls(
            id=case.id,
            firm_id=case.firm_id,
            legacy_id=case.legacy_id,
            case_name=case.case_name,
            case_number=case.case_number,
            case_number_original=case.case_number_original,
            court_district=case.court_district,
            chapter=case.chapter,
            petition_pdf_url=case.petition_pdf_url,
            case_file_collection=case.case_file_collection,
            gmail_collection=case.gmail_collection,
            courtdrive_collection=case.courtdrive_collection,
            ssn_last4=case.ssn_last4,
            # ORM column defaults only apply on INSERT, so freshly-built
            # Case() instances (and pre-Phase-1 rows briefly during the
            # migration window) may have these as None. Coerce to the
            # documented defaults so the wire format is always populated.
            ssn_extraction_status=case.ssn_extraction_status or "not_found",
            status=case.status or "filed",
        )


class CaseListResponse(BaseModel):
    """Paginated response for GET /core/cases. `petition_pdf_url` on each
    returned case is freshly re-signed (1h TTL) so the FE can render the
    PDF directly without per-case round-trips. `has_more` lets the FE
    drive a Load More button without computing offsets itself."""

    cases: list[CaseResponse]
    total: int
    limit: int
    offset: int
    has_more: bool


class CaseCreateResponse(BaseModel):
    """Response body for POST /core/cases."""
    case: CaseResponse
    case_file_chunks_indexed: int
    gmail_emails_indexed: int
    courtdrive_emails_indexed: int


class CasePetitionUrlResponse(BaseModel):
    """Response body for GET /core/cases/{case_id}/petition-url.

    Returns a freshly-signed R2 URL for the case's petition PDF. The
    `petition_pdf_url` field on a Case row is signed at case-creation
    time and goes stale once the URL's TTL elapses — this endpoint is
    the source of truth for previewing the petition later in the
    case's lifecycle.
    """
    petition_pdf_url: str


class SupportingDocUploadResponse(BaseModel):
    """Response body for POST /core/cases/{case_id}/supporting-docs.

    Two URL fields serve two different purposes:

      - `file_url` is the raw R2 key (e.g.
        'cases/26_10700/supporting_docs/<uuid>.pdf'). The FE echoes this
        back in a SupportingDocsPick.file_urls on resume; it must live
        under the case's supporting_docs prefix or the resolver rejects
        the pick.
      - `presigned_url` is a time-limited signed URL the FE can use
        immediately to render a preview of the uploaded file (thumbnail,
        'open in new tab', etc.). Expires in ~1h; NOT suitable for
        long-term storage or persistence.
    """
    file_url: str
    presigned_url: str
    filename: str
