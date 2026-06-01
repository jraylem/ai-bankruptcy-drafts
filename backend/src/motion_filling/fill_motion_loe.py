from __future__ import annotations
from pathlib import Path
from .generator_common import generate_document
from zipfile import ZipFile
import json, re
from datetime import date
from dateutil.parser import parse
from docxtpl import DocxTemplate
import anthropic
from ..config import settings
from ..ai_models import CLAUDE_MODEL_STANDARD

# -------------------- paths --------------------
BASE_DIR = Path(__file__).parent.resolve()
DATAFILE = BASE_DIR / "data" / "payload.loe.json"
OUT_DIR = BASE_DIR / "out"

# Use the standard template file inside templates folder
TEMPLATE_CANDIDATES = [
    BASE_DIR.parent / "templates" / "motion_to_loe.docx",
]

OUTPUT_BASENAME = "Motion_to_LOE_FILLED"

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
    raise SystemExit("Template not found. Place 'motion_to_loe.docx' under templates/ .")


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

# -------------------- AI enhancement for Explanation --------------------

def _capitalize_sentences(text: str) -> str:
    """Ensure proper capitalization at the start of each sentence."""
    if not text:
        return text
    
    # Split by sentence-ending punctuation followed by space
    # This regex looks for period, exclamation, or question mark followed by space(s)
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

def enhance_loe_explanation(user_input: str) -> str:
    """
    Enhance user-provided explanation for Letter of Explanation with professional legal language.
    
    Args:
        user_input: Raw user input for the explanation
        
    Returns:
        Enhanced legal text suitable for a formal letter to the trustee, or original input if enhancement fails
    """
    if not user_input or not user_input.strip():
        return ""
    
    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        prompt = """You are a legal writing assistant. Transform the user's input into professional legal language for a Letter of Explanation to the bankruptcy trustee.

CRITICAL RULES:
1. PRESERVE ALL FACTS: Keep every detail, reason, and circumstance the user mentioned - do not omit anything. Preserve the user's original words as much as possible.
2. IMPROVE PRESENTATION: Convert to third person ("the Debtor"), improve grammar, and use a neutral, factual tone.
3. DO NOT ADD NEW INFORMATION: Only rephrase what the user said - do not introduce new facts, dates, amounts, or circumstances.
4. PARAGRAPH FORMAT: Write 1-2 paragraphs maximum. Only exceed 2 paragraphs if the user's input contains multiple distinct topics that cannot be logically combined.
5. PROPER GRAMMAR & PUNCTUATION: Ensure correct capitalization (especially "The Debtor" at the start of sentences), proper punctuation, and grammatically correct sentence structure.
6. GENDER-NEUTRAL LANGUAGE: Use "their" instead of "his" or "her" (e.g., "their income" not "his income").
7. BE DIRECT: No emotional appeals, no sympathy language, no filler sentences. State facts only. Keep output compact.

EXAMPLE:
User input: "I missed my plan payment in March because I had unexpected car repairs that cost $1,200 and my paycheck was delayed by two weeks due to company payroll issues"
Good output: "The Debtor missed the March plan payment due to unexpected automobile repairs totaling $1,200 and a two-week delay in receiving wages caused by the employer's payroll processing issues."
Bad output: "The Debtor experienced financial difficulties in March resulting in a missed payment." (loses specific details about car repairs, the $1,200 amount, and the two-week payroll delay)

IMPORTANT: Make sure every sentence starts with a capital letter, especially "The Debtor" (not "the Debtor") at the beginning of sentences.

Transform the following explanation into professional legal language for a letter to the trustee:

User Input: "{user_input}"

Return ONLY the enhanced text with no explanations.""".format(user_input=user_input.strip())

        response = client.messages.create(
            model=CLAUDE_MODEL_STANDARD,
            max_tokens=400,
            system="You are a legal writing assistant specializing in bankruptcy motions. Your role is to improve presentation while preserving all user-provided facts. Be direct and factual — no emotional appeals or filler. Always use proper grammar, punctuation, and capitalization.",
            messages=[
                {"role": "user", "content": prompt}
            ],
        )

        enhanced_text = response.content[0].text.strip()

        if enhanced_text:
            enhanced_text = _clean_fragment(enhanced_text, strip_trailing_punct=False)
            enhanced_text = _force_third_person(enhanced_text)
            enhanced_text = _normalize_defined_term_debtor(enhanced_text)
            # Ensure proper capitalization at the start of each sentence
            enhanced_text = _capitalize_sentences(enhanced_text)
            return enhanced_text.strip()

        return user_input if user_input else ""
        
    except Exception as e:
        print(f"WARNING: Failed to enhance LOE explanation: {e}. Using original input.")
        return user_input if user_input else ""


def enhance_loe_explanation_with_documents(
    user_input: str,
    supporting_docs_content: list[dict]
) -> str:
    """
    Enhance LOE explanation using Claude with supporting document context.
    Uses Claude Vision API output to incorporate specific evidence from documents.

    Args:
        user_input: Raw user input for the explanation
        supporting_docs_content: List of dicts with 'type', 'filename', 'content' keys

    Returns:
        Enhanced legal text with references to supporting documents
    """
    if not user_input or not user_input.strip():
        return ""

    if not supporting_docs_content:
        return enhance_loe_explanation(user_input)

    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        # Build document context string
        docs_context = "\n\n".join([
            f"=== Document: {doc.get('filename', 'Unknown')} ({doc.get('type', 'unknown')}) ===\n{doc.get('content', '')}"
            for doc in supporting_docs_content
        ])

        prompt = f"""You are a legal writing assistant for bankruptcy Letter of Explanation.

SUPPORTING DOCUMENTS PROVIDED BY USER:
{docs_context}

CRITICAL INSTRUCTIONS:
1. Review the supporting documents to corroborate the user's explanation
2. Use and refer to EXACT details from the supporting documents - be specific
3. For bank statements: point directly to transaction dates and amounts (e.g., "as shown in the March 15, 2024 transaction of $1,234.56")
4. For receipts/invoices: cite specific line items, dates, totals
5. PRESERVE all user-provided facts - do not omit anything
6. Enhance grammar and punctuation
7. Use third person ("the Debtor", "their") - never first person
8. Write 1-2 paragraphs maximum. Only exceed 2 paragraphs if the input contains multiple distinct topics that cannot be logically combined.
9. Ensure every sentence starts with a capital letter, especially "The Debtor"
10. Be direct and compact. No emotional appeals, no sympathy language, no filler sentences. State facts only.

USER'S EXPLANATION:
{user_input}

Transform into professional, neutral legal language incorporating specific evidence from the documents.
Return ONLY the enhanced text with no explanations."""

        response = client.messages.create(
            model=CLAUDE_MODEL_STANDARD,
            max_tokens=800,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
        )

        enhanced_text = response.content[0].text.strip()

        if enhanced_text:
            enhanced_text = _clean_fragment(enhanced_text, strip_trailing_punct=False)
            enhanced_text = _force_third_person(enhanced_text)
            enhanced_text = _normalize_defined_term_debtor(enhanced_text)
            enhanced_text = _capitalize_sentences(enhanced_text)
            return enhanced_text.strip()

        return enhance_loe_explanation(user_input)

    except Exception as e:
        print(f"WARNING: Failed to enhance LOE with documents: {e}. Falling back to standard enhancement.")
        return enhance_loe_explanation(user_input)


# -------------------- context builder --------------------
# Template placeholders expected (from Word template):
#   Date, TrusteeName, ChapterNumb, DebtorName, CaseNumb, Explanation, AttorneyName

def _as_text(val) -> str:
    if val is None:
        return ""
    if isinstance(val, (list, tuple)):
        # Join lists into a readable sentence.
        return " ".join(str(x).strip() for x in val if str(x).strip())
    return str(val)


def build_context(ai: dict) -> dict:
    # Extract data from the LOE payload structure
    date_raw = ai.get("Date") or ""
    trustee_name = (ai.get("TrusteeName") or "").strip().title()
    chapter_number = str(ai.get("ChapterNumb") or "")
    debtor_name = ai.get("DebtorName") or ""
    case_number = ai.get("CaseNumb") or ""
    raw_explanation = ai.get("Explanation") or ""
    attorney_name = ai.get("AttorneyName") or ""

    # Check for supporting documents (passed via special key in payload)
    supporting_docs = ai.get("_supporting_docs")

    # Parse date if it's a string
    date_parsed = parse_date(date_raw) if date_raw else None
    formatted_date = fmt_long(date_parsed) if date_parsed else date_raw

    # Enhance Explanation with AI (with or without supporting documents)
    if raw_explanation and raw_explanation.strip() and raw_explanation.upper() != "N/A":
        if supporting_docs:
            explanation = enhance_loe_explanation_with_documents(raw_explanation, supporting_docs)
        else:
            explanation = enhance_loe_explanation(raw_explanation)
    else:
        explanation = raw_explanation

    return {
        "Date": formatted_date,
        "TrusteeName": trustee_name,
        "ChapterNumb": chapter_number,  # Changed from ChapterNumber to match template
        "DebtorName": debtor_name,
        "CaseNumb": case_number,  # Changed from CaseNumber to match template
        "Explanation": explanation,
        "AttorneyName": attorney_name,
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
    """Resolve the correct template. For LOE, we use a single template file."""
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
    main()

    test_payload = {
        "Date":         "April 6, 2026",
        "TrusteeName":  "Robin R Weiner",
        "ChapterNumb":  "13",
        "DebtorName":   "Vincent S Dimino",
        "CaseNumb":     "25-21814-PDR",
        "Explanation":  "The Debtor experienced a temporary reduction in income due to a period of medical leave, which prevented them from maintaining regular plan payments. The Debtor has since returned to full employment and is prepared to resume plan obligations.",
        "AttorneyName": "John R. Doe, Esq.",
    }

    print("Testing letter of explanation functionality...")

    docx_path, pdf_path = generate_both_formats_from_payload(test_payload)
    print(f"DOCX generated: {docx_path}")
    print(f"PDF generated: {pdf_path}")