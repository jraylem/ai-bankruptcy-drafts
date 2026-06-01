import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.gmail import workflow_services
from src.chatbot import pending_petitions as pending_petitions_module
from src.gmail.workflow_services import (
    DocumentStorageService,
    EmailIngestionService,
    PDFParsingService,
    PetitionService,
    ScheduleMergeService,
    is_initial_schedules_subject,
)


def test_build_trigger_query_includes_sender_case_and_after():
    query = EmailIngestionService._build_trigger_query(
        ["BKECF@flnb.uscourts.gov", "bnc@flmb.uscourts.gov"],
        "26-00886",
        1700000000,
    )

    assert "from:BKECF@flnb.uscourts.gov" in query
    assert "from:bnc@flmb.uscourts.gov" in query
    assert '"26-00886"' in query
    assert "after:1700000000" in query


def test_extract_case_number_prefers_court_format():
    parser = PDFParsingService()
    text = "Case Number: 3:26-bk-00886 and alternate 26-00886"
    assert parser._extract_case_number(text, "") == "26-00886"


def test_extract_ssn_last4_handles_masked_formats():
    parser = PDFParsingService()
    assert parser._extract_ssn_last4("SSN: xxx-xx-1234") == "1234"
    assert parser._extract_ssn_last4("SSN: xxx – xx – 9 8 2 3") == "9823"


def test_petition_service_uses_uploads_before_court_mail(tmp_path, monkeypatch):
    upload_file = tmp_path / "Bankruptcy_Petition_John_Doe_26-11993_1234.pdf"
    upload_file.write_bytes(b"%PDF-1.4\n%test")

    monkeypatch.setattr(
        workflow_services,
        "scan_uploaded_petition_identities",
        lambda **_kwargs: {
            "status": "completed",
            "records": [
                {
                    "path": str(upload_file),
                    "case_number": "26-11993",
                    "client_name": "John Doe",
                    "ssn_last4": "1234",
                }
            ],
        },
    )

    class FakeEmailIngestion:
        async def fetch_petition_attachment_for_case(self, **kwargs):
            raise AssertionError("Court mail fallback should not run when uploads match")

    petition_service = PetitionService(email_ingestion_service=FakeEmailIngestion())
    result = asyncio.run(
        petition_service.retrieve_petition_for_case(
            case_number="26-11993",
            debtor_name="John Doe",
            ssn_last4="1234",
            sender_emails=None,
            max_results=25,
        )
    )
    assert result["source"] == "uploads"


def test_petition_service_returns_manual_upload_error_when_not_found(monkeypatch):
    monkeypatch.setattr(
        workflow_services,
        "scan_uploaded_petition_identities",
        lambda **_kwargs: {"status": "completed", "records": []},
    )

    class FakeEmailIngestion:
        async def fetch_petition_attachment_for_case(self, **kwargs):
            return None

    petition_service = PetitionService(email_ingestion_service=FakeEmailIngestion())

    with pytest.raises(ValueError, match="Petition not found. Please upload the petition manually."):
        asyncio.run(
            petition_service.retrieve_petition_for_case(
                case_number="26-11993",
                debtor_name="John Doe",
                ssn_last4="1234",
                sender_emails=None,
                max_results=25,
            )
        )


def test_document_storage_service_stores_pdf_directly_in_case_documents(tmp_path):
    storage = DocumentStorageService(
        root_dir=tmp_path,
        archive_root=tmp_path / "archive_sync",
    )
    stored = storage.store_document(
        session_id="session-123",
        case_number="26-11993",
        filename="petition.pdf",
        payload=b"%PDF-1.4\n%x",
        document_type="petition",
        source="unit_test",
    )

    stored_path = Path(stored["path"])
    assert stored_path.parent == tmp_path
    assert stored_path.exists()
    assert "__sid_" in stored_path.name


def test_document_storage_service_archives_flat_with_unique_names(tmp_path, monkeypatch):
    case_root = tmp_path / "case_documents"
    archive_root = tmp_path / "archive_sync"
    storage = DocumentStorageService(root_dir=case_root, archive_root=archive_root)

    legacy_dir = case_root / "session-123"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    legacy_file = legacy_dir / "petition.pdf"
    legacy_file.write_bytes(b"legacy")

    flat_file = case_root / "20260101010101__sid_session-123__case_2611993__petition.pdf"
    flat_file.write_bytes(b"flat")

    existing_archive_file = archive_root / "petition.pdf"
    existing_archive_file.write_bytes(b"existing")

    class FakePDF:
        def __init__(self, file_path: str):
            self.file_path = file_path

    async def fake_get_session_pdfs(session_id: str):
        assert session_id == "session-123"
        return [FakePDF(str(flat_file))]

    monkeypatch.setattr(workflow_services, "get_session_pdfs", fake_get_session_pdfs)
    from src.utils import sftp as sftp_module

    def fake_push_file(local_path: str, dest_filename: str) -> bool:
        destination = archive_root / dest_filename
        destination.write_bytes(Path(local_path).read_bytes())
        return True

    monkeypatch.setattr(sftp_module.sftp_client, "push_file", fake_push_file)

    result = asyncio.run(storage.archive_case_documents("session-123", reason="manual"))

    archived_paths = [archive_root / path for path in result["archived_files"]]
    assert archived_paths
    assert all(path.exists() for path in archived_paths)
    assert all(path.parent == archive_root for path in archived_paths)
    assert all("session-123" not in str(path.parent) for path in archived_paths)
    assert (archive_root / "petition.pdf").exists()
    assert any("__sid_session-123__" in path.name for path in archived_paths)


def test_move_petition_file_keeps_existing_destination_file(tmp_path):
    active_root = tmp_path / "active"
    active_root.mkdir(parents=True, exist_ok=True)

    existing_dest = active_root / "petition.pdf"
    existing_dest.write_bytes(b"existing")

    source_dir = tmp_path / "incoming"
    source_dir.mkdir(parents=True, exist_ok=True)
    source_file = source_dir / "petition.pdf"
    source_file.write_bytes(b"new")

    moved_path = Path(workflow_services._move_petition_file(source_file, active_root))

    assert existing_dest.read_bytes() == b"existing"
    assert moved_path != existing_dest
    assert moved_path.name == "petition_1.pdf"
    assert moved_path.read_bytes() == b"new"


# ---------------------------------------------------------------------------
# Initial Schedules Filed — subject matching
# ---------------------------------------------------------------------------

def test_is_initial_schedules_subject_matches_exact():
    assert is_initial_schedules_subject("Initial Schedules Filed: 26-00886") is True


def test_is_initial_schedules_subject_case_insensitive():
    assert is_initial_schedules_subject("INITIAL SCHEDULES FILED: Jane Doe") is True
    assert is_initial_schedules_subject("initial schedules filed: case 26-01234") is True


def test_is_initial_schedules_subject_allows_extra_text_after_colon():
    assert is_initial_schedules_subject(
        "Initial Schedules Filed: Debtor John Doe, Case No. 26-00886"
    ) is True


def test_is_initial_schedules_subject_rejects_non_matching_subjects():
    assert is_initial_schedules_subject("Voluntary Petition Filed: John Doe") is False
    assert is_initial_schedules_subject("Initial Schedules") is False  # missing colon
    assert is_initial_schedules_subject("") is False
    assert is_initial_schedules_subject("RE: Schedules Filed") is False


def test_email_ingestion_service_static_method_delegates_to_module_function():
    # The static method on EmailIngestionService must agree with the module-level function
    subject = "Initial Schedules Filed: 26-00886"
    assert EmailIngestionService._is_initial_schedules_subject(subject) is True
    assert EmailIngestionService._is_initial_schedules_subject("Voluntary Petition") is False


# ---------------------------------------------------------------------------
# Initial Schedules Filed — merge invocation (end-to-end with fakes)
# ---------------------------------------------------------------------------

def _make_gmail_message(message_id: str, subject: str, case_number: str) -> dict:
    """Build a minimal fake Gmail message dict."""
    return {
        "id": message_id,
        "threadId": f"thread_{message_id}",
        "snippet": f"Case {case_number}",
        "payload": {
            "headers": [
                {"name": "Subject", "value": subject},
                {"name": "From", "value": "BKECF@flnb.uscourts.gov"},
                {"name": "Date", "value": "Wed, 25 Mar 2026 10:00:00 -0500"},
            ],
            "parts": [
                {
                    "mimeType": "application/pdf",
                    "filename": "schedules_ab.pdf",
                    "body": {
                        "data": "JVBERi0xLjQK",  # minimal base64-encoded PDF header
                    },
                }
            ],
        },
    }


class _FakeGmailService:
    """Minimal Gmail API stub that returns a single pre-canned message."""

    def __init__(self, message: dict):
        self._message = message

    def users(self):
        return self

    def messages(self):
        return self

    def get(self, **_kwargs):
        return self

    def execute(self):
        return self._message


def test_ingest_message_invokes_schedule_merge_service(tmp_path, monkeypatch):
    """Initial Schedules emails should be delegated into the auto-merge service."""
    merge_calls: list[dict] = []

    class FakeStorage:
        def store_document(self, **_kwargs):
            raise AssertionError("EmailIngestionService should not directly store schedule attachments")

    class FakePetitionService:
        async def ingest_petition_attachment(self, **_kwargs):
            raise AssertionError("ingest_petition_attachment must not be called for schedule events")

    class FakeScheduleMergeService:
        async def merge_initial_schedules(self, **kwargs):
            merge_calls.append(kwargs)
            return {
                "status": "merged_schedule",
                "stored_documents": [
                    {
                        "path": str(tmp_path / "schedules_ab.pdf"),
                        "size_bytes": 10,
                    }
                ],
            }

    async def fake_get_ingestion_status(_session_id, _ingestion_type):
        return None  # not previously processed

    async def fake_create_or_update_ingestion(**_kwargs):
        return True

    monkeypatch.setattr(workflow_services, "get_ingestion_status", fake_get_ingestion_status)
    monkeypatch.setattr(workflow_services, "create_or_update_ingestion", fake_create_or_update_ingestion)

    svc = EmailIngestionService(
        storage_service=FakeStorage(),
        petition_service=FakePetitionService(),
        schedule_merge_service=FakeScheduleMergeService(),
    )

    message = _make_gmail_message(
        message_id="msg_sched_001",
        subject="Initial Schedules Filed: 26-00886 Jane Doe",
        case_number="26-00886",
    )
    gmail_stub = _FakeGmailService(message)

    result = asyncio.run(
        svc._ingest_message_for_trigger(
            gmail_service=gmail_stub,
            session_id="session-abc",
            case_number="26-00886",
            message_id="msg_sched_001",
        )
    )

    assert result["scanned"] == 1
    assert result["stored_docs"] == 1
    assert result["petition_events"] == 0
    assert result["schedule_merge_events"] == 1

    assert len(merge_calls) == 1
    assert merge_calls[0]["target_session_id"] == "session-abc"
    assert merge_calls[0]["case_number"] == "26-00886"
    assert [item["filename"] for item in merge_calls[0]["attachments"]] == ["schedules_ab.pdf"]


def test_ingest_message_skips_already_processed(monkeypatch):
    """A message whose ingestion record is already 'completed' must be skipped (idempotency)."""

    async def fake_get_ingestion_status(_session_id, _ingestion_type):
        return {"status": "completed"}

    monkeypatch.setattr(workflow_services, "get_ingestion_status", fake_get_ingestion_status)

    svc = EmailIngestionService()

    # Pass a stub that would blow up if actually called
    class BoomGmail:
        def users(self):
            raise AssertionError("Gmail API must not be called for already-processed messages")

    result = asyncio.run(
        svc._ingest_message_for_trigger(
            gmail_service=BoomGmail(),
            session_id="session-xyz",
            case_number="26-00886",
            message_id="alreadydone_msg_001",
        )
    )

    assert result == {"scanned": 0, "stored_docs": 0, "petition_events": 0, "schedule_merge_events": 0}


def test_ingest_message_petition_not_affected_by_schedule_trigger(tmp_path, monkeypatch):
    """A petition attachment in a non-schedule email must still call ingest_petition_attachment."""
    petition_ingested: list[str] = []
    schedule_merge_calls: list[dict] = []

    class FakeStorage:
        def store_document(self, **kwargs):
            return {"path": str(tmp_path / kwargs["filename"]), "size_bytes": 10}

    class FakePetitionService:
        async def ingest_petition_attachment(self, **kwargs):
            petition_ingested.append(kwargs["attachment_filename"])
            return {"status": "completed"}

    class FakeScheduleMergeService:
        async def merge_initial_schedules(self, **kwargs):
            schedule_merge_calls.append(kwargs)
            return {"stored_documents": []}

    async def fake_get_ingestion_status(_session_id, _ingestion_type):
        return None

    async def fake_create_or_update_ingestion(**_kwargs):
        return True

    monkeypatch.setattr(workflow_services, "get_ingestion_status", fake_get_ingestion_status)
    monkeypatch.setattr(workflow_services, "create_or_update_ingestion", fake_create_or_update_ingestion)

    svc = EmailIngestionService(
        storage_service=FakeStorage(),
        petition_service=FakePetitionService(),
        schedule_merge_service=FakeScheduleMergeService(),
    )

    # Subject does NOT match schedules pattern — filename contains "petition"
    message = _make_gmail_message(
        message_id="msg_pet_002",
        subject="Voluntary Petition Filed: 26-00886 Jane Doe",
        case_number="26-00886",
    )
    # Rename the attachment part to look like a petition
    message["payload"]["parts"][0]["filename"] = "voluntary_petition.pdf"
    gmail_stub = _FakeGmailService(message)

    result = asyncio.run(
        svc._ingest_message_for_trigger(
            gmail_service=gmail_stub,
            session_id="session-def",
            case_number="26-00886",
            message_id="msg_pet_002",
        )
    )

    assert result["petition_events"] == 1
    assert result["schedule_merge_events"] == 0
    assert petition_ingested == ["voluntary_petition.pdf"]
    assert schedule_merge_calls == []


def test_schedule_merge_service_reuses_existing_merge_schedule_logic(tmp_path, monkeypatch):
    """The schedule merge service must stage docs and call the existing merge_schedule resolver."""
    stored_calls: list[dict] = []
    saved_pdf_calls: list[dict] = []
    ingestion_calls: list[dict] = []
    resolution_calls: list[dict] = []
    thread_updates: list[dict] = []

    class FakeStorage:
        def store_document(self, **kwargs):
            stored_calls.append(kwargs)
            filename = kwargs["filename"]
            stored_path = tmp_path / filename
            stored_path.write_bytes(kwargs["payload"])
            return {
                "path": str(stored_path),
                "size_bytes": len(kwargs["payload"]),
                "filename": filename,
            }

    async def fake_get_session(_session_id):
        return SimpleNamespace(id="target-session", user_id="user-123")

    async def fake_get_session_chat_thread(_session_id, include_inactive=True):
        assert include_inactive is True
        return SimpleNamespace(id="thread-123", title="Jane Doe", case_number="26-00886")

    async def fake_create_session(user_id=None):
        assert user_id == "user-123"
        return SimpleNamespace(id="pending-session", user_id=user_id)

    async def fake_create_or_update_chat_thread(session_id: str):
        assert session_id == "pending-session"
        return SimpleNamespace(id="pending-thread", session_id=session_id)

    async def fake_update_thread_metadata(thread_id: str, **kwargs):
        thread_updates.append({"thread_id": thread_id, **kwargs})
        return True

    async def fake_save_pdf_metadata(**kwargs):
        saved_pdf_calls.append(kwargs)
        return SimpleNamespace(
            id="pdf-123",
            filename=kwargs["filename"],
            original_filename=kwargs["original_filename"],
            file_path=kwargs["file_path"],
            file_size=kwargs["file_size"],
            uploaded_at=None,
            inbox_checked_at=None,
            petition_status=kwargs.get("petition_status"),
            is_active=True,
        )

    async def fake_create_or_update_ingestion(**kwargs):
        ingestion_calls.append(kwargs)
        return True

    async def fake_set_thread_active(self, thread_id: str, is_active: bool):
        assert thread_id == "pending-thread"
        assert is_active is False

    class FakeResolutionService:
        async def resolve(self, pending_session_id: str, **kwargs):
            resolution_calls.append(
                {
                    "pending_session_id": pending_session_id,
                    **kwargs,
                }
            )
            return {
                "status": "merged_schedule",
                "action": "merge_schedule",
                "target_session_id": kwargs["target_session_id"],
            }

    monkeypatch.setattr(workflow_services, "get_session", fake_get_session)
    monkeypatch.setattr(workflow_services, "get_session_chat_thread", fake_get_session_chat_thread)
    monkeypatch.setattr(workflow_services, "create_session", fake_create_session)
    monkeypatch.setattr(workflow_services, "create_or_update_chat_thread", fake_create_or_update_chat_thread)
    monkeypatch.setattr(workflow_services, "update_thread_metadata", fake_update_thread_metadata)
    monkeypatch.setattr(workflow_services, "save_pdf_metadata", fake_save_pdf_metadata)
    monkeypatch.setattr(workflow_services, "create_or_update_ingestion", fake_create_or_update_ingestion)
    monkeypatch.setattr(
        workflow_services,
        "extract_ssn_from_uploaded_petition_pdfs",
        lambda _session_id: {"status": "completed", "ssn_last4": "1234"},
    )
    monkeypatch.setattr(ScheduleMergeService, "_set_thread_active", fake_set_thread_active)
    monkeypatch.setattr(
        pending_petitions_module,
        "PendingPetitionResolutionService",
        FakeResolutionService,
    )

    svc = ScheduleMergeService(storage_service=FakeStorage())

    result = asyncio.run(
        svc.merge_initial_schedules(
            target_session_id="target-session",
            case_number="26-00886",
            email_metadata={
                "subject": "Initial Schedules Filed: 26-00886 Jane Doe",
                "date": "Wed, 25 Mar 2026 10:00:00 -0500",
            },
            attachments=[
                {
                    "filename": "schedules_ab.pdf",
                    "bytes": b"%PDF-1.4\nSchedule A/B",
                }
            ],
        )
    )

    assert result["status"] == "merged_schedule"
    assert stored_calls[0]["document_type"] == "schedule_filed"
    assert stored_calls[0]["filename"] == "schedules_ab.pdf"
    assert saved_pdf_calls[0]["petition_status"] == "pending_acceptance"
    assert ingestion_calls[0]["ingestion_type"] == "pending_acceptance"
    assert thread_updates[0]["title"] == "Jane Doe"
    assert resolution_calls == [
        {
            "pending_session_id": "pending-session",
            "action": "merge_schedule",
            "user_id": "user-123",
            "target_session_id": "target-session",
            "client_name": "Jane Doe",
            "ssn_last4": "1234",
            "case_number": "26-00886",
        }
    ]
