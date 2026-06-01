from __future__ import annotations

from pathlib import Path
from .generator_common import generate_document
from zipfile import ZipFile
import json
import re

from datetime import date
from dateutil.parser import parse
from docxtpl import DocxTemplate

# -------------------- paths --------------------
BASE_DIR = Path(__file__).parent.resolve()
DATAFILE = BASE_DIR / "data" / "payload.service.json"
OUT_DIR = BASE_DIR / "out"

TEMPLATE_PRIMARY = BASE_DIR.parent / "templates" / "cert_of_service.docx"

TEMPLATE_CANDIDATES = [TEMPLATE_PRIMARY]

OUTPUT_BASENAME = "Certificate_of_Service_FILLED"


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


def fmt_ordinal_day(day: int) -> str:
    """Convert day number to ordinal suffix (1st, 2nd, 3rd, 4th, etc.)"""
    if 10 <= day % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def fmt_ordinal_date(dt_like) -> str:
    """
    Formats a date into ordinal format: '2nd day of April, 2026'.
    If the input cannot be parsed as a date, returns the original string as-is.
    """
    if not dt_like:
        return ""
    try:
        d = dt_like if isinstance(dt_like, date) else parse(str(dt_like)).date()
        return f"{fmt_ordinal_day(d.day)} day of {d.strftime('%B')}, {d.year}"
    except Exception:
        return str(dt_like)


def ensure_docx_template() -> Path:
    missing = [p for p in TEMPLATE_CANDIDATES if not p.exists()]
    if missing:
        missing_list = ", ".join(str(p) for p in missing)
        raise SystemExit(f"Template(s) not found: {missing_list}")
    return TEMPLATE_PRIMARY


def warn_unresolved_placeholders(docx_path: Path):
    try:
        with ZipFile(docx_path, "r") as archive:
            xml = archive.read("word/document.xml").decode("utf-8", errors="ignore")
    except Exception:
        return

    leftovers = re.findall(r"{{[^}]+}}", xml)
    if leftovers:
        print("\nWARNING: Unresolved placeholders detected:")
        for token in leftovers:
            print("  -", token)


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
        doc.ExportAsFixedFormat(str(pdf_path.resolve()), 17)  # 17 == wdExportFormatPDF
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
    pdf_path = convert_to_pdf_wordcom(docx_path) or convert_to_pdf_libreoffice(docx_path)
    if not pdf_path or not pdf_path.exists():
        raise RuntimeError(
            "Could not convert to PDF. Install MS Word + pywin32 or LibreOffice (soffice on PATH)."
        )
    return pdf_path


# -------------------- context builder --------------------
def _is_truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "y", "1"}:
            return True
        if normalized in {"false", "no", "n", "0", "", "n/a", "na", "none"}:
            return False
    return bool(value)


def build_context(payload: dict) -> dict:
    # --- Extract raw fields from payload ---
    debtor_name        = (payload.get("DebtorName")        or "N/A").strip()
    case_number        = (payload.get("CaseNumber")        or "N/A").strip()
    court_district_raw = (payload.get("CourtDistrict")     or "N/A").strip()
    chapter            = (payload.get("Chapter")           or "N/A").strip()
    current_date_raw   = (payload.get("CurrentDate")       or "N/A").strip()
    motion_type        = (payload.get("MotionType")        or "N/A").strip()
    trustee_name       = (payload.get("TrusteeName")       or "").strip()
    trustee_email      = (payload.get("TrustEmail")        or "").strip()
    us_trustee_email   = (payload.get("USTemail")          or "N/A").strip()
    misc_mail_listings = (payload.get("MiscMailListings")  or "")
    if_notice_of_hearing = (payload.get("IfNoticeofHearing") or "N/A").strip()
    docket_motion      = (payload.get("DocketMotion")      or "N/A").strip()

    # --- Format CurrentDate as ordinal (e.g. "2nd day of April, 2026") ---
    # Falls back to today's date if missing or N/A
    if not current_date_raw or current_date_raw.upper() in ("N/A", "NA", "NONE", ""):
        formatted_date = fmt_ordinal_date(date.today())
    elif "day of" in current_date_raw.lower():
        formatted_date = current_date_raw  # already in ordinal format, pass through
    else:
        formatted_date = fmt_ordinal_date(parse_date(current_date_raw))

    # --- MotionType: title case with exceptions (e.g. "Motion to Waive", not "Motion To Waive") ---
    # Small words (prepositions, conjunctions, articles) stay lowercase unless they are the first word
    _LOWERCASE_WORDS = {"to", "of", "the", "a", "an", "and", "or", "but", "in", "on", "at", "for", "with", "by"}
    if not motion_type or motion_type.upper() in ("N/A", "NA", "NONE", ""):
        motion_type_formatted = "N/A"
    else:
        words = motion_type.split()
        motion_type_formatted = " ".join(
            word.capitalize() if i == 0 or word.lower() not in _LOWERCASE_WORDS else word.lower()
            for i, word in enumerate(words)
        )

    # --- CourtDistrict: uppercase; default to "DISTRICT OF FLORIDA" if missing/N/A ---
    if not court_district_raw or court_district_raw.strip().upper() in ("", "N/A", "NA", "NONE"):
        court_district_capitalized = "DISTRICT OF FLORIDA"
    else:
        court_district_capitalized = court_district_raw.upper()

    # --- MiscMailListings: format "Name|email" entries into "Name\nemail" blocks ---
    # Input is a JSON string (e.g. '["Name|email", ...]') or "N/A"
    if not misc_mail_listings or str(misc_mail_listings).strip().upper() in ("N/A", "NA", "NONE", ""):
        misc_mail_formatted = ""
    else:
        try:
            entries = json.loads(misc_mail_listings) if isinstance(misc_mail_listings, str) else misc_mail_listings
            blocks = []
            for entry in entries:
                if "|" in entry:
                    name, email = entry.split("|", 1)
                    blocks.append(f"{name.strip()}\n{email.strip()}")
                else:
                    blocks.append(entry.strip())
            misc_mail_formatted = "\n\n".join(blocks)
        except Exception:
            misc_mail_formatted = str(misc_mail_listings)

    # --- Notice of Hearing conditional logic ---
    # hearing = True  → docket +3, "and the Notice of Hearing were", "Verified {MotionType}"
    # hearing = False → docket +2, "was", MotionType unchanged
    # N/A fields are preserved as-is throughout
    if _is_truthy(if_notice_of_hearing):
        # With hearing: docket offset +3
        try:
            docket_final = str(int(docket_motion) + 3) if docket_motion.upper() not in ("N/A", "NA", "NONE", "") else "N/A"
        except (ValueError, AttributeError):
            docket_final = docket_motion
        was_or_were_final   = "and the Notice of Hearing were"
        motion_type_final   = f"{motion_type_formatted}" if motion_type_formatted not in ("N/A", "") else "N/A"
    else:
        # Without hearing: docket offset +2
        try:
            docket_final = str(int(docket_motion) + 2) if docket_motion.upper() not in ("N/A", "NA", "NONE", "") else "N/A"
        except (ValueError, AttributeError):
            docket_final = docket_motion
        was_or_were_final   = "was"
        motion_type_final   = motion_type_formatted if motion_type_formatted not in ("N/A", "") else "N/A"

    # Split "A and B" or "A, B, and C" into one name per line
    raw_debtor = payload.get("DebtorName", "")
    import re as _re
    _parts = [p.strip() for p in _re.split(r',\s*(?:and\s+)?|\s+and\s+', raw_debtor) if p.strip()]
    header_debtor_name = "\n".join(_parts) if _parts else raw_debtor

    return {
        "HeaderDebtorName": header_debtor_name,
        "DebtorName": debtor_name,
        "CaseNumber": case_number,
        "CourtDistrict": court_district_capitalized,
        "Chapter": chapter,
        "CurrentDate": formatted_date or current_date_raw,
        "TrusteeName": trustee_name,
        "TrustEmail": trustee_email,
        "USTemail": us_trustee_email,
        "MiscMailListings": misc_mail_formatted,
        "IfNoticeofHearing": if_notice_of_hearing,
        "WasOrWere": was_or_were_final,
        "MotionType": motion_type_final,
        "DocketMotion": docket_final,
    }


# -------------------- render helpers --------------------
def render_docx(template_docx: Path, context: dict, name_slug: str) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_docx = OUT_DIR / f"{name_slug}.docx"

    doc = DocxTemplate(template_docx)
    render_context = {k: v for k, v in context.items() if not k.startswith("_")}
    doc.render(render_context)
    doc.save(out_docx)
    warn_unresolved_placeholders(out_docx)
    return out_docx


# -------------------- orchestration --------------------
def resolve_template_from_payload(context: dict) -> Path:
    ensure_docx_template()
    # Always use primary template regardless of notice hearing status
    return TEMPLATE_PRIMARY


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
    ctx = build_context(payload_data)
    template = resolve_template_from_payload(ctx)
    name_slug = output_basename or OUTPUT_BASENAME
    out_docx = render_docx(template, ctx, name_slug)
    out_pdf = convert_to_pdf(out_docx)
    return out_docx, out_pdf


# -------------------- main --------------------
def main():
    ensure_docx_template()
    payload = load_payload()
    ctx = build_context(payload)
    template = resolve_template_from_payload(ctx)
    out_docx = render_docx(template, ctx, OUTPUT_BASENAME)
    print("DOCX generated:", out_docx.resolve())


def test_build_context():
    test_payload = {
        "CaseNumber": "25-21814-PDR",
        "Chapter": "13",
        "DebtorName": "Laura Marie Cavazos and Moises Rafael Cavazos",
        "DateOne": "October 7, 2025",
        "DateTwo": "2026-04-02",
        "employment_explanation": "",
        "CourtDistrict": "Southern District of Florida",
        "MotionType": "Motion to Waive",
        "TrusteeName": "Robin R Weiner",
        "TrustEmail": "auto-forward-ecf@ch13weiner.com",
        "USTemail": "USTPRegion21.MM.ECF@usdoj.gov",
        "CurrentDate": "2nd day of April, 2026",
        "IfNoticeofHearing": False, #"Yes",
        "WasOrWere": "N/A",
        "DocketMotion": "22",
        "MiscMailListings": "[\"Michael S Feldman|michaelf@wassersteinpa.com\", \"Nicole W Giuliano, Esq.|nicole@giulianolaw.com\", \"Leslie B Gomez|ecfflsb@aldridgepite.com\", \"Leslie J Rushing|lrushing@hillwallack.com\", \"Giselle Velez|gvelez@rasflaw.com\"]",
    }

    # Print resolved context
    ctx = build_context(test_payload)
    print("=== Context ===")
    for key, value in ctx.items():
        print(f"{key}: {repr(value)}")

    # Generate DOCX
    print("\n=== Generating DOCX ===")
    ensure_docx_template()
    template = resolve_template_from_payload(ctx)
    out_docx = render_docx(template, ctx, OUTPUT_BASENAME)
    print(f"DOCX generated: {out_docx.resolve()}")


if __name__ == "__main__":
    test_payload = {
        "CaseNumber":        "25-21814-PDR",
        "Chapter":           "13",
        "DebtorName":        "Laura Marie Cavazos and Moises Rafael Cavazo",
        "CourtDistrict":     "Southern District of Florida",
        "MotionType":        "Motion to Waive",
        "TrusteeName":       "Robin R Weiner",
        "TrustEmail":        "auto-forward-ecf@ch13weiner.com",
        "USTemail":          "USTPRegion21.MM.ECF@usdoj.gov",
        "CurrentDate":       "April 6, 2026",
        "IfNoticeofHearing": False,
        "DocketMotion":      "22",
        "MiscMailListings":  "[\"Michael S Feldman|michaelf@wassersteinpa.com\", \"Nicole W Giuliano, Esq.|nicole@giulianolaw.com\"]",
    }

    print("Testing certificate of service functionality...")

    docx_path, pdf_path = generate_both_formats_from_payload(test_payload)
    print(f"DOCX generated: {docx_path}")
    print(f"PDF generated: {pdf_path}")

