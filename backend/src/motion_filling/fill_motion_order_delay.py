"""
Order on Motion for Delay filling functionality.
This module handles the creation and filling of order on motion for delay documents.
"""

from __future__ import annotations
from pathlib import Path
from .generator_common import generate_document
from zipfile import ZipFile
import json, re
from typing import Dict, Any, Optional
from docxtpl import DocxTemplate
from langchain.chat_models import init_chat_model
from ..config import settings
from ..ai_models import CLAUDE_MODEL_STANDARD, CLAUDE_PROVIDER

# -------------------- paths --------------------
BASE_DIR = Path(__file__).parent.resolve()
OUT_DIR  = BASE_DIR / "out"

TEMPLATE_CANDIDATES = [
    BASE_DIR.parent / "templates" / "order_motion_delay.docx",
]

OUTPUT_BASENAME = "Order_Motion_Delay_FILLED"

# -------------------- helpers --------------------
def ensure_docx_template() -> Path:
    for p in TEMPLATE_CANDIDATES:
        if p.exists():
            return p
    raise SystemExit("Template not found. Place 'order_motion_delay.docx' under templates/ .")


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


# -------------------- AI pre-fill --------------------

# Called by: tasks/pleading_tasks._enrich_prefilled() (order delay motion type only)
def generate_extension_explanation_suggestions(motion_payload: dict = None, session_id: str = None) -> list:
    """
    Generate up to 3 WhyExtensionNeeded suggestions shown as clickable chips at AWAITING_INPUT.

    Searches Schedule D (Creditors Who Have Claims Secured by Property) from the petition
    PDF vectorstore to extract creditor names and secured property/vehicle descriptions
    (including VIN numbers), then uses Claude to draft suggestion sentences in the format:

      "Debtor, [Creditor Name] (Creditor) to file the Reaffirmation Agreement for the
       Debtor's Vehicle, [Year Make Model] with Vin# [VIN] (Vehicle)."

    Returns a list of up to 3 suggestion strings, or [] if no Schedule D data is found.
    """
    try:
        # Step 1 — pull Schedule D context from the petition PDF
        schedule_d_context = ""
        if session_id:
            from ..chatbot.vectorestore import search_vectorstore
            pdf_collection = f"bankruptcy_knowledge_{session_id}"
            try:
                # Four targeted queries merged to maximize Schedule D coverage.
                # Queries 1-2 target property entries; 3-4 specifically target vehicle/VIN
                # entries so they are not crowded out by repeated property chunks.
                queries = [
                    "Schedule D secured creditor property address",
                    "Creditors Who Have Claims Secured by Property describe property secures claim",
                    "vehicle VIN secured claim Kelley Blue Book",
                    "Tesla VIN# secured creditor reaffirmation",
                ]
                seen_contents = set()
                all_docs = []
                for q in queries:
                    for d in search_vectorstore(q, collection_name=pdf_collection, k=6) or []:
                        if hasattr(d, "page_content") and d.page_content not in seen_contents:
                            seen_contents.add(d.page_content)
                            all_docs.append(d)
                if all_docs:
                    schedule_d_context = "\n".join(d.page_content for d in all_docs)
                    print(f"INFO: Retrieved {len(all_docs)} unique Schedule D chunks")
            except Exception as search_err:
                print(f"WARNING: Could not search PDF for Schedule D info: {search_err}")

        if not schedule_d_context:
            print(f"INFO: generate_extension_explanation_suggestions — no Schedule D context found (session_id={session_id!r})")
            return []

        debtor_name = (motion_payload or {}).get("DebtorName", "")
        debtor_ref = debtor_name if debtor_name and debtor_name != "N/A" else "[Debtor Name]"

        # Step 2 — use Claude to extract creditors/assets and build suggestion sentences
        model = init_chat_model(
            CLAUDE_MODEL_STANDARD,
            model_provider=CLAUDE_PROVIDER,
            api_key=settings.ANTHROPIC_API_KEY,
            temperature=0.2,
        )

        prompt = (
            "You are extracting data from Schedule D: Creditors Who Have Claims Secured by Property "
            "from a bankruptcy petition.\n\n"
            "How Schedule D entries are structured:\n"
            "Each entry contains:\n"
            "  - A creditor name (appears near the label 'Creditor's Name')\n"
            "  - A collateral description (appears after 'Describe the property that secures the claim:')\n"
            "    which is either a real property address or a vehicle (Year Make Model + VIN#)\n"
            "IMPORTANT: Each creditor name belongs ONLY to its own entry's collateral. "
            "Do not carry a creditor name from one entry into another entry's collateral.\n\n"
            "Task:\n"
            "1. Find EVERY creditor entry in the data below — scan ALL of it, top to bottom.\n"
            "   For each entry: pair the creditor name with its collateral.\n"
            "   Deduplication: if two entries have the same property address OR the same VIN, "
            "keep only one. Ignore claim numbers (2.1, 2.2, 2.3, etc.).\n"
            "2. For each unique creditor+asset pair extract:\n"
            "   - Vehicle: Year, Make, Model, VIN#\n"
            "   - Real property: street address + city + state + zip only (no legal descriptions)\n"
            "3. Write sentences that ALWAYS combine ALL unique pairs into a single sentence per style. "
            "No period at the end of any sentence. No separate per-pair sentences.\n"
            "   Produce exactly 3 sentence styles, each chaining ALL pairs together:\n\n"
            "   Style 1 — 'directs' (use 'and directs' to join additional pairs):\n"
            f'      "Debtor, {debtor_ref}, directs NR/SMS/CAL (Creditor) to file a Reaffirmation '
            "Agreement for the Debtor's property located at 10646 North Lago Vista Circle, Parkland, FL 33076, "
            "and directs USAA FSB (Creditor) to file a Reaffirmation Agreement for the Debtor's vehicle, "
            'a 2023 Tesla Model Y, VIN #7SAYGAEE3PF674540\"\n\n'
            "   Style 2 — 'requests that' (use 'and that' to join additional pairs):\n"
            f'      "Debtor {debtor_ref} requests that NR/SMS/CAL (Creditor) file a Reaffirmation '
            "Agreement for the property at 10646 North Lago Vista Circle, Parkland, FL 33076, "
            "and that USAA FSB (Creditor) file a Reaffirmation Agreement for the Debtor's vehicle, "
            'a 2023 Tesla Model Y (VIN #7SAYGAEE3PF674540)\"\n\n'
            "   Style 3 — chaining (use 'and' to join additional pairs):\n"
            f'      "Debtor, {debtor_ref}, NR/SMS/CAL (Creditor) to file the Reaffirmation '
            "Agreement for the Debtor's Property at 10646 North Lago Vista Circle, Parkland, FL 33076, "
            "and USAA FSB (Creditor) to file the Reaffirmation Agreement for the Debtor's "
            'Vehicle, 2023 Tesla Model Y with Vin# 7SAYGAEE3PF674540 (Vehicle)\"\n\n'
            "   If only 1 pair found, write the same 3 styles but for that single pair only (no joining needed).\n"
            "4. Return exactly 3 strings in a JSON array. "
            "If no Schedule D data found, return [].\n"
            "Return ONLY a valid JSON array of strings, nothing else.\n\n"
            f"Schedule D data:\n{schedule_d_context}"
        )

        print(f"INFO: schedule_d_context length={len(schedule_d_context)} chars, invoking Claude...")
        response = model.invoke(prompt)
        result = (response.content or "").strip()
        print(f"INFO: Claude raw response: {result[:300]!r}")

        import json as _json
        import re as _re
        match = _re.search(r'\[.*\]', result, _re.DOTALL)
        if match:
            suggestions = _json.loads(match.group())
            if isinstance(suggestions, list) and all(isinstance(s, str) for s in suggestions):
                print(f"INFO: Parsed {len(suggestions)} suggestion(s)")
                return suggestions[:3]
        print("WARNING: Could not parse suggestions from Claude response")
        return []

    except Exception as e:
        print(f"WARNING: Failed to generate extension explanation suggestions: {e}")
        return []


# -------------------- context builder --------------------
def build_context(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build the context dictionary for template rendering.

    This function formats the payload data for the template.
    """

    court_district_raw = payload.get("District", "N/A")

    # --- District: uppercase; default to "" if missing/N/A ---
    if not court_district_raw or court_district_raw.strip().upper() in ("", "N/A", "NA", "NONE"):
        court_district_capitalized = ""
    else:
        court_district_capitalized = court_district_raw.upper()

    # --- OldDischargeability: normalize to "Month D, YYYY" if not already in that format ---
    # OldDischargeabilityDatePlus30 is always recomputed from the (possibly user-edited)
    # OldDischargeability so that frontend edits are reflected in the +30 date.
    raw_date = payload.get("OldDischargeability", "N/A")
    _correct_format = re.compile(r'^[A-Za-z]+ \d{1,2}, \d{4}$')

    if raw_date and raw_date != "N/A":
        if not _correct_format.match(raw_date.strip()):
            # Not in the expected format — parse and reformat
            try:
                from datetime import timedelta
                from dateutil.parser import parse as _parse_date
                parsed = _parse_date(raw_date)
                old_dischargeability = parsed.strftime(f"%B {parsed.day}, %Y")
            except Exception:
                old_dischargeability = raw_date
        else:
            old_dischargeability = raw_date.strip()

        # Always recompute +30 from the final OldDischargeability value
        try:
            from datetime import timedelta
            from dateutil.parser import parse as _parse_date
            parsed_final = _parse_date(old_dischargeability)
            plus_30 = parsed_final + timedelta(days=30)
            old_dischargeability_plus_30 = plus_30.strftime(f"%B {plus_30.day}, %Y")
        except Exception:
            old_dischargeability_plus_30 = "N/A"
    else:
        old_dischargeability = "N/A"
        old_dischargeability_plus_30 = "N/A"
    
    # Split "A and B" or "A, B, and C" into one name per line
    raw_debtor = payload.get("DebtorName", "")
    import re as _re
    _parts = [p.strip() for p in _re.split(r',\s*(?:and\s+)?|\s+and\s+', raw_debtor) if p.strip()]
    header_debtor_name = "\n".join(_parts) if _parts else raw_debtor

    ctx = {
        "HeaderDebtorName":              header_debtor_name,
        "DebtorName":                    payload.get("DebtorName", ""),
        "CaseNumber":                    payload.get("CaseNumber", ""),
        "ChapterNumber":                 payload.get("ChapterNumber", ""),
        "DocketNumber":                  payload.get("DocketNumber", "N/A"),
        "District":                      court_district_capitalized,
        "OldDischargeability":           old_dischargeability,
        "OldDischargeabilityDatePlus30": old_dischargeability_plus_30,
        "WhyExtensionNeeded":            payload.get("WhyExtensionNeeded", "N/A"),
        "WithMotion":                    payload.get("WithMotion", False),
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
    """Resolve the template path. For order delay, we use a single template."""
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
    Generate both DOCX and PDF formats from the payload.

    Args:
        payload_data: Dictionary containing the order delay data
        output_basename: Optional custom output filename (without extension)

    Returns:
        tuple[Path, Path]: (docx_path, pdf_path)
    """
    print(f"INFO: Generating order delay documents...")
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
    test_payload = {
        "DebtorName":                    "Laura Marie Cavazos and Moises Rafael Cavazos",
        "CaseNumber":                    "25-14980-PDR",
        "ChapterNumber":                 "13",
        "DocketNumber":                  "42",
        "OldDischargeability":           "March 24, 2026",
        "OldDischargeabilityDatePlus30": "April 23, 2026",
        "WhyExtensionNeeded":            "Debtor, Jacques Fenelon, NR/SMS/CAL (Creditor) to file the Reaffirmation Agreement for the Debtor's Property at 10646 North Lago Vista Circle, Parkland, FL 33076, and USAA FSB (Creditor) to file the Reaffirmation Agreement for the Debtor's Vehicle, 2023 Tesla Model Y with Vin# 7SAYGAEE3PF674540 (Vehicle)",
        "WithMotion":                    False,
    }

    print("Testing order delay functionality...")

    docx_path, pdf_path = generate_both_formats_from_payload(test_payload)
    print(f"DOCX generated: {docx_path}")
    print(f"PDF generated: {pdf_path}")
