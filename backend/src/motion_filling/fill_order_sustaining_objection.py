from __future__ import annotations
from pathlib import Path
from .generator_common import generate_document
from zipfile import ZipFile
import re
from docxtpl import DocxTemplate
from dateutil.parser import parse as parse_date

# -------------------- paths --------------------
BASE_DIR = Path(__file__).parent.resolve()
OUT_DIR = BASE_DIR / "out"

TEMPLATE_CANDIDATES = [
    BASE_DIR.parent / "templates" / "order_sustaining_objection.docx",
]

OUTPUT_BASENAME = "Order_Sustaining_Objection_FILLED"


def ensure_docx_template() -> Path:
    """Return the first existing DOCX template for the order sustaining objection."""
    for p in TEMPLATE_CANDIDATES:
        if p.exists():
            return p
    raise SystemExit("Template not found. Place 'order_sustaining_objection.docx' under templates/ .")


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
# Expected payload fields (from schema):
#   DebtorName, CaseNumber, ChapterNumber, SlotNumb, Creditor, DocketNumber, TrusteeCalendar
# Template fields:
#   HeaderDebtorName, DebtorName, CaseNumber, ChapterNumber, SlotNumb,
#   Creditor, CREDITOR, DocketNumber, TrusteeCalendar


_LEGAL_UPPER = {"LLC", "LLP", "INC", "CORP", "NA", "FSB", "PLC", "LP", "PC", "DBA", "LTD", "PLLC", "CO"}


def _as_str(val) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    return "" if s.upper() == "N/A" else s


def _normalize_creditor(val: str) -> str:
    """Convert all-caps creditor name to mixed case, preserving acronyms and legal abbreviations.

    Example: "LVNV FUNDING, LLC" -> "LVNV Funding, LLC"
    """
    if not val:
        return val

    def _convert_word(word: str) -> str:
        rstripped = word.rstrip(".,;:()")
        trailing = word[len(rstripped):]
        alpha_only = re.sub(r"[^A-Z]", "", rstripped.upper())

        # Known legal/business abbreviations → keep uppercase
        if alpha_only in _LEGAL_UPPER:
            return rstripped.upper() + trailing

        # No vowels → likely an acronym → keep uppercase
        if alpha_only and not any(c in "AEIOU" for c in alpha_only):
            return rstripped.upper() + trailing

        # Regular word → title case
        return rstripped.capitalize() + trailing

    return " ".join(_convert_word(w) for w in val.split())


def build_context(ai: dict) -> dict:
    """Build context dictionary for Order Sustaining Objection to Claim template."""
    debtor_name = _as_str(ai.get("DebtorName"))
    case_number = _as_str(ai.get("CaseNumber"))
    chapter_number = _as_str(ai.get("ChapterNumber") or ai.get("ChapterNumb"))
    slot_numb = _as_str(ai.get("SlotNumb"))
    creditor = _normalize_creditor(_as_str(ai.get("Creditor")))
    docket_number = _as_str(ai.get("DocketNumber"))
    trustee_calendar_raw = _as_str(ai.get("TrusteeCalendar"))

    # TrusteeCalendar format — output: "April 6th, 2026 at 10:00 AM", or "" if no value
    trustee_calendar = ""
    if trustee_calendar_raw and trustee_calendar_raw.strip().upper() not in ("", "N/A"):
        try:
            parsed = parse_date(trustee_calendar_raw, fuzzy=True)
            day = parsed.day
            suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
            trustee_calendar = parsed.strftime(f"%B {day}{suffix}, %Y at %I:%M %p")
        except Exception:
            trustee_calendar = trustee_calendar_raw

    # Split "A and B" or "A, B, and C" into one name per line for header
    import re as _re
    _parts = [p.strip() for p in _re.split(r',\s*(?:and\s+)?|\s+and\s+', debtor_name) if p.strip()]
    header_debtor_name = "\n".join(_parts) if _parts else debtor_name

    return {
        "HeaderDebtorName": header_debtor_name,
        "DebtorName": debtor_name,
        "CaseNumber": case_number,
        "ChapterNumber": chapter_number,
        "SlotNumb": slot_numb,
        "Creditor": creditor,
        "CREDITOR": creditor.upper() if creditor else "",
        "DocketNumber": docket_number,
        "TrusteeCalendar": trustee_calendar,
    }


# -------------------- render --------------------
def render_docx(template_docx: Path, ctx: dict, name_slug: str) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_docx = OUT_DIR / f"{name_slug}.docx"
    if out_docx.exists():
        out_docx.unlink()

    print(f"DEBUG: Rendering order sustaining objection with context: {ctx}")
    print(f"DEBUG: Template file: {template_docx}")
    print(f"DEBUG: Template exists: {template_docx.exists()}")

    doc = DocxTemplate(template_docx)
    doc.render(ctx)
    doc.save(out_docx)
    warn_unresolved_placeholders(out_docx)
    return out_docx


# -------------------- orchestration helpers --------------------
def resolve_template_from_payload(_payload: dict) -> Path:
    """Resolve the correct template for order sustaining objection."""
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
    Generate both DOCX and PDF for Order Sustaining Objection to Claim from payload data.

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
    sample = {
        "DebtorName": "Joanie Maryann Paiement",
        "CaseNumber": "25-22288-PDR",
        "ChapterNumber": "13",
        "SlotNumb": "2-1",
        "Creditor": "LVNV FUNDING, LLC",
        "DocketNumber": "32",
        "TrusteeCalendar": "04/06/2026 at 10:00 AM",
    }
    out_docx, out_pdf = generate_both_formats_from_payload(sample)
    print("DOCX generated:", out_docx.resolve())
    print("PDF generated:", out_pdf.resolve())


if __name__ == "__main__":
    main()
