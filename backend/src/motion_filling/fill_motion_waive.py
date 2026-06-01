from pathlib import Path
from .generator_common import generate_document
from zipfile import ZipFile
import subprocess, shutil, re
from docxtpl import DocxTemplate
from dateutil.parser import parse as parse_date
from datetime import date, datetime
from langchain.chat_models import init_chat_model

from ..config import settings
from ..ai_models import CLAUDE_MODEL_STANDARD, CLAUDE_PROVIDER

BASE_DIR = Path(__file__).parent.resolve()
OUT_DIR  = BASE_DIR / "out"

# Template for motion to waive
TEMPLATE_CANDIDATES = [
    BASE_DIR.parent / "templates" / "motion_to_waive.docx",
]

# ---------- helpers ----------

def ensure_docx_template() -> Path:
    """Find template; if it's .doc, try to convert to .docx via Word COM."""
    for p in TEMPLATE_CANDIDATES:
        if p.exists():
            if p.suffix.lower() == ".docx":
                return p
            docx_out = p.with_suffix(".docx")
            if convert_doc_to_docx(p, docx_out) and docx_out.exists():
                return docx_out
            raise SystemExit(
                f"Template is .doc and automatic conversion failed.\n"
                f"Open in Word and Save As .docx, then re-run.\nProblem file: {p}"
            )
    raise SystemExit("Template not found. Tried:\n  " + "\n  ".join(str(x) for x in TEMPLATE_CANDIDATES))

def convert_doc_to_docx(doc_path: Path, out_path: Path) -> bool:
    try:
        import win32com.client as win32
    except Exception:
        return False
    try:
        word = win32.gencache.EnsureDispatch("Word.Application")
        word.Visible = False
        doc = word.Documents.Open(str(doc_path.resolve()))
        # wdFormatXMLDocument = 12
        doc.SaveAs(str(out_path.resolve()), FileFormat=12)
        doc.Close(False)
        word.Quit()
        return True
    except Exception:
        try:
            word.Quit()
        except Exception:
            pass
        return False

def convert_to_pdf_wordcom(docx_path: Path) -> Path | None:
    try:
        import win32com.client as win32
    except Exception:
        return None
    pdf_path = docx_path.with_suffix(".pdf")
    word = win32.gencache.EnsureDispatch("Word.Application")
    word.Visible = False
    doc = word.Documents.Open(str(docx_path.resolve()))
    # wdExportFormatPDF = 17
    doc.ExportAsFixedFormat(str(pdf_path.resolve()), 17)
    doc.Close(False)
    word.Quit()
    return pdf_path

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

def fmt_long(dt_like) -> str:
    """
    Formats a date into 'Month Day, Year' (e.g. 'September 26, 2025')
    If the input cannot be parsed as a date, returns the original string as-is.
    """
    if not dt_like:
        return ""
    try:
        d = dt_like if isinstance(dt_like, date) else parse_date(str(dt_like)).date()
        return f"{d.strftime('%B')} {d.day}, {d.year}"
    except Exception:
        # If not a normal date, just return the literal
        return str(dt_like)

def fmt_ordinal_day(day: int) -> str:
    """
    Convert day number to ordinal format (1st, 2nd, 3rd, 4th, etc.)
    """
    if 10 <= day % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"

def fmt_ordinal_date(dt_like) -> str:
    """
    Formats a date into ordinal format: '10th day of December 2025'
    If the input cannot be parsed as a date, returns the original string as-is.
    """
    if not dt_like:
        return ""
    try:
        d = dt_like if isinstance(dt_like, date) else parse_date(str(dt_like)).date()
        ordinal_day = fmt_ordinal_day(d.day)
        return f"{ordinal_day} day of {d.strftime('%B')} {d.year}"
    except Exception:
        # If not a normal date, just return the literal
        return str(dt_like)

# ---------- AI pre-fill ----------

# Called by: tasks/pleading_tasks._enrich_prefilled() (waive motion type only)
def generate_employment_explanation_suggestions(motion_payload: dict = None, session_id: str = None) -> list:
    """
    Generate 3 distinct employment descriptions shown as clickable chips at AWAITING_INPUT.

    The first suggestion prefills the textarea; all 3 are shown as chips (truncated in the UI).
    Searches the petition PDF vectorstore for real employer/income info, then uses
    Claude to draft 3 vague-but-factual descriptions in formal legal tone.

    Returns a list of 3 suggestion strings, or [] on failure.
    """
    try:
        # Step 1 — pull employment/income context from the petition PDF
        employment_context = ""
        if session_id:
            from ..chatbot.vectorestore import search_vectorstore
            pdf_collection = f"bankruptcy_knowledge_{session_id}"
            try:
                docs = search_vectorstore(
                    "employer occupation income employment Schedule I",
                    collection_name=pdf_collection,
                    k=5,
                )
                if docs:
                    employment_context = "\n".join(
                        d.page_content for d in docs if hasattr(d, "page_content")
                    )
            except Exception as search_err:
                print(f"WARNING: Could not search PDF for employment info: {search_err}")

        debtor_name = (motion_payload or {}).get("DebtorName", "")
        debtor_ref = f"The Debtor, {debtor_name}," if debtor_name and debtor_name != "N/A" else "The Debtor"

        context_section = f"\n\nPetition data:\n{employment_context}" if employment_context else ""

        # Step 2 — generate 3 distinct descriptions using Claude
        model = init_chat_model(
            CLAUDE_MODEL_STANDARD,
            model_provider=CLAUDE_PROVIDER,
            api_key=settings.ANTHROPIC_API_KEY,
            temperature=0.4,
        )

        prompt = (
            f"Write 3 distinct employment descriptions for a Motion to Waive Filing Fee. "
            f"Each must begin with '{debtor_ref}'. Rules:\n"
            "- Do not state the exact job title; be vague about the position\n"
            "- Use any employer or industry info found in the petition data below\n"
            "- Each description is 2 short sentences, no filler words\n"
            "- State that the role involves handling sensitive consumer information\n"
            "- State that the employer places significant trust in them to handle it\n"
            "- Formal third-person legal tone\n"
            "- Make each of the 3 descriptions meaningfully different in phrasing\n"
            "- Return ONLY a valid JSON array of 3 strings, nothing else\n\n"
            "Example:\n"
            "[\n"
            f"  \"{debtor_ref} is employed by an insurance firm where her daily responsibilities involve "
            "the opening of incoming customer accounts and the handling of their sensitive personal information.\",\n"
            f"  \"{debtor_ref} has been employed in her current position for approximately four years, where "
            "her responsibilities require her employer to place significant trust in her to handle sensitive "
            "consumer information. Her role involves the regular processing and management of confidential "
            "personal data belonging to members of the public.\",\n"
            f"  \"{debtor_ref} holds a position of trust in which the employer requires strict confidentiality "
            "in the handling of sensitive consumer data, and any breach of that trust would result in "
            "immediate termination.\"\n"
            "]\n\n"
            "Return only the JSON array, nothing else."
            f"{context_section}"
        )

        response = model.invoke(prompt)
        result = (response.content or "").strip()

        import json as _json
        import re as _re
        match = _re.search(r'\[.*\]', result, _re.DOTALL)
        if match:
            suggestions = _json.loads(match.group())
            if isinstance(suggestions, list) and all(isinstance(s, str) for s in suggestions):
                return suggestions[:3]
        # Fallback: return raw result as single item
        return [result] if result else []

    except Exception as e:
        print(f"WARNING: Failed to generate employment explanation suggestion: {e}")
        return []


# ---------- context build ----------

def build_context(ai: dict) -> dict:
    """
    Build context dictionary for motion to waive template.
    
    Expected payload fields:
    - CaseNumber: Case number (may include judge initial)
    - Chapter: Chapter number (e.g., "13")
    - DebtorName: Debtor's full name
    - DateOne: Date of filing (formatted as "September 26, 2025")
    - DateTwo: Current date (automatically set, formatted as "10th day of December 2025")
    - EmploymentExplanation: Manual input with AI enhancement
    
    Note: Conclusion is fixed in the template and not part of the payload.
    """
    # Extract fields from payload
    case_number = (ai.get("CaseNumber") or "").strip()
    chapter = str(ai.get("Chapter") or "").strip()
    debtor_name = (ai.get("DebtorName") or "").strip()
    date_one_raw = ai.get("DateOne") or ""
    date_two_raw = ai.get("DateTwo") or ""
    employment_explanation_raw = (ai.get("EmploymentExplanation") or "N/A").strip()
    
    # Format DateOne if it's a date string
    date_one = date_one_raw
    if date_one_raw and date_one_raw != "N/A":
        try:
            date_one = fmt_long(date_one_raw)
        except Exception:
            date_one = date_one_raw
    
    # Format DateTwo - use current date if not provided, format as ordinal
    if date_two_raw and date_two_raw != "N/A":
        date_two = fmt_ordinal_date(date_two_raw)
    else:
        # Default to current date formatted as ordinal
        date_two = fmt_ordinal_date(date.today())
    
    # Use provided value or fallback if empty/N/A
    if employment_explanation_raw and employment_explanation_raw.upper() not in ("N/A", "NONE", ""):
        employment_explanation = employment_explanation_raw
    else:
        employment_explanation = "The Debtors have provided no employment explanation."

    import re as _re
    _parts = [p.strip().title() for p in _re.split(r',\s*(?:and\s+)?|\s+and\s+', debtor_name) if p.strip()]
    header_debtor_name = "\n".join(_parts) if _parts else (debtor_name.title() if debtor_name else "")

    ctx = {
        "HeaderDebtorName": header_debtor_name,
        "CaseNumber": case_number,
        "Chapter": chapter,
        "DebtorName": debtor_name.title() if debtor_name else "",
        "DateOne": date_one,
        "DateTwo": date_two,
        "EmploymentExplanation": employment_explanation
    }
    return ctx

# ---------- render ----------

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

def generate_document_from_payload(payload_data: dict, output_basename: str = None, output_type: str = "pdf") -> Path:
    return generate_document(
        payload_data=payload_data,
        output_basename=output_basename,
        output_type=output_type,
        default_basename="motion_waive",
        resolve_template=lambda _data: ensure_docx_template(),
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
    Generate both DOCX and PDF motion documents from payload data.
    
    Args:
        payload_data: Dictionary containing the motion data
        output_basename: Optional custom output filename (without extension)
    
    Returns:
        tuple[Path, Path]: (docx_path, pdf_path)
    """
    template = ensure_docx_template()
    ctx = build_context(payload_data)
    name_slug = output_basename or "motion_waive"
    out_docx = render_docx(template, ctx, name_slug)
    
    # Convert DOCX to PDF
    out_pdf = convert_to_pdf(out_docx)
    
    return out_docx, out_pdf


# -------------------- main --------------------
if __name__ == "__main__":
    test_payload = {
        "CaseNumber":            "25-21814-PDR",
        "Chapter":               "13",
        "DebtorName":            "Laura Marie Cavazos and Moises Rafael Cavazos",
        "DateOne":               "September 26, 2025",
        "DateTwo":               "April 6, 2026",
        "EmploymentExplanation": "The Debtor is employed at a financial services firm where daily responsibilities involve handling sensitive consumer information, and the employer places significant trust in the Debtor to maintain the confidentiality of that data.",
    }

    print("Testing motion to waive functionality...")

    docx_path, pdf_path = generate_both_formats_from_payload(test_payload)
    print(f"DOCX generated: {docx_path}")
    print(f"PDF generated: {pdf_path}")
