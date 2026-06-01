from __future__ import annotations
from pathlib import Path
from .generator_common import generate_document
from zipfile import ZipFile
import re
from datetime import date
from dateutil.parser import parse as parse_date
from docxtpl import DocxTemplate

# -------------------- paths --------------------
BASE_DIR = Path(__file__).parent.resolve()
OUT_DIR = BASE_DIR / "out"

TEMPLATE_CANDIDATES = [
    BASE_DIR.parent / "templates" / "order_motion_withdraw.docx",
]

OUTPUT_BASENAME = "Order_Motion_Withdraw_FILLED"


def ensure_docx_template() -> Path:
    """Return the first existing DOCX template for the order on motion to withdraw."""
    for p in TEMPLATE_CANDIDATES:
        if p.exists():
            return p
    raise SystemExit(
        "Template not found. Place 'order_motion_withdraw.docx' under templates/ ."
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
# Expected payload fields:
#   DebtorName, CaseNumber, ChapterNumber, MotionAddress, IfExParte


def _as_str(val) -> str:
    if val is None:
        return ""
    return str(val).strip()


def _normalize_if_ex_parte_flag(flag) -> str:
    """
    Normalize an IfExParte flag (bool or string) into the phrase used in the order template.

    - True  -> "without a hearing on the Ex-Parte Agreed"
    - False -> "Chapter 13 Trustee’s Consent Calendar on "
    - Other/None -> "" or the literal value (e.g., "N/A")
    """
    if isinstance(flag, bool):
        return (
            "WITHOUT A HEARING ON THE EX-PARTE AGREED"
            if flag
            else "CHAPTER 13 TRUSTEE’S CONSENT CALENDAR ON "
        )

    if flag is None:
        return ""

    s = str(flag).strip().lower()
    if s in {"true", "yes", "y", "1"}:
        return "without a hearing on the Ex-Parte Agreed"
    if s in {"false", "no", "n", "0"}:
        return "Chapter 13 Trustee’s Consent Calendar on "

    # For "N/A" or any other literal, just return as-is so the template can decide.
    return str(flag)


def build_context(ai: dict) -> dict:
    """
    Build context dictionary for Order on Motion to Withdraw template.
    """
    debtor_name = _as_str(ai.get("DebtorName"))
    case_number = _as_str(ai.get("CaseNumber"))
    chapter_number = _as_str(ai.get("ChapterNumber") or ai.get("Chapter"))
    motion_address = _as_str(ai.get("MotionAddress") or ai.get("DebtorCurrentAddy"))
    # if_ex_parte_raw = ai.get("IfExParte", "N/A") - remove based on the updated document - order_motion_withdraw.docx
    docket_number = _as_str(ai.get("DocketNumber"))
    trustee_calendar_raw = _as_str(ai.get("TrusteeCalendar"))

    # if if_ex_parte_raw not in (None, "N/A"): - remove based on the updated document - order_motion_withdraw.docx
    #     if_ex_parte_text = _normalize_if_ex_parte_flag(if_ex_parte_raw)
    # else:
    #     if_ex_parte_text = str(if_ex_parte_raw)

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
        "MotionAddress": motion_address,
        # "IfExParte": if_ex_parte_text, - remove based on the updated document - order_motion_withdraw.docx
        "DocketNumber": docket_number,
        "TrusteeCalendar": trustee_calendar,
    }
    return ctx


# -------------------- render --------------------
def render_docx(template_docx: Path, ctx: dict, name_slug: str) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_docx = OUT_DIR / f"{name_slug}.docx"
    if out_docx.exists():
        out_docx.unlink()

    print(f"DEBUG: Rendering order withdraw with context: {ctx}")
    print(f"DEBUG: Template file: {template_docx}")
    print(f"DEBUG: Template exists: {template_docx.exists()}")

    doc = DocxTemplate(template_docx)
    doc.render(ctx)
    doc.save(out_docx)
    warn_unresolved_placeholders(out_docx)
    return out_docx


# -------------------- orchestration helpers --------------------
def resolve_template_from_payload(payload: dict) -> Path:
    """Resolve the correct template for order withdraw."""
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


def generate_pdf_from_payload(
    payload_data: dict, output_basename: str | None = None
) -> Path:
    return generate_document_from_payload(payload_data, output_basename, "pdf")


def generate_docx_from_payload(
    payload_data: dict, output_basename: str | None = None
) -> Path:
    return generate_document_from_payload(payload_data, output_basename, "docx")


def generate_both_formats_from_payload(
    payload_data: dict, output_basename: str | None = None
) -> tuple[Path, Path]:
    """
    Generate both DOCX and PDF for Order on Motion to Withdraw from payload data.

    Returns:
        (docx_path, pdf_path)
    """
    template = resolve_template_from_payload(payload_data)
    ctx = build_context(payload_data)
    name_slug = output_basename or OUTPUT_BASENAME
    out_docx = render_docx(template, ctx, name_slug)
    out_pdf = convert_to_pdf(out_docx)
    return out_docx, out_pdf


def main():
    template = ensure_docx_template()
    sample = {
        "DebtorName": "Sample Debtor",
        "CaseNumber": "25-12345-PDR",
        "ChapterNumber": "13",
        "MotionAddress": "123 Main St, City, FL 33301",
        # "IfExParte": True,
        "DocketNumber": "1",
    }
    ctx = build_context(sample)
    out_docx = render_docx(template, ctx, OUTPUT_BASENAME)
    print("DOCX generated:", out_docx.resolve())


if __name__ == "__main__":
    test_payload = {
        "DebtorName":      "Laura Marie Cavazos and Moises Rafael Cavazos",
        "CaseNumber":      "25-21814-PDR",
        "ChapterNumber":   "13",
        "MotionAddress":   "123 Main Street, Hollywood, FL 33020",
        "DocketNumber":    "15",
        "TrusteeCalendar": "April 6th, 2026 at 10:00 AM",
    }

    print("Testing order to withdraw functionality...")

    docx_path, pdf_path = generate_both_formats_from_payload(test_payload)
    print(f"DOCX generated: {docx_path}")
    print(f"PDF generated: {pdf_path}")

