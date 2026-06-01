from __future__ import annotations
from pathlib import Path
from .generator_common import generate_document
from zipfile import ZipFile
import json, re
from datetime import date
from dateutil.parser import parse
from docxtpl import DocxTemplate

# -------------------- paths --------------------
BASE_DIR = Path(__file__).parent.resolve()
DATAFILE = BASE_DIR / "data" / "payload.order_extend_expedite.json"
OUT_DIR = BASE_DIR / "out"

# Use the standard template file inside templates folder
TEMPLATE_CANDIDATES = [
    BASE_DIR.parent / "templates" / "order_granting_expedited_motion_to_extend.docx",
]

OUTPUT_BASENAME = "Order_Granting_Expedited_Motion_to_Extend_FILLED"

# -------------------- helpers --------------------
def load_payload() -> dict:
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
        # If not a normal date, just return the literal (e.g. "8th day of September, 2025")
        return str(dt_like)


def ensure_docx_template() -> Path:
    for p in TEMPLATE_CANDIDATES:
        if p.exists():
            return p
    raise SystemExit("Template not found. Place 'order_granting_expedited_motion_to_extend.docx' under templates/ .")


def warn_unresolved_placeholders(docx_path: Path):
    with ZipFile(docx_path, "r") as z:
        xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
    leftovers = re.findall(r"{{[^}]+}}", xml)
    if leftovers:
        print("\nWARNING: Unresolved placeholders:")
        for tok in leftovers:
            print("  -", tok)


# -------------------- PDF conversion (same style as other motions) --------------------
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
    import shutil, subprocess
    if not shutil.which("soffice"):
        return None
    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.run([
            "soffice", "--headless", "--convert-to", "pdf",
            "--outdir", str(OUT_DIR), str(docx_path)
        ], check=True)
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
# Template placeholders expected (from Word template):
#   DebtorName, CaseNumber, Chapter, GRANTING, DENYING, GRANTED, DENIED, CalendarDate, DocketMotion, OptionalConditions

def _as_text(val) -> str:
    if val is None:
        return ""
    if isinstance(val, (list, tuple)):
        # Join lists into a readable sentence.
        return " ".join(str(x).strip() for x in val if str(x).strip())
    return str(val)


def build_context(ai: dict, granted: bool | None = None) -> dict:
    # Extract data from the order payload structure
    debtor_name = ai.get("DebtorName") or ""
    case_number = ai.get("CaseNumber") or ""
    chapter = str(ai.get("Chapter") or "")
    calendar_date_raw = ai.get("CalendarDate") or ""
    docket_motion = ai.get("DocketMotion") or ""
    optional_conditions = ai.get("OptionalConditions") or ""

    # Leave docket_motion as blank if equal to N/A
    if docket_motion and docket_motion.upper() == "N/A":
        docket_motion = "" # No docket motion to place in the document
    
    # Check the "granted" field - can be boolean True/False or string "True"/"False"
    # If granted parameter is provided, use it; otherwise use the payload value.
    # Unrecognized values (e.g. "N/A", None) default to True (GRANTING).
    if granted is None:
        granted_value = ai.get("granted")
        if isinstance(granted_value, bool):
            granted = granted_value
        elif isinstance(granted_value, str):
            lower = granted_value.lower()
            if lower in ("true", "yes", "1"):
                granted = True
            elif lower in ("false", "no", "0"):
                granted = False
            else:
                granted = True  # default for unrecognized values like "N/A"
        else:
            granted = True  # default when field is missing or None
    
    # Set GRANTING/GRANTED or DENYING/DENIED based on granted value
    if granted:
        granting = "GRANTING"
        granted_text = "GRANTED"
        denying = ""
        denied = ""
    else:
        granting = ""
        granted_text = ""
        denying = "DENYING"
        denied = "DENIED"
    
    # Format calendar date — output: "April 6th, 2026 at 10:00 AM", or "" if no value
    formatted_calendar_date = ""
    if calendar_date_raw and calendar_date_raw.strip().upper() not in ("", "N/A"):
        try:
            parsed = parse(calendar_date_raw, fuzzy=True)
            day = parsed.day
            suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
            formatted_calendar_date = parsed.strftime(f"%B {day}{suffix}, %Y at %I:%M %p")
        except Exception:
            formatted_calendar_date = ""

    # Split "A and B" or "A, B, and C" into one name per line
    import re as _re
    _parts = [p.strip() for p in _re.split(r',\s*(?:and\s+)?|\s+and\s+', debtor_name) if p.strip()]
    header_debtor_name = "\n".join(_parts) if _parts else debtor_name

    return {
        "HeaderDebtorName": header_debtor_name,
        "DebtorName": debtor_name,
        "CaseNumber": case_number,
        "Chapter": chapter,
        "GRANTING": granting,
        "DENYING": denying,
        "GRANTED": granted_text,
        "DENIED": denied,
        "CalendarDate": formatted_calendar_date,
        "DocketMotion": docket_motion,
        "OptionalConditions": optional_conditions,
    }


# -------------------- render --------------------
def render_docx(template_docx: Path, ctx: dict, name_slug: str) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_docx = OUT_DIR / f"{name_slug}.docx"
    
    # Debug: Print context being used for rendering
    print(f"DEBUG: Rendering with context: {ctx}")
    print(f"DEBUG: Template file: {template_docx}")
    print(f"DEBUG: Template exists: {template_docx.exists()}")
    
    doc = DocxTemplate(template_docx)
    doc.render(ctx)
    doc.save(out_docx)
    
    # Debug: Check for unresolved placeholders
    print(f"DEBUG: Generated file: {out_docx}")
    warn_unresolved_placeholders(out_docx)
    return out_docx


# -------------------- orchestration helpers (DOCX + PDF) --------------------
def resolve_template_from_payload(payload: dict) -> Path:
    """Resolve the correct template. For order granting expedited extend, we use a single template file."""
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
    """
    Generate granted version of the order.
    Returns (order_docx, order_pdf)
    """
    template = resolve_template_from_payload(payload_data)

    ctx = build_context(payload_data, granted=True)
    name_slug = output_basename or OUTPUT_BASENAME
    order_docx = render_docx(template, ctx, name_slug)
    order_pdf = convert_to_pdf(order_docx)

    return order_docx, order_pdf

# -------------------- main --------------------
def main():
    template = ensure_docx_template()
    ai_data = load_payload()
    ctx = build_context(ai_data)
    out_docx = render_docx(template, ctx, OUTPUT_BASENAME)
    print("DOCX generated:", out_docx.resolve())


if __name__ == "__main__":
    test_payload = {
        "DebtorName":         "Laura Marie Cavazos and Moises Rafael Cavazos",
        "CaseNumber":         "25-14980-PDR",
        "Chapter":            "13",
        "CalendarDate":       "April 6th, 2026 at 10:00 AM",
        "DocketMotion":       "42",
        "OptionalConditions": "",
    }

    print("Testing order granting extend (expedite) functionality...")

    docx_path, pdf_path = generate_both_formats_from_payload(test_payload)
    print(f"DOCX generated: {docx_path}")
    print(f"PDF generated: {pdf_path}")

