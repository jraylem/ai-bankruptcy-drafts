"""PDF upload routes for the chatbot module."""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Request, Depends, Query
from fastapi.responses import StreamingResponse
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from sqlalchemy import text
from ..schema import PDFUploadResponse
from ..auth.auth import get_current_user
from ..auth.models import User
from .service import process_pdf_upload
from .database import (
    get_session,
    create_session_with_id,
    save_pdf_metadata,
    create_or_update_session_pdf_metadata,
    create_or_update_chat_thread,
    update_thread_metadata as db_update_thread_metadata,
    log_user_action,
    get_session_pdfs,
    AsyncSessionLocal
)
from .vectorestore import process_uploaded_file, clear_collection
from .pending_petitions import _resolve_managed_path
from ..auth.models import User
from ..common.dependencies import get_current_firm_user
from ..billing.service import report_usage_event
from ..courtdrive.service import (
    normalize_to_short_case_number,
    extract_district_from_pdf_path,
    extract_debtor_name_from_pdf_via_session_extractor,
    _extract_case_number_from_pdf_directly,
)
from ..gmail.service import ingest_gmail_emails_for_session
from ..gmail.workflow_services import CourtMailTriggerService

router = APIRouter()

# PDF storage directories
PDF_STORAGE_DIR = "uploads"
ACTIVE_UPLOADS_DIR = "uploads/active"
os.makedirs(PDF_STORAGE_DIR, exist_ok=True)
os.makedirs(ACTIVE_UPLOADS_DIR, exist_ok=True)

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


def _resolve_session_pdf_path(path: str) -> Path:
    """Resolve stored PDF paths consistently across uploads/, uploads/active/, and absolute paths."""
    candidate = (path or "").strip()
    if not candidate:
        return Path()

    parsed = Path(candidate)
    if candidate.startswith("/uploads/"):
        return (_BACKEND_ROOT / candidate.lstrip("/")).resolve()
    if parsed.is_absolute():
        return parsed.resolve()
    if parsed.parts and parsed.parts[0] == "uploads":
        return (_BACKEND_ROOT / parsed).resolve()
    return (_BACKEND_ROOT / PDF_STORAGE_DIR / parsed).resolve()


async def _background_gmail_ingest(
    session_id: str,
    case_number: str,
    debtor_name: str,
    user_id: str | None = None,
    firm_id: str | None = None,
):
    """Run Gmail ingestion in the background (trigger registration happens synchronously)."""
    loop = asyncio.get_running_loop()
    try:
        print(f"DEBUG: [background] Fetching Gmail emails for case {case_number}")
        gmail_result = await loop.run_in_executor(
            None, ingest_gmail_emails_for_session, session_id, case_number, debtor_name
        )
        print(f"DEBUG: [background] Gmail ingestion result: {gmail_result.get('status')} - {gmail_result.get('message', '')}")
        result_payload = gmail_result.get("result", {}) if isinstance(gmail_result.get("result"), dict) else {}
        await log_user_action(
            action="gmail_ingest",
            user_id=user_id,
            session_id=session_id,
            firm_id=firm_id,
            metadata={
                "case_number": case_number,
                "source": "upload_pdf",
                "status": gmail_result.get("status"),
                "emails_scanned": result_payload.get("total_emails_found", 0),
                "documents_stored": result_payload.get("total_documents_stored", 0),
            },
        )
    except Exception as gmail_err:
        print(f"DEBUG: [background] Gmail ingestion failed: {gmail_err}")


async def _background_ai_extraction(
    session_id: str,
    thread_id: str,
    pdf_path: str,
    needs_debtor: bool,
    needs_case: bool,
    needs_district: bool,
    user_id: str | None,
    current_case_number: str | None,
    current_debtor_name: str | None,
    firm_id: str | None = None,
) -> None:
    """AI-based fallback extraction for fields that fast regex couldn't resolve.

    Runs as an asyncio.create_task() after upload_pdf() returns. Writes to DB
    once all AI calls complete, which triggers the extraction-status SSE to fire.
    Also registers the court mail trigger and starts Gmail ingestion if the case
    number is resolved here for the first time.
    """
    loop = asyncio.get_running_loop()
    metadata_updates: dict = {}

    try:
        from ..courtdrive.service import (
            extract_debtor_name_for_session,
            extract_case_number_for_session,
        )

        futures: dict[str, asyncio.Future] = {}
        if needs_debtor:
            futures["debtor"] = loop.run_in_executor(None, extract_debtor_name_for_session, session_id)
        if needs_case:
            futures["case"] = loop.run_in_executor(None, extract_case_number_for_session, session_id)
        if needs_district:
            futures["district"] = loop.run_in_executor(None, extract_district_from_pdf_path, pdf_path)

        for key, fut in futures.items():
            try:
                result = await fut
                if key == "debtor":
                    if result.get("status") == "completed" and result.get("debtor_name"):
                        name = result["debtor_name"].strip().splitlines()[0][:60]
                        if name and name != "N/A":
                            metadata_updates["title"] = name
                elif key == "case":
                    if result.get("status") == "completed" and result.get("case_number"):
                        cn = normalize_to_short_case_number(result["case_number"].strip().splitlines()[0])
                        if cn and cn != "N/A":
                            metadata_updates["case_number"] = cn
                elif key == "district":
                    if result:
                        metadata_updates["district"] = result
            except Exception as e:
                print(f"DEBUG: AI fallback extraction failed for {key}: {e}")

        if metadata_updates:
            await db_update_thread_metadata(thread_id, **metadata_updates)
            print(f"DEBUG: AI fallback updated {list(metadata_updates)} for session {session_id}")

        final_debtor_name = metadata_updates.get("title") or current_debtor_name

        # Only register trigger + Gmail when AI is the one that resolved the case number
        # for the first time. If case_number came from current_case_number (fast path already
        # registered), skip — upload_pdf() already handled it.
        newly_resolved_case = metadata_updates.get("case_number")
        if newly_resolved_case and newly_resolved_case != "N/A":
            try:
                trigger_service = CourtMailTriggerService()
                await trigger_service.register_trigger(session_id=session_id, case_number=newly_resolved_case)
                print(f"DEBUG: AI fallback registered trigger for {session_id} / {newly_resolved_case}")
            except Exception as e:
                print(f"DEBUG: AI fallback trigger registration failed: {e}")

            asyncio.create_task(
                _background_gmail_ingest(session_id, newly_resolved_case, final_debtor_name or "", user_id, firm_id)
            )

    except Exception as e:
        print(f"DEBUG: _background_ai_extraction error: {e}")


def _looks_like_petition_pdf(filename: str, original_filename: str = "") -> bool:
    """Return True when a PDF entry appears to be the main petition document."""
    content = f"{filename}\n{original_filename}".lower()
    petition_markers = (
        "petition",
        "voluntary petition",
        "bankruptcy petition",
        "official form 101",
    )
    return any(marker in content for marker in petition_markers)


@router.post("/upload-pdf", response_model=PDFUploadResponse)
async def upload_pdf(
    request: Request,
    file: UploadFile = File(...),
    collection_name: str = Form("default_collection"),
    session_id: str = Form(...),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a PDF file and make it available for bankruptcy review processing.
    """
    print(f"DEBUG: PDF upload endpoint called by user: {current_user.email}")
    
    try:
        # Validate session exists or create new one
        session = await get_session(session_id)
        if not session:
            session = await create_session_with_id(session_id, user_id=current_user.id, firm_id=current_user.firm_id)
        
        # Process the PDF upload — save directly to the active directory so the
        # archiver (which only scans the flat uploads/ dir) never touches it.
        response, new_pdf_path = process_pdf_upload(
            file,
            collection_name,
            None,
            ACTIVE_UPLOADS_DIR,
            session_id
        )
        
        # Save PDF metadata to database (upsert — prevents duplicate rows on re-upload)
        await create_or_update_session_pdf_metadata(
            session_id=session_id,
            filename=response.filename,
            original_filename=file.filename,
            file_path=new_pdf_path,
            file_size=file.size,
            collection_name=collection_name,
            source="manual",
            petition_status="working",
        )
        await log_user_action(
            action="upload_pdf",
            user_id=current_user.id,
            session_id=session_id,
            firm_id=current_user.firm_id,
            metadata={"filename": file.filename, "file_size": file.size},
        )
        asyncio.create_task(report_usage_event(current_user.firm_id, "ingestion"))
        
        # Extract debtor name, case number, and district.
        # Fast path (pypdf + regex, no LLM) runs synchronously and completes in <1s.
        # If regex can't resolve a field, an AI fallback task runs in the background
        # after the response is returned, then writes to DB when done.
        final_case_number = None
        final_debtor_name = None
        try:
            chat_thread = await create_or_update_chat_thread(session_id)

            needs_title = not (chat_thread.title and chat_thread.title.strip() and chat_thread.title != "Untitled conversation")
            needs_case = not (chat_thread.case_number and chat_thread.case_number.strip() and chat_thread.case_number != "N/A")

            # Fast extraction — all regex/pypdf, no LLM, run concurrently in thread pool
            loop = asyncio.get_running_loop()
            debtor_future = loop.run_in_executor(None, extract_debtor_name_from_pdf_via_session_extractor, new_pdf_path, session_id) if needs_title else None
            case_future = loop.run_in_executor(None, _extract_case_number_from_pdf_directly, session_id) if needs_case else None
            district_future = loop.run_in_executor(None, extract_district_from_pdf_path, new_pdf_path, True)  # fast_only=True

            await asyncio.gather(*[f for f in [debtor_future, case_future, district_future] if f is not None])

            metadata_updates: dict = {}
            needs_ai_debtor = False
            needs_ai_case = False
            needs_ai_district = False

            if debtor_future:
                dr = await debtor_future
                if dr.get("status") == "completed" and dr.get("debtor_name"):
                    name = dr["debtor_name"].strip()
                    if name and name != "N/A":
                        clean = name.splitlines()[0].strip()[:60]
                        if clean:
                            metadata_updates["title"] = clean
                            print(f"DEBUG: Fast debtor name: {clean}")
                        else:
                            needs_ai_debtor = True
                    else:
                        needs_ai_debtor = True
                else:
                    needs_ai_debtor = True
            else:
                print(f"DEBUG: Thread already has title '{chat_thread.title}', skipping debtor extraction")

            if case_future:
                cr = await case_future
                if cr.get("status") == "completed" and cr.get("case_number"):
                    cn = cr["case_number"].strip()
                    if cn and cn != "N/A":
                        clean_cn = normalize_to_short_case_number(cn.splitlines()[0].strip())
                        if clean_cn:
                            metadata_updates["case_number"] = clean_cn
                            print(f"DEBUG: Fast case number: {clean_cn}")
                        else:
                            needs_ai_case = True
                    else:
                        needs_ai_case = True
                else:
                    needs_ai_case = True
            else:
                print(f"DEBUG: Thread already has case number '{chat_thread.case_number}', skipping extraction")

            district_result = await district_future
            if district_result:
                metadata_updates["district"] = district_result
                print(f"DEBUG: Fast district: {district_result}")
            else:
                needs_ai_district = True

            if metadata_updates:
                await db_update_thread_metadata(chat_thread.id, **metadata_updates)

            final_case_number = metadata_updates.get("case_number") or chat_thread.case_number
            final_debtor_name = metadata_updates.get("title") or chat_thread.title

            # Schedule AI fallback for any field regex couldn't resolve.
            # _background_ai_extraction writes to DB when done (fires SSE) and
            # registers the court mail trigger + Gmail if it resolves the case number.
            if needs_ai_debtor or needs_ai_case or needs_ai_district:
                asyncio.create_task(_background_ai_extraction(
                    session_id=session_id,
                    thread_id=chat_thread.id,
                    pdf_path=new_pdf_path,
                    needs_debtor=needs_ai_debtor,
                    needs_case=needs_ai_case,
                    needs_district=needs_ai_district,
                    user_id=current_user.id,
                    current_case_number=final_case_number,
                    current_debtor_name=final_debtor_name,
                    firm_id=current_user.firm_id,
                ))

            # Register trigger + Gmail only when case_number is already resolved.
            # If still pending AI, _background_ai_extraction handles this instead.
            if final_case_number and final_case_number != "N/A" and not needs_ai_case:
                try:
                    trigger_service = CourtMailTriggerService()
                    await trigger_service.register_trigger(
                        session_id=session_id,
                        case_number=final_case_number,
                    )
                    print(f"DEBUG: Court mail trigger registered for session {session_id} case {final_case_number}")
                except Exception as trigger_err:
                    print(f"DEBUG: Court mail trigger registration failed: {trigger_err}")

                asyncio.create_task(
                    _background_gmail_ingest(
                        session_id,
                        final_case_number,
                        final_debtor_name or "",
                        current_user.id,
                        current_user.firm_id,
                    )
                )

        except Exception as e:
            print(f"DEBUG: Error during fast extraction: {e}")
            # Don't fail the upload if extraction fails

        # Auto-merge any pending inbox entries that match this case (2-of-3).
        # Runs OUTSIDE the extraction try-block so it fires even when extraction fails.
        # The task re-parses the uploaded PDF directly to get the document's own
        # case_number / debtor_name / SSN, independent of the thread's stored values
        # (the thread may hold a different case number when uploading to an existing session).
        _pdf_snap = new_pdf_path
        _uid_snap = current_user.id
        _sid_snap = session_id
        _case_snap = final_case_number
        _name_snap = final_debtor_name

        async def _auto_merge_pending():
            try:
                from .pending_petitions import PendingPetitionResolutionService
                from ..gmail.workflow_services import PDFParsingService
                from pathlib import Path as _Path

                _case_for_merge = _case_snap
                _name_for_merge = _name_snap
                _ssn_for_merge = None

                pdf_file = _Path(_pdf_snap)
                if pdf_file.exists():
                    _loop = asyncio.get_event_loop()
                    pdf_bytes = await _loop.run_in_executor(None, pdf_file.read_bytes)
                    parsed = PDFParsingService().parse_petition_fields(
                        pdf_bytes, fallback_filename=pdf_file.name
                    )
                    if parsed.case_number:
                        _case_for_merge = parsed.case_number
                    if parsed.client_name:
                        _name_for_merge = parsed.client_name
                    if parsed.ssn_last4:
                        _ssn_for_merge = parsed.ssn_last4

                if not (_case_for_merge or _name_for_merge):
                    return

                svc = PendingPetitionResolutionService()
                merged = await svc.auto_merge_pending_on_case_match(
                    _sid_snap,
                    user_id=_uid_snap,
                    case_number=_case_for_merge,
                    debtor_name=_name_for_merge,
                    ssn_last4=_ssn_for_merge,
                )
                if merged:
                    print(f"DEBUG: auto_merge absorbed {len(merged)} pending session(s) into {_sid_snap}")
            except Exception as _exc:
                print(f"DEBUG: auto_merge_pending_on_case_match failed: {_exc}")
        asyncio.create_task(_auto_merge_pending())

        return response
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in PDF upload: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Upload error: {str(e)}")


@router.get("/sessions/{session_id}/extraction-status")
async def extraction_status_sse(
    session_id: str,
    request: Request,
    since: Optional[str] = Query(None, description="ISO-8601 timestamp; stream fires when updated_at is newer than this"),
    _user: User = Depends(get_current_firm_user),
):
    """
    SSE stream that emits one event when case metadata extraction completes.

    Connect immediately after POST /upload-pdf. Pass the thread's current
    updated_at (or the upload timestamp) as `since` — the stream will emit
    a `done` event as soon as the DB row is updated, or a `timeout` event
    after 35 seconds if nothing changes.

    Event payload: {"status": "done"|"timeout", "case_name", "case_number", "district"}
    """
    try:
        since_dt = datetime.fromisoformat(since).replace(tzinfo=timezone.utc) if since else datetime.now(timezone.utc)
    except ValueError:
        since_dt = datetime.now(timezone.utc)

    async def event_generator():
        poll_interval = 0.6  # seconds between DB checks
        timeout_secs = 35
        elapsed = 0.0

        while elapsed < timeout_secs:
            if await request.is_disconnected():
                return

            async with AsyncSessionLocal() as db:
                row = await db.execute(
                    text("""
                        SELECT title, case_number, district, updated_at
                        FROM chat_threads
                        WHERE session_id = :sid
                        ORDER BY created_at DESC
                        LIMIT 1
                    """),
                    {"sid": session_id},
                )
                thread = row.fetchone()

            if thread and thread.updated_at:
                # Ensure both sides are timezone-aware for comparison
                updated = thread.updated_at
                if updated.tzinfo is None:
                    updated = updated.replace(tzinfo=timezone.utc)

                if updated > since_dt:
                    payload = json.dumps({
                        "status": "done",
                        "case_name": thread.title,
                        "case_number": thread.case_number,
                        "district": thread.district,
                    })
                    yield f"data: {payload}\n\n"
                    return

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        yield f"data: {json.dumps({'status': 'timeout'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/sessions/{session_id}/pdfs")
async def get_session_pdfs_api(session_id: str, request: Request):  # Temporarily removed auth for testing
    """
    Get PDFs for a specific session.
    Merges results from the database (covers extract-petition flow) and
    filesystem scan (covers direct-upload flow) so both paths return PDFs.
    """
    try:
        import time

        base_url = str(request.base_url).rstrip("/")
        uploads_dir = Path(PDF_STORAGE_DIR)
        seen_stems = set()
        pdf_list = []

        # --- 1. Query the database for PDFs saved via save_pdf_metadata() ---
        try:
            db_pdfs = await get_session_pdfs(session_id)
            for db_pdf in db_pdfs:
                pdf_path = _resolve_session_pdf_path(db_pdf.file_path)
                if pdf_path.is_file():
                    seen_stems.add(pdf_path.stem)
                    stat = pdf_path.stat()
                    pdf_list.append({
                        "id": pdf_path.stem,
                        "filename": pdf_path.name,
                        "file_path": f"/uploads/{pdf_path.name}",
                        "download_url": f"{base_url}/api/pdf/{pdf_path.stem}/download",
                        "original_filename": db_pdf.original_filename or pdf_path.name,
                        "file_size": stat.st_size,
                        "uploaded_at": time.ctime(stat.st_mtime),
                        "_mtime": stat.st_mtime,
                    })
        except Exception as db_err:
            print(f"DB lookup failed for session {session_id}, falling back to filesystem: {db_err}")

        # --- 2. Filesystem scan for uploads that embed session_id in filename ---
        if uploads_dir.exists():
            fs_patterns = [
                f"*{session_id}*.pdf",
                f"bankruptcy_petition_{session_id}.pdf",
                f"petition_{session_id}.pdf",
            ]
            fs_files = []
            scan_dirs = [uploads_dir, Path(ACTIVE_UPLOADS_DIR)]
            for scan_dir in scan_dirs:
                if scan_dir.exists():
                    for pattern in fs_patterns:
                        fs_files.extend(scan_dir.glob(pattern))

            for pdf_file in set(fs_files):
                if pdf_file.is_file() and pdf_file.stem not in seen_stems:
                    seen_stems.add(pdf_file.stem)
                    stat = pdf_file.stat()
                    original_filename = pdf_file.stem
                    if f"_{session_id}" in original_filename:
                        original_filename = original_filename.replace(f"_{session_id}", "")
                    original_filename += ".pdf"
                    pdf_list.append({
                        "id": pdf_file.stem,
                        "filename": pdf_file.name,
                        "file_path": f"/uploads/{pdf_file.name}",
                        "download_url": f"{base_url}/api/pdf/{pdf_file.stem}/download",
                        "original_filename": original_filename,
                        "file_size": stat.st_size,
                        "uploaded_at": time.ctime(stat.st_mtime),
                        "_mtime": stat.st_mtime,
                    })

        # Sort: bankruptcy_petition first, then by modification time (newest first)
        def get_priority(p):
            mtime = -p.get("_mtime", 0)
            name = p["filename"].lower()
            original_name = (p.get("original_filename") or "").lower()
            if _looks_like_petition_pdf(name, original_name):
                return (0, mtime)
            elif name.startswith("objection_pdf_"):
                return (1, mtime)
            elif name.startswith("motion_pdf_"):
                return (2, mtime)
            return (3, mtime)

        pdf_list.sort(key=get_priority)

        print(f"Found {len(pdf_list)} PDFs for session {session_id}")
        return {
            "session_id": session_id,
            "pdfs": pdf_list
        }

    except Exception as e:
        print(f"Error getting PDFs for session {session_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get PDFs: {str(e)}")


@router.get("/pdf/{pdf_id}/download")
async def download_pdf(pdf_id: str):  # Temporarily removed auth for testing
    """
    Download a PDF file by filename (pdf_id is the filename without extension).
    """
    try:
        from fastapi.responses import FileResponse
        from sqlalchemy import text as sa_text
        from .database import AsyncSessionLocal

        # First: check uploads/ root directly
        file_path = Path(PDF_STORAGE_DIR) / f"{pdf_id}.pdf"

        # Second: check uploads/active/ — accepted petitions live here after
        # commit 67dee36 to keep them out of the archiver's sweep.
        if not file_path.exists():
            active_path = Path(ACTIVE_UPLOADS_DIR) / f"{pdf_id}.pdf"
            if active_path.exists():
                file_path = active_path

        # Third: check archived_petitions subdirectory
        if not file_path.exists():
            archived_path = Path(PDF_STORAGE_DIR) / "archived_petitions" / f"{pdf_id}.pdf"
            if archived_path.exists():
                file_path = archived_path

        # Fallback: look up the stored file_path in the DB
        if not file_path.exists():
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    sa_text(
                        "SELECT file_path FROM pdf_documents WHERE filename = :name OR filename = :name_pdf LIMIT 1"
                    ),
                    {"name": pdf_id, "name_pdf": f"{pdf_id}.pdf"},
                )
                row = result.fetchone()
                if row and row.file_path:
                    resolved = _resolve_managed_path(row.file_path)
                    if resolved:
                        file_path = resolved

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="PDF file not found")
        
        # Return the file
        return FileResponse(
            path=str(file_path),
            filename=f"{pdf_id}.pdf",
            media_type='application/pdf'
        )
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error downloading PDF {pdf_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Download error: {str(e)}")


@router.delete("/sessions/{session_id}/pdfs")
async def delete_session_pdfs(
    session_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """
    Delete all PDFs associated with a session ID.
    """
    print(f"DEBUG: PDF delete endpoint called for session {session_id} by user: {current_user.email}")
    
    try:
        from pathlib import Path
        import glob
        
        # Get all PDFs for this session — scan both uploads/ and uploads/active/
        uploads_dir = Path(PDF_STORAGE_DIR)
        active_uploads_dir = Path(ACTIVE_UPLOADS_DIR)

        pdf_patterns = [
            f"*{session_id}*.pdf",
            f"bankruptcy_petition_{session_id}.pdf",
            f"petition_{session_id}.pdf"
        ]

        pdf_files = []
        for scan_dir in [uploads_dir, active_uploads_dir]:
            if scan_dir.exists():
                for pattern in pdf_patterns:
                    pdf_files.extend(scan_dir.glob(pattern))
        
        # Remove duplicates
        pdf_files = list(set(pdf_files))
        
        deleted_count = 0
        deleted_files = []
        
        # Delete each PDF file
        for pdf_file in pdf_files:
            if pdf_file.is_file():
                try:
                    pdf_file.unlink()  # Delete the file
                    deleted_count += 1
                    deleted_files.append(pdf_file.name)
                    print(f"DEBUG: Deleted PDF file: {pdf_file.name}")
                except Exception as e:
                    print(f"DEBUG: Error deleting {pdf_file.name}: {e}")
        
        # Also mark PDFs as inactive in database
        async with AsyncSessionLocal() as session:
            try:
                await session.execute(
                    text("UPDATE pdf_documents SET is_active = false, petition_status = 'deleted' WHERE session_id = :session_id"),
                    {"session_id": session_id}
                )
                await session.commit()
                print(f"DEBUG: Marked PDFs as inactive in database for session {session_id}")
            except Exception as e:
                print(f"DEBUG: Error updating database: {e}")
                # Don't fail the whole operation if DB update fails
        
        print(f"DEBUG: Successfully deleted {deleted_count} PDFs for session {session_id}")
        return {
            "message": f"Successfully deleted {deleted_count} PDF(s)",
            "deleted_count": deleted_count,
            "deleted_files": deleted_files
        }
        
    except Exception as e:
        print(f"Error deleting PDFs for session {session_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete PDFs: {str(e)}")


@router.post("/upload-objection-pdf", response_model=PDFUploadResponse)
async def upload_objection_pdf(
    request: Request,
    file: UploadFile = File(...),
    session_id: str = Form(...),
    current_user: User = Depends(get_current_user),
):
    """
    Upload an objection PDF file and save it to the objection_pdf_{session_id} vectorstore collection.
    """
    print(f"DEBUG: Objection PDF upload endpoint called by user: {current_user.email}")
    
    try:
        # Validate session exists or create new one
        session = await get_session(session_id)
        if not session:
            session = await create_session_with_id(session_id, user_id=current_user.id, firm_id=current_user.firm_id)
        
        # Validate file type
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are allowed")
        
        # Validate file size (configurable limit)
        from ..config import settings
        max_size_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
        if file.size > max_size_bytes:
            raise HTTPException(status_code=400, detail=f"File too large. Maximum size is {settings.MAX_FILE_SIZE_MB}MB")
        
        # Save the objection PDF with a unique name based on session
        filename = f"objection_pdf_{session_id}.pdf"
        file_path = os.path.join(PDF_STORAGE_DIR, filename)
        
        import shutil
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Verify the file was saved successfully
        if not os.path.exists(file_path):
            raise HTTPException(status_code=500, detail="Failed to save uploaded file")
        
        # Ingest the uploaded objection PDF into the session-scoped vectorstore collection
        try:
            objection_collection = f"objection_pdf_{session_id}"
            # Overwrite behavior: clear the collection before ingesting
            try:
                clear_result = clear_collection(objection_collection)
                if not clear_result.get("success"):
                    print(f"⚠️ Failed to clear collection {objection_collection}: {clear_result.get('error')}")
            except Exception as e:
                print(f"⚠️ Error clearing collection {objection_collection}: {e}")
            
            ingest_result = process_uploaded_file(file_path, file_type="pdf", collection_name=objection_collection)
            if not ingest_result.get("success"):
                print(f"⚠️ Vectorstore ingest failed for {objection_collection}: {ingest_result.get('error')}")
            else:
                print(f"✅ Ingested uploaded objection PDF into collection {objection_collection}: {ingest_result.get('stored_count')} chunks")
        except Exception as e:
            print(f"Error ingesting uploaded objection PDF into vectorstore: {e}")
        
        # Save PDF metadata to database
        await save_pdf_metadata(
            session_id=session_id,
            filename=filename,
            original_filename=file.filename,
            file_path=file_path,
            file_size=file.size,
            collection_name=objection_collection,
            source="manual",
        )
        
        response = PDFUploadResponse(
            message=f"Objection PDF '{file.filename}' uploaded successfully and is ready for processing",
            filename=filename,
            file_path=file_path,
            size=file.size,
            available_for_review=True
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in objection PDF upload: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Upload error: {str(e)}")


@router.post("/upload-motion-pdf", response_model=PDFUploadResponse)
async def upload_motion_pdf(
    request: Request,
    file: UploadFile = File(...),
    session_id: str = Form(...),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a motion PDF file and save it to the motion_pdf_{session_id} vectorstore collection.
    """
    print(f"DEBUG: Motion PDF upload endpoint called by user: {current_user.email}")
    
    try:
        # Validate session exists or create new one
        session = await get_session(session_id)
        if not session:
            session = await create_session_with_id(session_id, user_id=current_user.id, firm_id=current_user.firm_id)
        
        # Validate file type
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are allowed")
        
        # Validate file size (configurable limit)
        from ..config import settings
        max_size_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
        if file.size > max_size_bytes:
            raise HTTPException(status_code=400, detail=f"File too large. Maximum size is {settings.MAX_FILE_SIZE_MB}MB")
        
        # Save the motion PDF with a unique name based on session
        filename = f"motion_pdf_{session_id}.pdf"
        file_path = os.path.join(PDF_STORAGE_DIR, filename)
        
        import shutil
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Verify the file was saved successfully
        if not os.path.exists(file_path):
            raise HTTPException(status_code=500, detail="Failed to save uploaded file")
        
        # Ingest the uploaded motion PDF into the session-scoped vectorstore collection
        try:
            motion_collection = f"motion_pdf_{session_id}"
            # Overwrite behavior: clear the collection before ingesting
            try:
                clear_result = clear_collection(motion_collection)
                if not clear_result.get("success"):
                    print(f"⚠️ Failed to clear collection {motion_collection}: {clear_result.get('error')}")
            except Exception as e:
                print(f"⚠️ Error clearing collection {motion_collection}: {e}")
            
            ingest_result = process_uploaded_file(file_path, file_type="pdf", collection_name=motion_collection)
            if not ingest_result.get("success"):
                print(f"⚠️ Vectorstore ingest failed for {motion_collection}: {ingest_result.get('error')}")
            else:
                print(f"✅ Ingested uploaded motion PDF into collection {motion_collection}: {ingest_result.get('stored_count')} chunks")
        except Exception as e:
            print(f"Error ingesting uploaded motion PDF into vectorstore: {e}")
        
        # Save PDF metadata to database
        await save_pdf_metadata(
            session_id=session_id,
            filename=filename,
            original_filename=file.filename,
            file_path=file_path,
            file_size=file.size,
            collection_name=motion_collection,
            source="manual",
        )
        
        response = PDFUploadResponse(
            message=f"Motion PDF '{file.filename}' uploaded successfully and is ready for processing",
            filename=filename,
            file_path=file_path,
            size=file.size,
            available_for_review=True
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in motion PDF upload: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Upload error: {str(e)}")


@router.post("/upload-loe-supporting-docs")
async def upload_loe_supporting_docs(
    request: Request,
    files: list[UploadFile] = File(...),
    session_id: str = Form(...),
    task_id: str = Form(...),
    store_permanently: bool = Form(False),
    current_user: User = Depends(get_current_user),
):
    """
    Upload supporting documents (PDF, DOCX, images) for LOE generation.
    Accepts up to 10 files. Processes them and stores temporarily in Redis.
    If store_permanently=True, also stores in vectorstore for future chatbot access.
    """
    from pathlib import Path
    import shutil
    from ..motion_filling.loe_document_processor import process_loe_supporting_docs

    print(f"DEBUG: LOE supporting docs upload endpoint called for session {session_id}, task {task_id} by user: {current_user.email}")

    try:
        # Validate file count
        if len(files) > 10:
            raise HTTPException(status_code=400, detail="Maximum 10 files allowed")

        if len(files) == 0:
            raise HTTPException(status_code=400, detail="No files provided")

        # Allowed file extensions
        allowed_extensions = {'.pdf', '.docx', '.doc', '.png', '.jpg', '.jpeg', '.gif', '.webp'}

        # Validate and save files
        saved_files = []
        for file in files:
            ext = Path(file.filename).suffix.lower()
            if ext not in allowed_extensions:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid file type: {ext}. Allowed: PDF, DOCX, PNG, JPG, JPEG"
                )

            # Validate file size
            from ..config import settings
            max_size_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
            if file.size and file.size > max_size_bytes:
                raise HTTPException(
                    status_code=400,
                    detail=f"File {file.filename} too large. Maximum size is {settings.MAX_FILE_SIZE_MB}MB"
                )

            # Save file temporarily
            safe_filename = f"loe_doc_{task_id}_{len(saved_files)}{ext}"
            file_path = os.path.join(PDF_STORAGE_DIR, safe_filename)

            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            if os.path.exists(file_path):
                saved_files.append((file_path, file.filename))
            else:
                print(f"WARNING: Failed to save file {file.filename}")

        if not saved_files:
            raise HTTPException(status_code=500, detail="Failed to save any files")

        # Process all saved files
        result = process_loe_supporting_docs(
            file_paths=saved_files,
            session_id=session_id,
            task_id=task_id,
            store_permanently=store_permanently
        )

        return {
            "success": result.get("success", False),
            "processed_count": result.get("processed_count", 0),
            "errors": result.get("errors"),
            "store_permanently": store_permanently,
            "message": f"Processed {result.get('processed_count', 0)} supporting documents"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in LOE supporting docs upload: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Upload error: {str(e)}")


@router.post("/upload-order-delay-motion")
async def upload_order_delay_motion(
    request: Request,
    files: list[UploadFile] = File(...),
    session_id: str = Form(...),
    task_id: str = Form(...),
):
    """
    Upload the Motion to Delay PDF/DOCX for order-delay generation.
    Accepts exactly 1 file. Extracts text and stores temporarily in Redis
    (TTL: 1 hour) for chip generation in resume_pleading_extraction().
    """
    from pathlib import Path
    import shutil
    from ..motion_filling.order_delay_document_processor import process_order_delay_motion_doc

    # --- Auth (identical pattern to upload_loe_supporting_docs) ---
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")

    token = auth_header.split(" ")[1]
    try:
        from ..auth.auth import get_user_by_id
        from jose import jwt
        from ..config import settings

        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        current_user = await get_user_by_id(user_id)
        if not current_user:
            raise HTTPException(status_code=401, detail="User not found")
    except Exception:
        raise HTTPException(status_code=401, detail="Authentication failed")

    try:
        # --- Validation ---
        if len(files) == 0:
            raise HTTPException(status_code=400, detail="No file provided")
        if len(files) > 1:
            raise HTTPException(status_code=400, detail="Only 1 file allowed for Motion to Delay upload")

        allowed_extensions = {".pdf", ".docx", ".doc"}
        file = files[0]
        ext = Path(file.filename).suffix.lower()

        if ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type: {ext}. Allowed: PDF, DOCX"
            )

        from ..config import settings
        max_size_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
        if file.size and file.size > max_size_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum size is {settings.MAX_FILE_SIZE_MB}MB"
            )

        # --- Save temp file ---
        safe_filename = f"order_delay_doc_{task_id}_0{ext}"
        file_path = os.path.join(PDF_STORAGE_DIR, safe_filename)

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        if not os.path.exists(file_path):
            raise HTTPException(status_code=500, detail="Failed to save file")

        # --- Process & store in Redis ---
        result = process_order_delay_motion_doc(
            file_paths=[(file_path, file.filename)],
            session_id=session_id,
            task_id=task_id,
        )

        return {
            "success": result.get("success", False),
            "processed_count": result.get("processed_count", 0),
            "errors": result.get("errors"),
            "message": (
                "Motion to Delay document processed successfully"
                if result.get("success")
                else "Processing failed — check errors"
            ),
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in order-delay motion upload: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Upload error: {str(e)}")
