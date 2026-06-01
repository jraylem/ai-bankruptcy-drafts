from __future__ import annotations
from pathlib import Path
from .generator_common import generate_document
from zipfile import ZipFile
import json, re, subprocess, shutil
from datetime import date
from dateutil.parser import parse
from docxtpl import DocxTemplate
import anthropic
from ..config import settings
from ..ai_models import CLAUDE_MODEL_STANDARD, TEMPERATURE_AGENTS

# -------------------- paths --------------------
BASE_DIR = Path(__file__).parent.resolve()
DATAFILE = BASE_DIR / "data" / "payload.delay.json"
OUT_DIR = BASE_DIR / "out"

# Template for motion to delay
TEMPLATE_CANDIDATES = [
    BASE_DIR.parent / "templates" / "motion_to_delay.docx",
]

OUTPUT_BASENAME = "Motion_to_Delay_FILLED"

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
    raise SystemExit("Template not found. Place 'motion_to_delay.docx' under templates/ .")


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


# -------------------- AI recommendation chips for delay reasons --------------------
def generate_delay_reason_recommendations() -> list[str]:
    """
    Generate 2-3 sentence reasons why a debtor would need to delay their discharge
    besides needing to file a reaffirmation, in legal writing.
    Returns a list of recommendation strings.
    """
    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        prompt = (
            "You are a legal writing assistant specializing in bankruptcy law. "
            "Generate exactly 3 different reasons why a debtor would need to delay their discharge "
            "in a Chapter 7 bankruptcy case, EXCLUDING reasons related to reaffirmation agreements. "
            "Each reason should be 2-3 sentences in formal legal prose suitable for a Motion to Delay Discharge.\n\n"
            "Common reasons include:\n"
            "- Debtor needs additional time to complete required financial management course\n"
            "- Debtor is awaiting resolution of a pending adversary proceeding\n"
            "- Debtor needs time to resolve issues with their means test or schedules\n"
            "- Debtor is negotiating with creditors regarding exemptions\n"
            "- Debtor requires additional time to submit amended schedules\n\n"
            "Return ONLY a JSON array of 3 strings, each being a complete reason. No other text."
        )

        response = client.messages.create(
            model=CLAUDE_MODEL_STANDARD,
            max_tokens=600,
            temperature=0.7,
            system="You are a legal writing assistant. Return only valid JSON arrays.",
            messages=[
                {"role": "user", "content": prompt},
            ],
        )

        raw_response = response.content[0].text.strip()

        import json as json_module
        try:
            recommendations = json_module.loads(raw_response)
            if isinstance(recommendations, list) and len(recommendations) >= 1:
                return recommendations[:3]
        except json_module.JSONDecodeError:
            pass

        return [
            "The Debtor requires additional time to complete the mandatory financial management course as required under 11 U.S.C. § 727(a)(11). The Debtor has enrolled in an approved course and anticipates completion within the next thirty days.",
            "The Debtor is currently engaged in negotiations with secured creditors regarding the treatment of certain exempt property. Additional time is necessary to finalize these discussions and ensure proper disposition of the estate assets.",
            "The Debtor needs to file amended schedules to correct certain discrepancies identified during the meeting of creditors. The Debtor requires additional time to gather the necessary documentation and ensure accuracy of the amended filings.",
        ]
    except Exception as e:
        print(f"WARNING: Failed to generate delay recommendations: {e}. Using defaults.")
        return [
            "The Debtor requires additional time to complete the mandatory financial management course as required under 11 U.S.C. § 727(a)(11). The Debtor has enrolled in an approved course and anticipates completion within the next thirty days.",
            "The Debtor is currently engaged in negotiations with secured creditors regarding the treatment of certain exempt property. Additional time is necessary to finalize these discussions and ensure proper disposition of the estate assets.",
            "The Debtor needs to file amended schedules to correct certain discrepancies identified during the meeting of creditors. The Debtor requires additional time to gather the necessary documentation and ensure accuracy of the amended filings.",
        ]


# -------------------- AI enhancement for ReasonForDelay --------------------
def enhance_reason_for_delay(user_input: str) -> str:
    """
    Enhance the user-provided ReasonForDelay into polished legal prose.
    """
    if not user_input or not user_input.strip() or user_input.strip().upper() == "N/A":
        return ""

    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        prompt = (
            "You are a legal writing assistant. Rewrite the following explanation "
            "into formal legal language suitable for a Motion to Delay Discharge "
            "in a bankruptcy case. Return only the enhanced text, no numbering or markers.\n\n"
            f'User input: "{user_input.strip()}"'
        )

        response = client.messages.create(
            model=CLAUDE_MODEL_STANDARD,
            max_tokens=300,
            temperature=TEMPERATURE_AGENTS,
            system="You are a legal writing assistant specializing in bankruptcy motions.",
            messages=[
                {"role": "user", "content": prompt},
            ],
        )

        enhanced_text = response.content[0].text.strip()
        if enhanced_text:
            # Strip any accidental leading numbering
            enhanced_text = re.sub(r"^\s*\d+[\).\-\s]+", "", enhanced_text)
            return enhanced_text.strip()

        return user_input.strip()
    except Exception as e:
        print(f"WARNING: Failed to enhance ReasonForDelay: {e}. Using original input.")
        return user_input.strip()


# -------------------- context builder --------------------
def _is_truthy(value) -> bool:
    """Check if a value is truthy, handling various formats."""
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


def _split_and_clean(value: str) -> list[str]:
    """Split newline-separated values and clean them."""
    if not value or value.strip().upper() == "N/A":
        return []
    # Split by newline
    return [v.strip() for v in value.split("\n") if v.strip()]


def _format_property_list(houses: list[str], addresses: list[str]) -> str:
    """Format property list for ReasonForDelay when ReaffirmationNeeded is true."""
    if not houses and not addresses:
        return ""
    
    parts = []
    max_len = max(len(houses), len(addresses))
    
    for i in range(max_len):
        house = houses[i] if i < len(houses) else ""
        address = addresses[i] if i < len(addresses) else ""
        
        if house and address:
            parts.append(f"{house}, {address} (\"Property\")")
        elif house:
            parts.append(f"{house} (\"Property\")")
        elif address:
            parts.append(f"{address} (\"Property\")")
    
    if len(parts) > 1:
        return ", ".join(parts[:-1]) + f", and {parts[-1]}"
    elif parts:
        return parts[0]
    return ""


def _format_vehicle_list(vehicles: list[str], vins: list[str]) -> str:
    """Format vehicle list for ReasonForDelay when ReaffirmationNeeded is true."""
    if not vehicles and not vins:
        return ""
    
    parts = []
    max_len = max(len(vehicles), len(vins))
    
    for i in range(max_len):
        vehicle = vehicles[i] if i < len(vehicles) else ""
        vin = vins[i] if i < len(vins) else ""
        
        if vehicle and vin:
            parts.append(f"{vehicle}, VIN# {vin} (\"Vehicle\")")
        elif vehicle:
            parts.append(f"{vehicle} (\"Vehicle\")")
        elif vin:
            parts.append(f"VIN# {vin} (\"Vehicle\")")
    
    if len(parts) > 1:
        return ", ".join(parts[:-1]) + f", and {parts[-1]}"
    elif parts:
        return parts[0]
    return ""


def _format_creditors_list(creditors: list[str]) -> str:
    """Format creditors list for Explain when ReaffirmationNeeded is true."""
    if not creditors:
        return ""
    
    if len(creditors) == 1:
        return f"{creditors[0]} (\"Creditors\")"
    elif len(creditors) == 2:
        return f"{creditors[0]} and {creditors[1]} (\"Creditors\")"
    else:
        return ", ".join(creditors[:-1]) + f", and {creditors[-1]} (\"Creditors\")"


def build_context(ai: dict) -> dict:
    """
    Build context dictionary for motion to delay template.
    
    Expected payload fields:
    - DebtorName: Debtor's full name
    - CaseNumber: Case number (may include judge initial)
    - ChapterNumb: Chapter number (e.g., "13")
    - DateFiled: Date the petition was filed
    - ConcludedMeetingDate: Date the meeting of creditors was concluded
    - CurrentDate: Current date
    - Vehicle: Vehicle make/model (newline-separated if multiple)
    - VIN: Vehicle VIN (newline-separated if multiple)
    - House: House/property description (newline-separated if multiple)
    - Address: Property address (newline-separated if multiple)
    - Creditors: Creditor names (newline-separated if multiple)
    - ReaffirmationNeeded: Boolean (true/false)
    - ReasonForDelay: Reason for delay (used when ReaffirmationNeeded is false)
    - Explain: Explanation (used when ReaffirmationNeeded is false)
    - IfReaffirmation: Reaffirmation text (used when ReaffirmationNeeded is true)
    """
    # Extract basic fields
    debtor_name = (ai.get("DebtorName") or "").strip()
    case_number = (ai.get("CaseNumber") or "").strip()
    chapter_number = str(ai.get("ChapterNumb") or "").strip()
    date_filed = (ai.get("DateFiled") or "").strip()
    concluded_meeting_date = (ai.get("ConcludedMeetingDate") or "").strip()
    current_date_raw = (ai.get("CurrentDate") or "").strip()
    
    # Extract property/vehicle/creditor fields (newline-separated if multiple)
    vehicle_raw = (ai.get("Vehicle") or "").strip()
    vin_raw = (ai.get("VIN") or "").strip()
    house_raw = (ai.get("House") or "").strip()
    address_raw = (ai.get("Address") or "").strip()
    creditors_raw = (ai.get("Creditors") or "").strip()
    
    # Parse ReaffirmationNeeded (can be boolean or string)
    reaffirmation_needed = _is_truthy(ai.get("ReaffirmationNeeded", False))
    
    # Format dates
    date_filed_formatted = fmt_long(parse_date(date_filed)) if date_filed else date_filed
    concluded_meeting_date_formatted = fmt_long(parse_date(concluded_meeting_date)) if concluded_meeting_date else concluded_meeting_date
    current_date_formatted = fmt_long(parse_date(current_date_raw)) if current_date_raw else current_date_raw
    
    # Initialize output fields
    if_reaffirmation = ""
    reason_for_delay = ""
    explain = ""
    
    if reaffirmation_needed:
        # When ReaffirmationNeeded is true, set specific values
        if_reaffirmation = "5.  Debtor needs to delay discharge in order to allow the Creditors the time needed to properly file the reaffirmation agreement."
        
        # Parse newline-separated values
        vehicles = _split_and_clean(vehicle_raw)
        vins = _split_and_clean(vin_raw)
        houses = _split_and_clean(house_raw)
        addresses = _split_and_clean(address_raw)
        creditors = _split_and_clean(creditors_raw)
        
        # Format property list
        property_list = _format_property_list(houses, addresses)
        
        # Format vehicle list
        vehicle_list = _format_vehicle_list(vehicles, vins)
        
        # Build ReasonForDelay
        # Format: "property, House1, Address1 ("Property"), House2, Address2 ("Property") (etc), and vehicle, Vehicle1, VIN# VIN1 ("Vehicle") etc"
        if property_list and vehicle_list:
            reason_for_delay = f"The Debtor scheduled their property, {property_list}, and vehicle, {vehicle_list} within their Chapter 7 schedules."
        elif property_list:
            reason_for_delay = f"The Debtor scheduled their property, {property_list} within their Chapter 7 schedules."
        elif vehicle_list:
            reason_for_delay = f"The Debtor scheduled their vehicle, {vehicle_list} within their Chapter 7 schedules."
        else:
            reason_for_delay = "The Debtor scheduled their property and vehicle within their Chapter 7 schedules."
        
        # Build Explain
        creditors_formatted = _format_creditors_list(creditors)
        if creditors_formatted:
            explain = f"The Debtor expressed their intent to reaffirm the debts for the Property for the debt that is owed to {creditors_formatted} in the statement of intentions."
        else:
            explain = "The Debtor expressed their intent to reaffirm the debts for the Property in the statement of intentions."
    else:
        # When ReaffirmationNeeded is false, use AI-enhanced ReasonForDelay only (no Explain)
        raw_reason = (ai.get("ReasonForDelay") or "").strip()

        reason_for_delay = enhance_reason_for_delay(raw_reason) if raw_reason and raw_reason.upper() != "N/A" else ""
        explain = ""
        if_reaffirmation = ""
    
    # Extract District from payload (or default to "SOUTHERN")
    district = (ai.get("District") or "SOUTHERN").strip().upper()

    import re as _re
    _parts = [p.strip() for p in _re.split(r',\s*(?:and\s+)?|\s+and\s+', debtor_name) if p.strip()]
    header_debtor_name = "\n".join(_parts) if _parts else debtor_name

    return {
        "HeaderDebtorName": header_debtor_name,
        "DebtorName": debtor_name,
        "CaseNumber": case_number,
        "ChapterNumb": chapter_number,
        "ChapterNumber": chapter_number,  # Alias for template header
        "District": district,
        "DateFiled": date_filed_formatted,
        "ConcludedMeetingDate": concluded_meeting_date_formatted,
        "ReasonForDelay": reason_for_delay,
        "IfReaffirmation": if_reaffirmation,
        "CurrentDate": current_date_formatted or current_date_raw,
        "Vehicle": vehicle_raw,
        "VIN": vin_raw,
        "House": house_raw,
        "Address": address_raw,
        "Creditors": creditors_raw,
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
    """Resolve the correct template. For delay, we use a single template file."""
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
    test_payload = {
        "DebtorName":           "Laura Marie Cavazos and Moises Rafael Cavazos",
        "CaseNumber":           "25-14980-PDR",
        "ChapterNumb":          "13",
        "DateFiled":            "March 1, 2025",
        "ConcludedMeetingDate": "April 10, 2025",
        "CurrentDate":          "April 6, 2026",
        "ReaffirmationNeeded":  True,
        "Vehicle":              "2023 Toyota Camry",
        "VIN":                  "4T1B11HK0JU123456",
        "House":                "",
        "Address":              "",
        "Creditors":            "ABC Auto Finance",
        "ReasonForDelay":       "Counsel requires additional time to review the reaffirmation agreement.",
        "District":             "SOUTHERN",
    }

    print("Testing motion to delay functionality...")

    docx_path, pdf_path = generate_both_formats_from_payload(test_payload)
    print(f"DOCX generated: {docx_path}")
    print(f"PDF generated: {pdf_path}")

