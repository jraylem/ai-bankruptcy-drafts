"""
Motion to Value filling functionality.
This module handles the creation and filling of motion to value documents.
"""

from __future__ import annotations
from pathlib import Path
from .generator_common import generate_document
from zipfile import ZipFile
import re
from typing import Dict, Any
from docxtpl import DocxTemplate

# -------------------- paths --------------------
BASE_DIR = Path(__file__).parent.resolve()
OUT_DIR  = BASE_DIR / "out"

TEMPLATE_YES_CLAIM = BASE_DIR.parent / "templates" / "motion_to_value_personal_yes_claim.docx"
TEMPLATE_NO_CLAIM = BASE_DIR.parent / "templates" / "motion_to_value_personal_no_claim.docx"

OUTPUT_BASENAME = "Motion_to_Value_FILLED"

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
    from .pdf_utils import convert_to_pdf_libreoffice as _convert
    return _convert(docx_path, OUT_DIR)


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
    2. Computes Price via Claude: total paid over 60-month loan at prime rate
    3. Formats all dollar fields with $ prefix for the template
    """

    # Check if with_claim yes or no
    with_claim = (payload.get("WithClaim") or "").strip()


    # Check if DescriptionOfProperty has a value input by the user
    has_description_property = bool(payload.get("DescriptionOfProperty"), ) 

    # future logic here, if has description property - ignore car property and use
    # escalate to Nick what would be the document and logic here
    
    # Compute Price: total paid over 60-month loan at prime rate via Claude
    def compute_price(value: str, percent: str) -> str:
        import re
        import anthropic
        from ..ai_models import CLAUDE_MODEL_STANDARD
        from ..config import settings
        try:
            if not value or value == "N/A" or not percent or percent == "N/A":
                return "N/A"
            api_key = settings.ANTHROPIC_API_KEY
            if not api_key:
                raise ValueError("Anthropic API key not configured.")
            client = anthropic.Anthropic(api_key=api_key)
            prompt = (
                f"Over a 60-month duration, how much total will be paid for a {value} loan "
                f"at a {percent}% Prime Rate. "
                "IMPORTANT: Your ENTIRE response must be the total dollar amount and nothing else. "
                "No markdown, no bold, no explanation, no extra text. "
                "If you cannot compute the value, return 'N/A' immediately. "
                "Example: $14,250.00"
            )
            response = client.messages.create(
                model=CLAUDE_MODEL_STANDARD,
                max_tokens=100,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = ""
            for block in response.content:
                if block.type == "text":
                    raw = block.text.strip()
            match = re.search(r"\$[\d,]+\.?\d*", raw)
            if match:
                return match.group(0)
            return "N/A"
        except Exception as e:
            print(f"[error] compute_price: {e}")
            return payload.get("Price", "N/A")

    price = compute_price(payload.get("Value", "N/A"), payload.get("Percent", "N/A"))

    import re as _re
    _raw_debtor = payload.get("DebtorName", "")
    _parts = [p.strip() for p in _re.split(r',\s*(?:and\s+)?|\s+and\s+', _raw_debtor) if p.strip()]
    header_debtor_name = "\n".join(_parts) if _parts else _raw_debtor

    if with_claim.upper() == "YES":
        ctx = {
            # Basic Information
            "HeaderDebtorName": header_debtor_name,
            "CaseNumber": payload.get("CaseNumber", ""),
            "ChapterNumber": payload.get("ChapterNumber", ""),
            "DebtorName": _raw_debtor,
            "Creditor": payload.get("Creditor", ""),

            # Vehicle Information
            "CarModel": payload.get("CarModel", ""),
            "VinModel": payload.get("VinModel", ""),
            "Odometer": payload.get("Odometer", ""),

            # Value Information
            "Value": ("$" + payload["Value"] if payload.get("Value") and not payload["Value"].startswith("$") else payload.get("Value", "")),
            "ValueMethod": payload.get("ValueMethod", ""),
            "ClaimSlot": payload.get("ClaimSlot", ""),
            "Percent": payload.get("Percent", ""),
            "Price": ("$" + price if price and price != "N/A" and not price.startswith("$") else price),
        }

    else:

        ctx = {
            # Basic Information
            "HeaderDebtorName": header_debtor_name,
            "CaseNumber": payload.get("CaseNumber", ""),
            "ChapterNumber": payload.get("ChapterNumber", ""),
            "DebtorName": _raw_debtor,
            "Creditor": payload.get("Creditor", ""),

            # Vehicle Information
            "CarModel": payload.get("CarModel", ""),
            "VinModel": payload.get("VinModel", ""),
            "Odometer": payload.get("Odometer", ""),

            # Value Information
            "Value": ("$" + payload["Value"] if payload.get("Value") and not payload["Value"].startswith("$") else payload.get("Value", "")),
            "ValueMethod": payload.get("ValueMethod", ""),
            "Percent": payload.get("Percent", ""),
            "Price": ("$" + price if price and price != "N/A" and not price.startswith("$") else price),
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
    
    - If WithClaim is "Yes" or "N/A" → use motion_to_value_personal_yes_claim template
    - If WithClaim is "No" → use motion_to_value_personal_no_claim template
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
    # Test the motion value functionality
    test_payload = {
        "CaseNumber": "25-12345",
        "ChapterNumber": "13",
        "DebtorName": "Laura Marie Cavazos and Moises Rafael Cavazos",
        "Creditor": "ABC Bank",
        "CarModel": "Ford - Ranger Edge Reg Cab 2003",
        "VinModel": "1FTYR10U63PA95953",
        "Odometer": "170000",
        "Value": "$5,000",
        "ValueMethod": "KBB",
        "ClaimSlot": "2",
        "Percent": "7.5",
        "Price": "100",
        "WithClaim": "Yes",
    }
    
    print("Testing motion value functionality...")
    
    # Generate both formats
    docx_path, pdf_path = generate_both_formats_from_payload(test_payload)
    print(f"DOCX generated: {docx_path}")
    print(f"PDF generated: {pdf_path}")
