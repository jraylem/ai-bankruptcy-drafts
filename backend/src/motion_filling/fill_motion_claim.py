from __future__ import annotations
from pathlib import Path
from .generator_common import generate_document
from zipfile import ZipFile
import json, re
from datetime import date
from dateutil.parser import parse
from docxtpl import DocxTemplate
from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage
from ..config import settings
from ..ai_models import CLAUDE_MODEL_FAST, CLAUDE_PROVIDER, TEMPERATURE_ENHANCE

# -------------------- paths --------------------
BASE_DIR = Path(__file__).parent.resolve()
DATAFILE = BASE_DIR / "data" / "payload.claim.json"
OUT_DIR = BASE_DIR / "out"

# Use the standard template file inside templates folder
TEMPLATE_CANDIDATES = [
    BASE_DIR.parent / "templates" / "motion_to_claim.docx",
]

OUTPUT_BASENAME = "Motion_to_Claim_FILLED"

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
    raise SystemExit("Template not found. Place 'motion_to_claim.docx' under templates/ .")


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
    from .pdf_utils import convert_to_pdf_libreoffice as _convert
    return _convert(docx_path, OUT_DIR)

def convert_to_pdf(docx_path: Path) -> Path:
    pdf = convert_to_pdf_wordcom(docx_path) or convert_to_pdf_libreoffice(docx_path)
    if not pdf or not pdf.exists():
        raise RuntimeError(
            "Could not convert to PDF. Install MS Word + pywin32 or LibreOffice (soffice on PATH)."
        )
    return pdf

# -------------------- AI enhancement helpers --------------------

def _clean_fragment(text: str, remove_leading: str | None = None, strip_trailing_punct: bool = True) -> str:
    """Minimal cleaner for AI fragments: strip quotes/commas and optionally trailing punctuation."""
    if not text:
        return ""
    s = text.strip().strip('"').strip("'")
    if remove_leading and s.lower().startswith(remove_leading.lower()):
        s = s[len(remove_leading):].strip()
    # Strip leading commas/spaces and trailing .,;: and spaces
    s = s.lstrip(", ")
    if strip_trailing_punct:
        s = re.sub(r"[\s\.,;:]+$", "", s)
    return s

def _normalize_defined_term_debtor(text: str) -> str:
    """Normalize the defined term 'Debtor' capitalization (Debtor, Debtor's, the Debtor).
    
    NOTE: Preserves "The Debtor" or "The Debtor's" at sentence start to avoid making first letter lowercase.
    """
    if not text:
        return text
    # Normalize possessive first to avoid partial overlaps
    s = re.sub(r"\bdebtor's\b", "Debtor's", text, flags=re.IGNORECASE)
    # Then normalize the noun
    s = re.sub(r"\bdebtor\b", "Debtor", s, flags=re.IGNORECASE)
    
    # Check if sentence starts with "The Debtor" - preserve capitalization at start
    starts_with_the_debtor = re.match(r"^The\s+Debtor", s, flags=re.IGNORECASE)
    
    if starts_with_the_debtor:
        # Preserve "The Debtor" at start - only normalize mid-sentence instances using negative lookbehind
        s = re.sub(r"(?<!^)(?<!\A)\bthe\s+Debtor\b", "the Debtor", s, flags=re.IGNORECASE)
    else:
        # Normalize all "the Debtor" instances
        s = re.sub(r"\bthe\s+Debtor\b", "the Debtor", s, flags=re.IGNORECASE)
    
    return s

def _force_third_person(text: str) -> str:
    """Best-effort conversion of first-person phrasing to third person.

    Handles common pronouns and simple verb forms. We keep the transformation
    conservative to avoid overreach and then pass through
    _normalize_defined_term_debtor for consistent casing of the defined term.
    """
    if not text:
        return text
    s = text
    # Convert "the undersigned" / "undersigned" to "the Debtor"
    s = re.sub(r"\bthe\s+undersigned's\b", "the Debtor's", s, flags=re.IGNORECASE)
    s = re.sub(r"\bthe\s+undersigned\b", "the Debtor", s, flags=re.IGNORECASE)
    s = re.sub(r"\bundersigned's\b", "the Debtor's", s, flags=re.IGNORECASE)
    s = re.sub(r"\bundersigned\b", "the Debtor", s, flags=re.IGNORECASE)
    # Basic pronoun replacements
    s = re.sub(r"\b[Ii]\s+am\b", "the Debtor is", s)
    s = re.sub(r"\b[Ii]\s+was\b", "the Debtor was", s)
    s = re.sub(r"\b[Ii]\s+have\b", "the Debtor has", s)
    s = re.sub(r"\b[Ii]\b", "the Debtor", s)
    s = re.sub(r"\bmy\b", "the Debtor's", s, flags=re.IGNORECASE)
    s = re.sub(r"\bme\b", "the Debtor", s, flags=re.IGNORECASE)
    s = re.sub(r"\bmine\b", "the Debtor's", s, flags=re.IGNORECASE)
    return _normalize_defined_term_debtor(s)

def _capitalize_sentences(text: str) -> str:
    """Ensure proper capitalization at the start of each sentence."""
    if not text:
        return text
    
    # Split by sentence-ending punctuation followed by space
    sentences = re.split(r'([.!?]+\s+)', text)
    
    result = []
    for i, part in enumerate(sentences):
        if i % 2 == 0:  # This is actual sentence content, not punctuation
            if part:
                # Find first alphabetic character and capitalize it
                m = re.search(r'[A-Za-z]', part)
                if m:
                    idx = m.start()
                    part = part[:idx] + part[idx].upper() + part[idx+1:]
            result.append(part)
        else:  # This is punctuation + space
            result.append(part)
    
    return ''.join(result)

# -------------------- AI enhancement for Basis --------------------

def enhance_basis_for_objection(user_input: str) -> str:
    """
    Enhance user-provided basis for objection using GPT with professional legal language.
    
    Args:
        user_input: Raw user input for basis of objection
        
    Returns:
        Enhanced legal text, or original input if enhancement fails
    """
    if not user_input or not user_input.strip():
        return ""
    
    try:
        model = init_chat_model(
            CLAUDE_MODEL_FAST,
            model_provider=CLAUDE_PROVIDER,
            api_key=settings.ANTHROPIC_API_KEY,
            temperature=TEMPERATURE_ENHANCE,
            max_tokens=300,
        )

        system_msg = "You are a legal writing assistant specializing in bankruptcy motions. Your role is to improve presentation while preserving all user-provided facts. Always use proper grammar, punctuation, and capitalization."

        prompt = """You are a legal writing assistant. Transform the user's input into professional legal language for an Objection to Claim in a bankruptcy case.

CRITICAL RULES:
1. PRESERVE ALL FACTS: Keep every detail, reason, and circumstance the user mentioned - do not omit anything. It is also important that as much as possible the user's input words are preserved in the output.
2. IMPROVE PRESENTATION: Convert to third person ("the Debtor"), improve grammar, and use formal legal tone.
3. DO NOT ADD NEW INFORMATION: Only rephrase what the user said - do not introduce new facts, dates, amounts, or circumstances.
4. COMPLETE SENTENCES: Write as one or more complete sentences in formal legal language suitable for an objection to claim.
5. PROPER GRAMMAR & PUNCTUATION: Ensure correct capitalization (especially "The Debtor" at the start of sentences), proper punctuation, and grammatically correct sentence structure.
6. GENDER-NEUTRAL LANGUAGE: Use "their" instead of "his" or "her" (e.g., "their claim" not "his claim").

EXAMPLE:
User input: "The claim amount is wrong - they said $5,000 but I only owe $3,200 because I already made two payments of $900 each before filing"
Good output: "The claim amount is incorrect, as the claimant asserts $5,000 when the Debtor owes only $3,200, having already made two payments of $900 each prior to filing the bankruptcy petition."
Bad output: "The claim amount exceeds the actual debt owed due to pre-petition payments." (loses specific amounts and details about two payments)

IMPORTANT: Make sure every sentence starts with a capital letter, especially "The Debtor" (not "the Debtor") at the beginning of sentences.

Transform the following basis for objection into professional legal language:

User Input: "{user_input}"

Return ONLY the enhanced text with no explanations.""".format(user_input=user_input.strip())

        response = model.invoke([
            SystemMessage(content=system_msg),
            HumanMessage(content=prompt),
        ])

        enhanced_text = (response.content or "").strip()

        if enhanced_text:
            enhanced_text = _clean_fragment(enhanced_text, strip_trailing_punct=False)
            enhanced_text = _force_third_person(enhanced_text)
            enhanced_text = _normalize_defined_term_debtor(enhanced_text)
            # Ensure proper capitalization at the start of each sentence
            enhanced_text = _capitalize_sentences(enhanced_text)
            return enhanced_text.strip()

        return user_input if user_input else ""
        
    except Exception as e:
        print(f"WARNING: Failed to enhance basis for objection: {e}. Using original input.")
        return user_input if user_input else ""

# -------------------- context builder --------------------
# Template placeholders expected (from Word template):
#   Date, DebtorName, CaseNumb, Slot, ClaimantName, ClaimAmount, Basis

def _as_text(val) -> str:
    if val is None:
        return ""
    if isinstance(val, (list, tuple)):
        # Join lists into a readable sentence.
        return " ".join(str(x).strip() for x in val if str(x).strip())
    return str(val)


def build_context(ai: dict) -> dict:
    # Extract data from the Claim payload structure
    date_raw = ai.get("Date") or ""
    debtor_name = ai.get("DebtorName") or ""
    case_number = ai.get("CaseNumber") or ""
    slot = ai.get("Slot") or ""
    claimant_name = ai.get("ClaimantName") or ""
    claim_amount = ai.get("ClaimAmount") or ""
    raw_basis = ai.get("Basis") or ""

    # Parse date if it's a string
    date_parsed = parse_date(date_raw) if date_raw else None
    formatted_date = fmt_long(date_parsed) if date_parsed else date_raw

    # Enhance Basis for Objection with AI
    basis = (
        enhance_basis_for_objection(raw_basis) 
        if raw_basis and raw_basis.strip() and raw_basis.upper() != "N/A"
        else raw_basis
    )

    import re as _re
    _parts = [p.strip() for p in _re.split(r',\s*(?:and\s+)?|\s+and\s+', debtor_name) if p.strip()]
    header_debtor_name = "\n".join(_parts) if _parts else debtor_name

    return {
        "HeaderDebtorName": header_debtor_name,
        "Date": formatted_date,
        "DebtorName": debtor_name,
        "CaseNumb": case_number,
        "Slot": slot,
        "ClaimantName": claimant_name,
        "ClaimAmount": claim_amount,
        "Basis": basis,
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
    """Resolve the correct template. For Claim, we use a single template file."""
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
        "Date":         "April 6, 2026",
        "DebtorName":   "Laura Marie Cavazos and Moises Rafael Cavazos",
        "CaseNumber":   "25-21814-PDR",
        "Slot":         "5",
        "ClaimantName": "ABC Bank, N.A.",
        "ClaimAmount":  "$15,000.00",
        "Basis":        "The claim is based on an unsecured personal loan for which no supporting documentation was attached.",
    }

    print("Testing motion to object to claim functionality...")

    docx_path, pdf_path = generate_both_formats_from_payload(test_payload)
    print(f"DOCX generated: {docx_path}")
    print(f"PDF generated: {pdf_path}")

