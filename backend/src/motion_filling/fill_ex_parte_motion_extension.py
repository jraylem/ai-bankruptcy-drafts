from __future__ import annotations
from pathlib import Path
from .generator_common import generate_document
from zipfile import ZipFile
import json, re, subprocess, shutil
from datetime import date
from dateutil.parser import parse
from docxtpl import DocxTemplate

# -------------------- paths --------------------
BASE_DIR = Path(__file__).parent.resolve()
DATAFILE = BASE_DIR / "data" / "payload.ex_parte_extension.json"
OUT_DIR = BASE_DIR / "out"

# Template for ex parte motion for extension
TEMPLATE_CANDIDATES = [
    BASE_DIR.parent / "templates" / "ex_parte_motion_for_extension.docx",
]

OUTPUT_BASENAME = "Ex_Parte_Motion_for_Extension_FILLED"

# -------------------- helpers --------------------
def load_payload() -> dict:
    if not DATAFILE.exists():
        raise SystemExit(f"Payload file not found: {DATAFILE}")
    return json.loads(DATAFILE.read_text(encoding="utf-8"))


def parse_date(dt_like) -> date | None:
    try:
        return parse(str(dt_like)).date() if dt_like else None
    except Exception:
        return None


def fmt_long(dt_like) -> str:
    """
    Formats a date into 'Month Day, Year' (e.g. 'October 8, 2025')
    If the input cannot be parsed as a date, returns the original string as-is.
    """
    if not dt_like:
        return ""
    try:
        d = dt_like if isinstance(dt_like, date) else parse(str(dt_like)).date()
        return f"{d.strftime('%B')} {d.day}, {d.year}"
    except Exception:
        return str(dt_like)


def ensure_docx_template() -> Path:
    for p in TEMPLATE_CANDIDATES:
        if p.exists():
            return p
    raise SystemExit("Template not found. Place 'ex_parte_motion_for_extension.docx' under templates/ .")


def warn_unresolved_placeholders(docx_path: Path):
    try:
        with ZipFile(docx_path, "r") as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
    except Exception:
        return
    leftovers = re.findall(r"{{[^}]+}}", xml)
    if leftovers:
        print("\nWARNING: Unresolved placeholders:")
        for tok in leftovers:
            print("  -", tok)


# -------------------- PDF conversion --------------------
def convert_to_pdf_wordcom(docx_path: Path) -> Path | None:
    try:
        import win32com.client as win32
    except Exception:
        return None
    try:
        pdf_path = docx_path.with_suffix(".pdf")
        word = win32.gencache.EnsureDispatch("Word.Application")
        word.Visible = False
        doc = word.Documents.Open(str(docx_path.resolve()))
        # wdExportFormatPDF = 17
        doc.ExportAsFixedFormat(str(pdf_path.resolve()), 17)
        doc.Close(False)
        word.Quit()
        return pdf_path if pdf_path.exists() else None
    except Exception:
        try:
            word.Quit()
        except Exception:
            pass
        return None


def convert_to_pdf_libreoffice(docx_path: Path) -> Path | None:
    from .pdf_utils import convert_to_pdf_libreoffice as _convert
    return _convert(docx_path, OUT_DIR)


def convert_to_pdf(docx_path: Path) -> Path:
    pdf = convert_to_pdf_wordcom(docx_path) or convert_to_pdf_libreoffice(docx_path)
    if not pdf or not pdf.exists():
        raise RuntimeError(
            "Could not convert to PDF. Install MS Word + pywin32 or LibreOffice (soffice on PATH)."
        )
    return pdf


# -------------------- context builder --------------------
def build_context(ai: dict) -> dict:
    """
    Build context dictionary for ex parte motion for extension template.
    
    Expected payload fields:
    - DebtorName: Debtor's full name
    - CaseNumber: Case number with judge initial (e.g., "25-12345-JCC")
    - ChapterNumber: Chapter number (e.g., "13")
    - DateFiled: Date the petition was filed
    - DateFiledPlusFourteen: DateFiled + 14 days
    - MeetingDate: Date of meeting of creditors
    - CurrentDate: Current date
    """
    # Extract basic fields
    debtor_name = (ai.get("DebtorName") or "").strip()
    case_number = (ai.get("CaseNumber") or "").strip()
    chapter_number = str(ai.get("ChapterNumber") or "").strip()
    date_filed = (ai.get("DateFiled") or "").strip()
    date_filed_plus_fourteen = (ai.get("DateFiledPlusFourteen") or "").strip()
    meeting_date = (ai.get("MeetingDate") or "").strip()
    current_date = (ai.get("CurrentDate") or "").strip()
    
    # Format dates - try to parse and format, otherwise use as-is
    date_filed_formatted = fmt_long(parse_date(date_filed)) if date_filed else date_filed
    date_filed_plus_fourteen_formatted = fmt_long(parse_date(date_filed_plus_fourteen)) if date_filed_plus_fourteen else date_filed_plus_fourteen
    meeting_date_formatted = fmt_long(parse_date(meeting_date)) if meeting_date else meeting_date
    current_date_formatted = fmt_long(parse_date(current_date)) if current_date else current_date
    
    import re as _re
    _parts = [p.strip() for p in _re.split(r',\s*(?:and\s+)?|\s+and\s+', debtor_name) if p.strip()]
    header_debtor_name = "\n".join(_parts) if _parts else debtor_name

    return {
        "HeaderDebtorName": header_debtor_name,
        "DebtorName": debtor_name,
        "CaseNumber": case_number,
        "ChapterNumber": chapter_number,
        "DateFiled": date_filed_formatted,
        "DateFiledPlusFourteen": date_filed_plus_fourteen_formatted,
        "MeetingDate": meeting_date_formatted,
        "CurrentDate": current_date_formatted or current_date,
    }


# -------------------- render --------------------
def render_docx(template_docx: Path, ctx: dict, name_slug: str) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_docx = OUT_DIR / f"{name_slug}.docx"
    
    if out_docx.exists():
        out_docx.unlink()
    
    doc = DocxTemplate(template_docx)
    doc.render(ctx)
    doc.save(out_docx)
    warn_unresolved_placeholders(out_docx)
    return out_docx


# -------------------- orchestration helpers (DOCX + PDF) --------------------
def resolve_template_from_payload(payload: dict) -> Path:
    """Resolve the correct template. For ex parte extension, we use a single template file."""
    return ensure_docx_template()


def generate_document_from_payload(payload_data: dict, output_basename: str = None, output_type: str = "pdf") -> Path:
    return generate_document(
        payload_data=payload_data,
        output_basename=output_basename,
        output_type=output_type,
        default_basename=OUTPUT_BASENAME,
        resolve_template=resolve_template_from_payload,
        build_context=build_context,
        render_docx=render_docx,
        convert_to_pdf=convert_to_pdf,
    )


def generate_pdf_from_payload(payload_data: dict, output_basename: str = None) -> Path:
    return generate_document_from_payload(payload_data, output_basename, "pdf")


def generate_docx_from_payload(payload_data: dict, output_basename: str = None) -> Path:
    return generate_document_from_payload(payload_data, output_basename, "docx")

def generate_both_formats_from_payload(payload_data: dict, output_basename: str = None) -> tuple[Path, Path]:
    template = resolve_template_from_payload(payload_data)
    ctx = build_context(payload_data)
    name_slug = output_basename or OUTPUT_BASENAME
    out_docx = render_docx(template, ctx, name_slug)
    out_pdf = convert_to_pdf(out_docx)
    return out_docx, out_pdf


# -------------------- main --------------------
def main():
    template = ensure_docx_template()
    ai_data = load_payload()
    ctx = build_context(ai_data)
    out_docx = render_docx(template, ctx, OUTPUT_BASENAME)
    print("DOCX generated:", out_docx.resolve())


if __name__ == "__main__":
    main()