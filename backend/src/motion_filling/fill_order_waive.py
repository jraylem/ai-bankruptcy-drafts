from __future__ import annotations
from pathlib import Path
from .generator_common import generate_document
from zipfile import ZipFile
import json
import re
from docxtpl import DocxTemplate
from datetime import date
from dateutil.parser import parse as parse_date

# -------------------- paths --------------------
BASE_DIR = Path(__file__).parent.resolve()
DATAFILE = BASE_DIR / "data" / "payload.order_waive.json"
OUT_DIR = BASE_DIR / "out"

# Template for order to waive
TEMPLATE_CANDIDATES = [
    BASE_DIR.parent / "templates" / "order_motion_waive.docx",
]

OUTPUT_BASENAME = "Order_Motion_Waive_FILLED"


# -------------------- helpers --------------------
def load_payload() -> dict:
    """Load sample payload from local JSON (for CLI testing/manual runs)."""
    return json.loads(DATAFILE.read_text(encoding="utf-8"))


def ensure_docx_template() -> Path:
    """Return the first existing DOCX template for the order to waive."""
    for p in TEMPLATE_CANDIDATES:
        if p.exists():
            return p
    raise SystemExit(
        "Template not found. Place 'order_motion_waive.docx' under templates/ ."
    )


def docx_xml(path: Path) -> str:
    try:
        with ZipFile(path, "r") as z:
            return z.read("word/document.xml").decode("utf-8", errors="ignore")
    except Exception:
        return ""


def warn_unresolved_placeholders(docx_path: Path):
    """After render, warn if any '{{...}}' leftovers remain."""
    xml = docx_xml(docx_path)
    leftovers = re.findall(r"{{[^}]+}}", xml)
    if leftovers:
        print("\nWARNING: Unresolved placeholders still in output:")
        for tok in leftovers:
            print("  -", tok)
        print("Check spelling/case in the template and context keys above.\n")


# -------------------- PDF conversion --------------------
def convert_to_pdf_wordcom(docx_path: Path) -> Path | None:
    try:
        import win32com.client as win32  # type: ignore
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
    import shutil
    import subprocess

    if not shutil.which("soffice"):
        return None
    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "soffice",
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(OUT_DIR),
                str(docx_path),
            ],
            check=True,
        )
        return docx_path.with_suffix(".pdf")
    except Exception:
        return None


def convert_to_pdf(docx_path: Path) -> Path:
    pdf = convert_to_pdf_wordcom(docx_path) or convert_to_pdf_libreoffice(docx_path)
    if not pdf or not pdf.exists():
        raise RuntimeError(
            "Could not convert to PDF. Install MS Word + pywin32 or LibreOffice (soffice on PATH)."
        )
    return pdf


# -------------------- context builder --------------------
# Expected payload fields (from stream):
#   DebtorName, CaseNumber, ChapterNumber, TrusteeCalendar


def _as_str(val) -> str:
    if val is None:
        return ""
    return str(val).strip()


def build_context(ai: dict) -> dict:
    """
    Build context dictionary for Order on Motion to Waive template.

    Expected payload fields:
    - DebtorName: Debtor's full name
    - CaseNumber: Case number (may include judge initials)
    - ChapterNumber: Chapter number (e.g., "13")
    - TrusteeCalendar: Calendar date/time or 'N/A'
    """
    debtor_name = _as_str(ai.get("DebtorName"))
    case_number = _as_str(ai.get("CaseNumber"))
    chapter_number = _as_str(ai.get("ChapterNumber"))
    trustee_calendar_raw = _as_str(ai.get("TrusteeCalendar"))
    docket_number = _as_str(ai.get("DocketNumber"))

    # Trustee Calendar Format — output: "April 6th, 2026 at 10:00 AM", or "" if no value
    trustee_calendar = ""
    if trustee_calendar_raw and trustee_calendar_raw.strip().upper() not in ("", "N/A"):
        try:
            parsed = parse_date(trustee_calendar_raw, fuzzy=True)
            day = parsed.day
            suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
            trustee_calendar = parsed.strftime(f"%B {day}{suffix}, %Y at %I:%M %p")
        except Exception:
            trustee_calendar = ""

    # Leave docker_number as blank if equal to N/A
    if docket_number and docket_number.upper() != "N/A":
        docket_number = str(docket_number).strip()
    else:
        docket_number = "" # No docket number to place in the document

    # Split "A and B" or "A, B, and C" into one name per line
    import re as _re
    _parts = [p.strip() for p in _re.split(r',\s*(?:and\s+)?|\s+and\s+', debtor_name) if p.strip()]
    header_debtor_name = "\n".join(_parts) if _parts else debtor_name

    ctx = {
        "HeaderDebtorName": header_debtor_name,
        "DebtorName": debtor_name,
        "CaseNumber": case_number,
        "ChapterNumber": chapter_number,
        "TrusteeCalendar": trustee_calendar,
        "DocketNumber": docket_number,
    }
    return ctx


# -------------------- render --------------------
def render_docx(template_docx: Path, ctx: dict, name_slug: str) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_docx = OUT_DIR / f"{name_slug}.docx"
    if out_docx.exists():
        out_docx.unlink()

    print(f"DEBUG: Rendering order waive with context: {ctx}")
    print(f"DEBUG: Template file: {template_docx}")
    print(f"DEBUG: Template exists: {template_docx.exists()}")

    doc = DocxTemplate(template_docx)
    doc.render(ctx)
    doc.save(out_docx)
    warn_unresolved_placeholders(out_docx)
    return out_docx


# -------------------- orchestration helpers --------------------
def resolve_template_from_payload(payload: dict) -> Path:
    """Resolve the correct template for order waive."""
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


def generate_pdf_from_payload(payload_data: dict, output_basename: str | None = None) -> Path:
    return generate_document_from_payload(payload_data, output_basename, "pdf")


def generate_docx_from_payload(payload_data: dict, output_basename: str | None = None) -> Path:
    return generate_document_from_payload(payload_data, output_basename, "docx")


def generate_both_formats_from_payload(
    payload_data: dict, output_basename: str | None = None
) -> tuple[Path, Path]:
    """
    Generate both DOCX and PDF for Order on Motion to Waive from payload data.

    Returns:
        (docx_path, pdf_path)
    """
    template = resolve_template_from_payload(payload_data)
    ctx = build_context(payload_data)
    name_slug = output_basename or OUTPUT_BASENAME
    out_docx = render_docx(template, ctx, name_slug)
    out_pdf = convert_to_pdf(out_docx)
    return out_docx, out_pdf


# -------------------- main (for manual testing) --------------------
def main():
    template = ensure_docx_template()
    ai_data = load_payload()
    ctx = build_context(ai_data)
    out_docx = render_docx(template, ctx, OUTPUT_BASENAME)
    print("DOCX generated:", out_docx.resolve())


if __name__ == "__main__":
    test_payload = {
        "DebtorName":      "Laura Marie Cavazos and Moises Rafael Cavazos",
        "CaseNumber":      "25-21814-PDR",
        "ChapterNumber":   "13",
        "TrusteeCalendar": "April 6th, 2026 at 10:00 AM",
        "DocketNumber":    "12",
    }

    print("Testing order to waive functionality...")

    docx_path, pdf_path = generate_both_formats_from_payload(test_payload)
    print(f"DOCX generated: {docx_path}")
    print(f"PDF generated: {pdf_path}")

