"""Routes for motion generation and CourtDrive functionality."""

import logging
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pathlib import Path
from ..chatbot.database import get_motion_case_info
from ..tasks.pleading_helpers import build_download_filename

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Motion Drafter - Core"])

GENERATED_DOCX_DIR = Path(__file__).parent.parent.parent / 'generated_docx'
GENERATED_PDF_DIR = Path(__file__).parent.parent.parent / 'generated_pdf'
UPLOADS_DIR = Path(__file__).parent.parent.parent / 'uploads'
GENERATED_DOCX_DIR.mkdir(parents=True, exist_ok=True)
GENERATED_PDF_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

MOTION_TYPE_MAP = {
    'extend': 'motion_to_extend',
    'modify': 'motion_to_modify',
    'value': 'motion_to_value',
    'loe': 'motion_to_loe',
    'withdraw': 'motion_to_withdraw',
    'waive': 'motion_to_waive',
    'claim': 'motion_to_claim',
    'delay': 'motion_to_delay',
    'reinstate': 'motion_to_reinstate',
    'service': 'certificate_of_service',
    'suggestion': 'motion_to_suggestion',
    'objection-sustain': 'order_sustaining_objection',
    'order-extend': 'order_on_motion_to_extend',
    'order-waive': 'order_on_motion_to_waive',
    'order-withdraw': 'order_on_motion_to_withdraw',
    'order-reinstate': 'order_on_motion_to_reinstate',
    'order-extension': 'order_on_motion_for_extension',
    'ex-parte-extension': 'ex_parte_motion_for_extension',
    'notice-withdraw': 'notice_to_withdraw',
}

def get_filenames(motion_type, session_id, variant: str | None = None):
    prefix = MOTION_TYPE_MAP.get(motion_type, f"motion_to_{motion_type}")
    suffix = f"_{variant}" if variant else ""
    docx_filename = f"{prefix}_{session_id}{suffix}.docx"
    pdf_filename = f"{prefix}_{session_id}{suffix}.pdf"
    return docx_filename, pdf_filename

@router.get("/motions/existence")
async def check_motion_files(
    session_id: str = Query(...),
    motion_type: str = Query(...),
    variant: str | None = Query(None, description="Variant: 'granted' or 'denied' (for order documents)"),
):
    docx_filename, pdf_filename = get_filenames(motion_type, session_id, variant)
    docx_path = GENERATED_DOCX_DIR / docx_filename
    pdf_path = GENERATED_PDF_DIR / pdf_filename
    return {
        "docx_exists": docx_path.exists(),
        "pdf_exists": pdf_path.exists(),
        "docx_filename": docx_filename,
        "pdf_filename": pdf_filename
    }


@router.get("/motions/download")
async def download_motion_file(
    session_id: str = Query(...),
    motion_type: str = Query(...),
    file_type: str = Query("pdf"),
    variant: str | None = Query(None, description="Variant: 'granted' or 'denied' (for order documents)"),
):
    """
    Download an existing generated motion file from generated_docx/generated_pdf root folders.
    file_type: 'pdf' or 'docx'
    variant: Optional variant for order documents ('granted' or 'denied')
    """
    docx_filename, pdf_filename = get_filenames(motion_type, session_id, variant)
    case_name, case_number = await get_motion_case_info(session_id)
    prefix = MOTION_TYPE_MAP.get(motion_type, f"motion_to_{motion_type}")
    if variant:
        prefix = f"{prefix}_{variant}"

    if file_type == "docx":
        path = GENERATED_DOCX_DIR / docx_filename
        if not path.exists():
            raise HTTPException(status_code=404, detail="DOCX not found")
        return FileResponse(
            path=str(path),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=build_download_filename(prefix, case_name, case_number, "docx"),
        )
    else:
        path = GENERATED_PDF_DIR / pdf_filename
        if not path.exists():
            raise HTTPException(status_code=404, detail="PDF not found")
        return FileResponse(
            path=str(path),
            media_type="application/pdf",
            filename=build_download_filename(prefix, case_name, case_number, "pdf"),
        )
