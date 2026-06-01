"""
Motion to Value filling functionality.
This module handles the creation and filling of order on motion to value documents.
"""

from __future__ import annotations
from pathlib import Path
from .generator_common import generate_document
from zipfile import ZipFile
import re
from typing import Dict, Any
from docxtpl import DocxTemplate
from dateutil.parser import parse as parse_date

# -------------------- paths --------------------
BASE_DIR = Path(__file__).parent.resolve()
OUT_DIR  = BASE_DIR / "out"

TEMPLATE_YES_CLAIM = BASE_DIR.parent / "templates" / "order_motion_to_value_yes_claim.docx"
TEMPLATE_NO_CLAIM = BASE_DIR.parent / "templates" / "order_motion_to_value_no_claim.docx"

OUTPUT_BASENAME = "Order_Motion_to_Value_FILLED"

# -------------------- helpers --------------------
def ensure_docx_template(template_path: Path) -> Path:
    if template_path.exists():
        return template_path
    raise SystemExit(f"Template not found: {template_path}")


def warn_unresolved_placeholders(docx_path: Path):
    """After render, warn if any '{{...}}' leftovers remain."""
    try:
        with ZipFile(docx_path, "r") as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
        leftovers = re.findall(r"{{[^}]+}}", xml)
        if leftovers:
            print("\nWARNING: Unresolved placeholders still in output:")
            for tok in leftovers:
                print("  -", tok)
            print("Check spelling/case in the template and context keys above.\n")
    except Exception:
        pass


# -------------------- PDF conversion functions --------------------
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
    import shutil
    import subprocess
    if not shutil.which("soffice"):
        print("WARNING: soffice not found in PATH")
        return None
    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        result = subprocess.run([
            "soffice", "--headless", "--convert-to", "pdf",
            "--outdir", str(OUT_DIR), str(docx_path)
        ], check=True, capture_output=True, text=True)
        
        pdf_path = docx_path.with_suffix(".pdf")
        if pdf_path.exists():
            return pdf_path
        else:
            print(f"WARNING: PDF conversion completed but output file not found: {pdf_path}")
            print(f"LibreOffice output: {result.stdout}")
            return None
    except subprocess.CalledProcessError as e:
        print(f"ERROR: LibreOffice conversion failed: {e}")
        print(f"Return code: {e.returncode}")
        print(f"Output: {e.stdout}")
        print(f"Error: {e.stderr}")
        return None
    except Exception as e:
        print(f"ERROR: Unexpected error during PDF conversion: {e}")
        return None


def convert_to_pdf(docx_path: Path) -> Path:
    """Convert DOCX to PDF. Returns Path or raises RuntimeError if conversion fails."""
    pdf = convert_to_pdf_wordcom(docx_path) or convert_to_pdf_libreoffice(docx_path)
    if not pdf or not pdf.exists():
        raise RuntimeError(
            "Could not convert to PDF. Install MS Word + pywin32 or LibreOffice (soffice on PATH)."
        )
    return pdf

def convert_to_pdf_safe(docx_path: Path) -> Path | None:
    """Safely convert DOCX to PDF. Returns Path or None if conversion fails."""
    try:
        return convert_to_pdf(docx_path)
    except RuntimeError:
        return None


# -------------------- context builder --------------------
def build_context(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build the context dictionary for template rendering.

    This function:
    1. Determines claim path based on WithClaim ("Yes" → yes-claim, "No" → no-claim)
    2. Formats TrusteeCalendar into ordinal date string
    3. Computes Value1/Value2 from AmountSecured/AmountClaimed (yes-claim path)
    4. Computes Price from Value × (1 + rate) or (Value1 + Value2) × (1 + rate)
    5. Formats all dollar fields with $ prefix for the template
    """

    # Split "A and B" or "A, B, and C" into one name per line
    import re as _re
    _raw_debtor = payload.get("DebtorName", "")
    _parts = [p.strip() for p in _re.split(r',\s*(?:and\s+)?|\s+and\s+', _raw_debtor) if p.strip()]
    header_debtor_name = "\n".join(_parts) if _parts else _raw_debtor

    # Determine claim status from WithClaim:
    #   "Yes" or "N/A" → lender HAS filed a proof of claim (yes-claim path)
    #   "No"           → lender has NOT filed a proof of claim (no-claim path)
    with_claim = (payload.get("WithClaim") or "").strip()

    # Format TrusteeCalendar — output: "April 6th, 2026 at 10:00 AM", or "" if no value
    trustee_calendar_raw = payload.get("TrusteeCalendar", "")
    trustee_calendar = ""
    if trustee_calendar_raw and trustee_calendar_raw.strip().upper() not in ("", "N/A"):
        try:
            parsed = parse_date(trustee_calendar_raw, fuzzy=True)
            day = parsed.day
            suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
            trustee_calendar = parsed.strftime(f"%B {day}{suffix}, %Y at %I:%M %p")
        except Exception:
            trustee_calendar = ""

    # compute Value1 (AmountSecured) and Value2 (AmountClaimed - AmountSecured, floor 0)
    amount_claimed_raw = (payload.get("AmountClaimed") or "N/A")
    amount_secured_raw = (payload.get("AmountSecured") or "N/A")
    percent_raw = (payload.get("Percent") or "N/A")

    if amount_claimed_raw == "N/A" or amount_secured_raw == "N/A":
        value1_str = payload.get("Value1") or "N/A"
        value2_str = payload.get("Value2") or "N/A"
        value1 = None
        value2 = None
    else:
        try:
            amount_claimed_f = float(amount_claimed_raw.replace("$", "").replace(",", ""))
            amount_secured_f = float(amount_secured_raw.replace("$", "").replace(",", ""))
            value1 = amount_secured_f
            value2 = max(0.0, amount_claimed_f - amount_secured_f)
            value1_str = f"${value1:,.2f}"
            value2_str = f"${value2:,.2f}"
        except Exception:
            value1_str = payload.get("Value1") or "N/A"
            value2_str = payload.get("Value2") or "N/A"
            value1 = None
            value2 = None

    # compute PriceYes ((Value1 + Value2) × (1 + rate)) — yes-claim path
    try:
        rate = float(percent_raw.replace("%", "").strip()) / 100
        price_yes_str = f"${(value1 + value2) * (1 + rate):,.2f}"
    except Exception:
        price_yes_str = payload.get("PriceYes") or "N/A"

    # compute PriceNo (Value × (1 + rate)) — no-claim path
    try:
        value_raw = (payload.get("Value") or "0").replace("$", "").replace(",", "").strip()
        price_no_str = f"${float(value_raw) * (1 + rate):,.2f}"
    except Exception:
        price_no_str = payload.get("PriceNo") or "N/A"

    # Path A: lender HAS filed a proof of claim (WithClaim = "Yes")
    if with_claim.upper() == "YES":
        ctx = {
            # Case / party information
            "HeaderDebtorName": header_debtor_name,
            "CaseNumber": payload.get("CaseNumber", ""),
            "ChapterNumber": payload.get("ChapterNumber", ""),
            "DebtorName": payload.get("DebtorName", ""),
            "Creditor": payload.get("Creditor", ""),
            "TrusteeCalendar": trustee_calendar,
            "DocketNumber": payload.get("DocketNumber", ""),

            # Motor vehicle fields
            "CarModel": payload.get("CarModel", ""),
            "VinModel": payload.get("VinModel", ""),
            "Odometer": payload.get("Odometer", ""),

            # Claim slot (lien position from Schedule D)
            "ClaimSlot": payload.get("ClaimSlot", ""),

            # Value1 = AmountSecured, Value2 = AmountClaimed - AmountSecured (floor 0)
            "Value1": "" if value1_str in ("", "N/A") else ("$" + value1_str if not value1_str.startswith("$") else value1_str),
            "Value2": "" if value2_str in ("", "N/A") else ("$" + value2_str if not value2_str.startswith("$") else value2_str),

            # Percent = U.S. prime rate on DateFiled (from service.py lookup table)
            "Percent": "" if percent_raw in ("", "N/A") else percent_raw,

            # Price = (Value1 + Value2) × (1 + rate) — yes-claim path total
            "Price": "" if price_yes_str in ("", "N/A") else ("$" + price_yes_str if not price_yes_str.startswith("$") else price_yes_str),

        }

    # Path B: lender has NOT filed a proof of claim (WithClaim = "No")
    else:
        # Percent = U.S. prime rate on DateFiled (from service.py lookup table)
        final_percent = "" if percent_raw in ("", "N/A") else percent_raw
        # Price = vehicle value × (1 + rate) — no-claim path total
        final_price = "" if price_no_str in ("", "N/A") else price_no_str

        ctx = {
            # Case / party information
            "HeaderDebtorName": header_debtor_name,
            "CaseNumber": payload.get("CaseNumber", ""),
            "ChapterNumber": payload.get("ChapterNumber", ""),
            "DebtorName": payload.get("DebtorName", ""),
            "Creditor": payload.get("Creditor", ""),
            "TrusteeCalendar": trustee_calendar,
            "DocketNumber": payload.get("DocketNumber", ""),

            # Motor vehicle fields
            "CarModel": payload.get("CarModel", ""),
            "VinModel": payload.get("VinModel", ""),
            "Odometer": payload.get("Odometer", ""),

            # Vehicle current value from Schedule A/B (petition)
            "Value": "" if payload.get("Value", "") in ("", "N/A") else ("$" + payload["Value"] if not payload["Value"].startswith("$") else payload["Value"]),

            # Percent = U.S. prime rate on DateFiled
            "Percent": final_percent,

            # Price = Value × (1 + rate) — no-claim path total
            "Price": "" if final_price in ("", "N/A") else ("$" + final_price if not final_price.startswith("$") else final_price),

        }
    
    return ctx


# -------------------- render --------------------
def render_docx(template_docx: Path, ctx: Dict[str, Any], name_slug: str) -> Path:
    """Render the DOCX template with the given context using docxtpl."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_docx = OUT_DIR / f"{name_slug}.docx"
    if out_docx.exists():
        out_docx.unlink()
    
    doc = DocxTemplate(template_docx)
    doc.render(ctx)
    doc.save(out_docx)
    warn_unresolved_placeholders(out_docx)
    return out_docx


# -------------------- orchestration helpers --------------------
def resolve_template_from_payload(payload: dict) -> Path:
    """
    Resolve the template path based on whether a claim was filed.
    
    - If WithClaim is "Yes" or "N/A" → use order_motion_to_value_yes_claim template
    - If WithClaim is "No" → use order_motion_to_value_no_claim template
    """
    with_claim = (payload.get("WithClaim") or "").strip()
    has_claim_filed = with_claim.upper() in ("YES", "N/A", "")
    
    if has_claim_filed:
        template = TEMPLATE_YES_CLAIM
    else:
        template = TEMPLATE_NO_CLAIM
    
    return ensure_docx_template(template)


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
    Generate both DOCX and PDF formats from the payload.
    
    Args:
        payload_data: Dictionary containing the motion data
        output_basename: Optional custom output filename (without extension)
    
    Returns:
        tuple[Path, Path]: (docx_path, pdf_path)
    """
    print(f"INFO: Generating motion value documents...")
    template = resolve_template_from_payload(payload_data)
    print(f"INFO: Template resolved: {template}")
    
    ctx = build_context(payload_data)
    print(f"INFO: Context built with {len(ctx)} fields")
    
    name_slug = output_basename or OUTPUT_BASENAME
    out_docx = render_docx(template, ctx, name_slug)
    print(f"INFO: DOCX generated: {out_docx}")
    
    try:
        out_pdf = convert_to_pdf(out_docx)
        print(f"INFO: PDF generated: {out_pdf}")
    except Exception as e:
        print(f"ERROR: PDF conversion failed: {e}")
        raise
    
    return out_docx, out_pdf


# -------------------- main --------------------
if __name__ == "__main__":

    # Pattern 1: Lender has NOT filed a proof of claim (no-claim path)
    test_payload_no_claim = {
        "CaseNumber": "25-12345-PDR",
        "ChapterNumber": "13",
        "DebtorName": "John Doe",
        "Creditor": "ABC Bank",
        "CarModel": "Ford - Ranger Edge Reg Cab 2003",
        "VinModel": "1FTYR10U63PA95953",
        "Odometer": "170000",
        "Value": "5,000.00",
        "ValueMethod": "KBB",
        "TrusteeCalendar": "April 6th, 2026 at 10:00 AM",
        "DocketNumber": "12",
        "Percent": "7.5",
        "WithClaim": "No",
    }

    # Pattern 2: Lender HAS filed a proof of claim (yes-claim path)
    test_payload_claim_filed = {
        "CaseNumber": "25-12345-PDR",
        "ChapterNumber": "13",
        "DebtorName": "Laura Marie Cavazos and Moises Rafael Cavazos",
        "Creditor": "ABC Bank",
        "CarModel": "Ford - Ranger Edge Reg Cab 2003",
        "VinModel": "1FTYR10U63PA95953",
        "Odometer": "170000",
        "Value": "5,000.00",
        "ValueMethod": "KBB",
        "TrusteeCalendar": "April 6th, 2026 at 10:00 AM",
        "DocketNumber": "12",
        "Percent": "7.5",
        "AmountClaimed": "8,500.00",
        "AmountSecured": "5,000.00",
        "ClaimSlot": "3",
        "WithClaim": "Yes",
    }

    print("Testing Pattern 1: No claim filed (WithClaim=No)...")
    docx_path, pdf_path = generate_both_formats_from_payload(test_payload_no_claim)
    print(f"DOCX generated: {docx_path}")
    print(f"PDF generated: {pdf_path}")

    print("\nTesting Pattern 2: Claim filed (WithClaim=Yes)...")
    docx_path, pdf_path = generate_both_formats_from_payload(test_payload_claim_filed)
    print(f"DOCX generated: {docx_path}")
    print(f"PDF generated: {pdf_path}")
