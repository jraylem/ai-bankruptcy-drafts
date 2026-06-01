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
from ..ai_models import CLAUDE_MODEL_STANDARD, TEMPERATURE_ENHANCE

# -------------------- paths --------------------
BASE_DIR = Path(__file__).parent.resolve()
DATAFILE = BASE_DIR / "data" / "payload.modify_plan.json"  # <- change if you prefer a different path/name
OUT_DIR  = BASE_DIR / "out"

# Template mapping based on modification_type
# Regular templates (first modification after original confirmation)
TEMPLATES = {
    "delinquent": BASE_DIR.parent / "templates" / "motion_to_modify_plan_regular.docx",
    "creditor_alteration": BASE_DIR.parent / "templates" / "motion_to_modify_plan_noD.docx",
    "both": BASE_DIR.parent / "templates" / "motion_to_modify_plan_hybrid.docx",
}

# Granting templates (subsequent modification after previous modify was granted)
TEMPLATES_GRANTING = {
    "delinquent": BASE_DIR.parent / "templates" / "motion_to_modify_plan_regular_granting.docx",
    "creditor_alteration": BASE_DIR.parent / "templates" / "motion_to_modify_plan_noD_granting.docx",
    "both": BASE_DIR.parent / "templates" / "motion_to_modify_plan_hybrid_granting.docx",
}

# Fallback for backwards compatibility
TEMPLATE_CANDIDATES = [
    BASE_DIR.parent / "templates" / "motion_to_modify_plan_regular.docx",
    BASE_DIR.parent / "templates" / "motion_to_modify_plan.docx",
]

OUTPUT_BASENAME = "Motion_to_Modify_Plan_FILLED"

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
    raise SystemExit("Template not found. Place 'motion_to_modify_plan.docx' under templates/ .")


def warn_unresolved_placeholders(docx_path: Path):
    with ZipFile(docx_path, "r") as z:
        xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
    leftovers = re.findall(r"{{[^}]+}}", xml)
    if leftovers:
        print("\nWARNING: Unresolved placeholders:")
        for tok in leftovers:
            print("  -", tok)


# -------------------- PDF conversion (same style as extend) --------------------
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
    # Basic pronoun replacements
    s = re.sub(r"\b[Ii]\s+am\b", "The Debtor is", s)
    s = re.sub(r"\b[Ii]\s+was\b", "The Debtor was", s)
    s = re.sub(r"\b[Ii]\s+have\b", "The Debtor has", s)
    s = re.sub(r"\b[Ii]\b", "The Debtor", s)
    s = re.sub(r"\bmy\b", "The Debtor's", s, flags=re.IGNORECASE)
    s = re.sub(r"\bme\b", "The Debtor", s, flags=re.IGNORECASE)
    s = re.sub(r"\bmine\b", "The Debtor's", s, flags=re.IGNORECASE)
    return _normalize_defined_term_debtor(s)

def _build_complete_sentence(prefix: str, fragment: str) -> str:
    """Build a complete sentence from prefix + fragment, ensuring capitalization and no double periods."""
    frag = (fragment or "").strip()
    # Remove any periods from fragment to avoid ".." 
    frag = re.sub(r"\s*\.+\s*", " ", frag)
    frag = re.sub(r"[\s\.,;:]+$", "", frag)
    frag = frag.lstrip(", ")
    frag = re.sub(r"\s+", " ", frag)
    frag = _normalize_defined_term_debtor(frag)
    
    # Build complete sentence
    sentence = f"{prefix} {frag}".strip()
    sentence = _normalize_defined_term_debtor(sentence)
    
    # Capitalize first alphabetic character
    m = re.search(r"[A-Za-z]", sentence)
    if m:
        idx = m.start()
        sentence = sentence[:idx] + sentence[idx].upper() + sentence[idx+1:]
    
    # Remove trailing punctuation and add exactly one period
    sentence = re.sub(r"[\s\.,;:]+$", "", sentence)
    return sentence + "."

def enhance_delinquent_reason(user_input: str) -> str:
    """
    Enhance user-provided delinquent reason using GPT to complete the sentence
    "The Debtor had" with professional legal language.
    
    Args:
        user_input: Raw user input for delinquent reason
        
    Returns:
        Enhanced legal text, or original input if enhancement fails
    """
    if not user_input or not user_input.strip():
        return ""
    
    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        # Completion-style instruction: return only the fragment to follow the prefix
        prompt = """You are a legal writing assistant. Transform the user's input into professional legal language for a bankruptcy motion.

CRITICAL RULES:
1. PRESERVE ALL FACTS: Keep every detail, reason, and circumstance the user mentioned - do not omit anything. It is also important that as much as possible the user's input words are preserved in the output.
2. IMPROVE PRESENTATION: Convert to third person, improve grammar, and use formal legal tone.
3. DO NOT ADD NEW INFORMATION: Only rephrase what the user said - do not introduce new facts, dates, amounts, or circumstances.
4. USE "THEY" TO AVOID REPETITION: The prefix already includes "The Debtor had", so use "they", "their", "them" instead of repeating "the Debtor" (e.g., "they were unable" not "the Debtor was unable").
5. GENDER-NEUTRAL LANGUAGE: Use "their" instead of "his" or "her" (e.g., "their obligations" not "his obligations").

EXAMPLE:
User input: "temporary loss of income due to medical leave"
Good output: "a temporary loss of income due to medical leave"
Bad output: "unexpected financial hardship from approved medical leave" (adds "unexpected" and "approved", changes "loss of income")

Complete this sentence: "The Debtor had"

User Input: "{user_input}"

Return ONLY the completion fragment (no prefix, no period at end).""".format(user_input=user_input.strip())

        response = client.messages.create(
            model=CLAUDE_MODEL_STANDARD,
            max_tokens=300,
            temperature=TEMPERATURE_ENHANCE,
            system="You are a legal writing assistant specializing in bankruptcy motions. Your role is to improve presentation while preserving all user-provided facts.",
            messages=[
                {"role": "user", "content": prompt}
            ],
        )

        enhanced_text = response.content[0].text.strip()

        # Build complete sentence with prefix
        if enhanced_text:
            completion = _clean_fragment(enhanced_text, strip_trailing_punct=True)
            completion = _force_third_person(completion)
            # Replace ANY occurrence of "the Debtor" with "they" to avoid repetition after "The Debtor had" prefix
            # This catches all cases: "the Debtor was", "the Debtor lost", "the Debtor experienced", etc.
            completion = re.sub(r"\bthe\s+Debtor\b", "they", completion, flags=re.IGNORECASE)
            # Also replace "The Debtor's" with "their"
            completion = re.sub(r"\bthe\s+Debtor's\b", "their", completion, flags=re.IGNORECASE)
            enhanced_text = _build_complete_sentence("The Debtor had", completion)

        return enhanced_text if enhanced_text else user_input
        
    except Exception as e:
        print(f"WARNING: Failed to enhance delinquent reason: {e}. Using original input.")
        return user_input

def generate_delinquent_reason_suggestions(motion_payload: dict, session_id: str) -> list[str]:
    """
    Generate AI-powered suggestion chips for the delinquent reason field.

    Uses session context (petition, emails) to generate 3 case-specific,
    realistic delinquent reason scenarios the user can select.

    Args:
        motion_payload: Extracted motion payload with debtor info
        session_id: Session identifier for context retrieval

    Returns:
        List of 3 suggestion strings, or empty list if generation fails
    """
    try:
        from ..chatbot.vectorestore import search_vectorstore

        debtor_name = motion_payload.get("debtor_name", "")

        context_chunks = []

        # Search petition vectorstore for employment/financial context
        try:
            petition_docs = search_vectorstore(
                query="employment income job salary expenses financial circumstances",
                collection_name=f"bankruptcy_knowledge_{session_id}",
                k=3
            )
            if petition_docs:
                context_chunks.extend([doc.page_content[:500] for doc in petition_docs])
        except Exception as e:
            print(f"Warning: Could not search petition for delinquent reason context: {e}")

        # Search gmail vectorstore for delinquency context
        try:
            gmail_docs = search_vectorstore(
                query="delinquent payment missed trustee notice financial hardship",
                collection_name=f"gmail_{session_id}",
                k=2
            )
            if gmail_docs:
                context_chunks.extend([doc.page_content[:500] for doc in gmail_docs])
        except Exception as e:
            print(f"Warning: Could not search gmail for delinquent reason context: {e}")

        context_text = "\n---\n".join(context_chunks) if context_chunks else ""

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        prompt = f"""You are a legal assistant generating suggestion chips for a Motion to Modify bankruptcy document.

The debtor became delinquent on their Chapter 13 plan payments. A law firm attorney needs to select a reason.

Debtor name: {debtor_name}

{f"Context from case documents:\n{context_text}" if context_text else "No additional context available."}

CRITICAL: Base your suggestions on the context provided above. If context mentions employment type, family situation, or financial circumstances, USE that information. Do NOT fabricate specific details that aren't supported by the data.

Generate exactly 3 realistic reasons why this debtor might fall behind on plan payments.
Each suggestion should:
- Be a COMPLETE SENTENCE starting with "The Debtor"
- Use gender-neutral language ("their", "them" instead of "his/her")
- Be 10-25 words
- Be REALISTIC and PLAUSIBLE based on available context
- If no specific context, use common generic scenarios (job loss, medical expenses, reduced hours)
- Do NOT invent specific family members, employers, or circumstances not in the data
- Sound professional and suitable for a legal motion

Examples of good suggestions:
- "The Debtor lost their job and is currently supporting the financial needs of their family"
- "The Debtor experienced unexpected medical expenses due to a health emergency"
- "The Debtor had a temporary reduction in work hours at their place of employment"

Return ONLY a JSON array of 3 strings, no explanation:
["sentence 1", "sentence 2", "sentence 3"]"""

        response = client.messages.create(
            model=CLAUDE_MODEL_STANDARD,
            max_tokens=300,
            temperature=0.7,
            system="You are a legal writing assistant. Return only the requested JSON array.",
            messages=[
                {"role": "user", "content": prompt}
            ],
        )

        raw_response = response.content[0].text.strip()

        # Parse JSON array
        suggestions = json.loads(raw_response)

        if isinstance(suggestions, list) and len(suggestions) >= 3:
            return [str(s).strip() for s in suggestions[:3]]

        return []

    except Exception as e:
        print(f"WARNING: Failed to generate delinquent reason suggestions: {e}")
        return []


# -------------------- context builder --------------------
# Template placeholders expected (from Word templates):
#
# Regular (delinquent): CaseNumber, ChapterNumber, ConfirmDate, CurrentDate,
#   DateDelinquent, DebtorName, DocketNumbConfirm, DocketNumbNotice, DocketNumbPlan, ReasonDelinquent
#
# noD (creditor_alteration): CaseNumber, ChapterNumber, ClaimSlot, ConfirmDate,
#   Creditors, DebtorName, DocketNumbConfirm, DocketNumbPlan, HasHave, s
#
# Hybrid (both): All fields from both Regular and noD

def _as_text(val) -> str:
    if val is None:
        return ""
    if isinstance(val, (list, tuple)):
        return " ".join(str(x).strip() for x in val if str(x).strip())
    return str(val)


def build_context(ai: dict) -> dict:
    # Header geography (use uppercase for court headers)
    district_raw = ai.get("court_district") or ""
    division_raw = ai.get("court_division") or ""

    # Case basics
    debtor_name    = ai.get("debtor_name") or ""
    case_number    = ai.get("case_no") or ""
    chapter_number = str(ai.get("chapter") or "")

    # Modification type
    modification_type = ai.get("modification_type", "delinquent")

    # Common dates & docket refs
    confirm_dt      = parse_date(ai.get("confirm_date"))
    docket_confirm = _as_text(ai.get("docket_confirm"))
    docket_plan    = _as_text(ai.get("docket_plan"))

    # Current date (optional in payload; default to today)
    current_raw = ai.get("current_date")
    current_dt = parse_date(current_raw) or date.today()

    # Split "A and B" or "A, B, and C" into one name per line
    import re as _re
    _parts = [p.strip() for p in _re.split(r',\s*(?:and\s+)?|\s+and\s+', debtor_name) if p.strip()]
    header_debtor_name = "\n".join(_parts) if _parts else debtor_name

    # Build base context (common to all templates)
    context = {
        "HeaderDebtorName": header_debtor_name,
        "CourtDistrict": district_raw.upper(),
        "CourtDivision": division_raw.upper(),
        "CaseNumber": case_number,
        "ChapterNumber": chapter_number,
        "DebtorName": debtor_name,
        "ConfirmDate": fmt_long(confirm_dt),
        "DocketNumbConfirm": docket_confirm,
        "DocketNumbPlan": docket_plan,
        "CurrentDate": fmt_long(current_raw),
    }

    # Add delinquent fields (for "delinquent" or "both")
    if modification_type in ("delinquent", "both"):
        date_delinquent = parse_date(ai.get("date_delinquent"))
        docket_notice  = _as_text(ai.get("docket_notice"))
        raw_delinquent_reason = _as_text(ai.get("delinquent_reason"))

        enhanced_delinquent_reason = (
            enhance_delinquent_reason(raw_delinquent_reason)
            if raw_delinquent_reason.strip()
            else ""
        )

        context.update({
            "DateDelinquent": fmt_long(date_delinquent),
            "DocketNumbNotice": docket_notice,
            "ReasonDelinquent": enhanced_delinquent_reason,
        })

    # Add creditor alteration fields (for "creditor_alteration" or "both")
    if modification_type in ("creditor_alteration", "both"):
        creditors = _as_text(ai.get("creditors"))
        claim_slot = _as_text(ai.get("claim_slot"))
        has_have = _as_text(ai.get("has_have")) or "has"
        s_plural = _as_text(ai.get("s_plural")) or ""

        context.update({
            "Creditors": creditors,
            "ClaimSlot": claim_slot,
            "HasHave": has_have,
            "s": s_plural,
        })

    return context


# -------------------- render --------------------
def render_docx(template_docx: Path, ctx: dict, name_slug: str) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_docx = OUT_DIR / f"{name_slug}.docx"
    doc = DocxTemplate(template_docx)
    doc.render(ctx)
    doc.save(out_docx)
    warn_unresolved_placeholders(out_docx)
    return out_docx


# -------------------- orchestration helpers (DOCX + PDF) --------------------
def resolve_template_from_payload(payload: dict) -> Path:
    """
    Resolve the correct template based on modification_type and use_granting_template flag.

    Template selection logic:
    - If use_granting_template=True and granting template exists → use granting template
    - Otherwise → use regular template for the modification_type
    """
    mod_type = payload.get("modification_type", "delinquent")
    use_granting = payload.get("use_granting_template", False)

    # Try granting template first if flag is set
    if use_granting:
        granting_template = TEMPLATES_GRANTING.get(mod_type)
        if granting_template and granting_template.exists():
            print(f"[TEMPLATE] Using GRANTING template: {granting_template.name}")
            return granting_template
        else:
            print(f"[TEMPLATE] Granting template not found for '{mod_type}', falling back to regular")

    # Use regular template
    template_path = TEMPLATES.get(mod_type)
    if template_path and template_path.exists():
        print(f"[TEMPLATE] Using REGULAR template: {template_path.name}")
        return template_path

    # Fallback to default template
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
    ai_data  = load_payload()
    ctx      = build_context(ai_data)
    out_docx = render_docx(template, ctx, OUTPUT_BASENAME)
    print("DOCX generated:", out_docx.resolve())


if __name__ == "__main__":
    test_payload = {
        "court_district":    "Southern District of Florida",
        "court_division":    "Fort Lauderdale",
        "debtor_name":       "Laura Marie Cavazos and Moises Rafael Cavazos",
        "case_no":           "25-21814-PDR",
        "chapter":           "13",
        "modification_type": "delinquent",
        "confirm_date":      "March 10, 2025",
        "docket_confirm":    "25",
        "docket_plan":       "18",
        "current_date":      "April 6, 2026",
        "date_delinquent":   "February 1, 2026",
        "docket_notice":     "32",
        "delinquent_reason": "The Debtor fell behind on plan payments due to a temporary loss of employment.",
    }

    print("Testing motion to modify functionality...")

    docx_path, pdf_path = generate_both_formats_from_payload(test_payload)
    print(f"DOCX generated: {docx_path}")
    print(f"PDF generated: {pdf_path}")