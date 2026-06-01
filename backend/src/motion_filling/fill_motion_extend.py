from pathlib import Path
from .generator_common import generate_document
from zipfile import ZipFile
import subprocess, shutil, re
from datetime import date, timedelta
from dateutil.parser import parse
from docxtpl import DocxTemplate
import anthropic
from ..config import settings
from ..ai_models import CLAUDE_MODEL_STANDARD

BASE_DIR = Path(__file__).parent.resolve()
OUT_DIR  = BASE_DIR / "out"

# Your template(s). .doc files will be auto-converted to .docx via Word COM if available.
# Backward-compatible default and explicit regular/expedite templates
TEMPLATE_CANDIDATES = [
    BASE_DIR.parent / "templates" / "motion_to_extend.docx",
]

TEMPLATE_MAP = {
    "regular": BASE_DIR.parent / "templates" / "motion_to_extend_regular.docx",
    "expedite": BASE_DIR.parent / "templates" / "motion_to_extend_expedite.docx",
}
OUTPUT_BASENAME = "motion_extend_filled"

# ---------- helpers ----------

def parse_date(dt_like) -> date | None:
    if not dt_like:
        return None
    try:
        return parse(str(dt_like)).date()
    except Exception:
        return None

def fmt_long(dt_like) -> str:
    if not dt_like:
        return ""
    try:
        d = dt_like if isinstance(dt_like, date) else parse(str(dt_like)).date()
        return f"{d.strftime('%B')} {d.day}, {d.year}"
    except Exception:
        return ""

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

def resolve_template_from_payload(payload: dict) -> Path:
    """Resolve the correct template based on payload fields.

    Prefers explicit templates:
      - payload["expedite"] == "regular" -> motion_to_extend_regular.docx
      - payload["expedite"] == "expedite" -> motion_to_extend_expedite.docx
      - payload["expedited"] similarly supported for FE variations
      - payload["extension_type"] also supported (from Taskiq flow)

    Falls back to legacy ensure_docx_template() if explicit file is missing.
    """
    try:
        choice_raw = (payload.get("extension_type")
                      or payload.get("expedite")
                      or payload.get("expedited")
                      or "").strip().lower()
        choice = "expedite" if choice_raw in ("expedite", "expedited") else "regular"
        template_path = TEMPLATE_MAP.get(choice)
        if template_path and template_path.exists():
            return template_path
        # If explicit choice file missing, try the other as a fallback
        fallback_choice = "regular" if choice == "expedite" else "expedite"
        fallback_path = TEMPLATE_MAP.get(fallback_choice)
        if fallback_path and fallback_path.exists():
            return fallback_path
    except Exception:
        pass
    # Final fallback: legacy behavior
    return ensure_docx_template()


def is_order_extend_expedite_from_motion_payload(payload: dict) -> bool:
    """Return True if motion payload indicates expedited (use order extend expedite template)."""
    choice_raw = (payload.get("extension_type") or payload.get("expedite") or payload.get("expedited") or "").strip().lower()
    return choice_raw in ("expedite", "expedited")


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

# ---------- AI enhancement ----------

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

_FACT_TOKEN_RE = re.compile(r"\$?\d[\d,]*(?:\.\d+)?")


def _heal_sentence(sentence: str) -> str:
    """Final LLM grammar-only polish. Rejects output that mutates any numeric/dollar token."""
    if not sentence or not sentence.strip():
        return sentence

    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=CLAUDE_MODEL_STANDARD,
            max_tokens=600,
            temperature=0.0,
            system="You are a legal writing editor. Fix grammar, subject-verb agreement, duplicate subjects, redundant phrasing, and missing sentence-ending punctuation. Prefer third-person plural pronouns ('they', 'them', 'their') over repeating 'the Debtor' after the first reference in a sentence — legal prose should read naturally, not mechanically. Never use contractions (rewrite 'they're' as 'they are', 'they've' as 'they have', 'they'll' as 'they will', 'they'd' as 'they would'). Never use 'he', 'she', 'his', or 'her'. Preserve every fact, number, date, dollar amount, name, and legal term exactly as written. Do not add, remove, or change facts. Return only the corrected sentence with no commentary.",
            messages=[{"role": "user", "content": sentence}],
        )
        healed = response.content[0].text.strip().strip('"').strip("'")
        if not healed:
            return sentence

        original_tokens = sorted(_FACT_TOKEN_RE.findall(sentence))
        healed_tokens = sorted(_FACT_TOKEN_RE.findall(healed))
        if original_tokens != healed_tokens:
            print(f"WARNING: _heal_sentence discarded output — numeric token mismatch. original={original_tokens} healed={healed_tokens}")
            return sentence

        healed = re.sub(r"[\s\.,;:]+$", "", healed)
        return healed
    except Exception as e:
        print(f"WARNING: _heal_sentence failed: {e}. Using unhealed sentence.")
        return sentence


def _build_complete_sentence(prefix: str, fragment: str) -> str:
    """Build a complete sentence from prefix + fragment. Template owns the final period."""
    frag = (fragment or "").strip()
    frag = re.sub(r"[\s\.,;:]+$", "", frag)
    frag = frag.lstrip(", ")
    frag = re.sub(r"\s+", " ", frag)
    frag = _normalize_defined_term_debtor(frag)

    sentence = f"{prefix} {frag}".strip()
    sentence = _normalize_defined_term_debtor(sentence)

    m = re.search(r"[A-Za-z]", sentence)
    if m:
        idx = m.start()
        sentence = sentence[:idx] + sentence[idx].upper() + sentence[idx+1:]

    sentence = re.sub(r"[\s\.,;:]+$", "", sentence)
    return _heal_sentence(sentence)

# Keep in sync with the template paragraphs in:
#   src/templates/motion_to_extend_regular.docx
#   src/templates/motion_to_extend_expedite.docx
# If those paragraphs are edited, update these constants so the LLM sees the
# actual surrounding text the fragment will slot into.
_TEMPLATE_PARAGRAPH_3 = (
    "During the one-year period prior to the Petition Date, the Debtor had one "
    "other bankruptcy case before the Bankruptcy Court, Case No.: "
    "{{ DismissedCaseNumber }} which was dismissed, on {{ DismissalDate }}, "
    "{{ TrusteesReason }}. (Dkt. NO.{{ DocketEntryNo }}). "
    "<<DISMISSAL_REASON_SENTENCE>>."
)
_TEMPLATE_PARAGRAPH_4 = (
    "<<CHANGE_IN_CIRCUMSTANCES_SENTENCE>>. As a result, the Debtor now has "
    "sufficient grounds to make the planned payments and fulfill all "
    "obligations under 11 U.S.C. §1325(a)(6)."
)


def _finalize_slot_sentence(text: str) -> str:
    """Normalize a sentence produced for a template placeholder: strip quotes/trailing
    punct, collapse whitespace, normalize Debtor casing, capitalize first letter."""
    if not text:
        return ""
    s = text.strip().strip('"').strip("'").strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[\s\.,;:]+$", "", s)
    s = _normalize_defined_term_debtor(s)
    if s and s[0].isalpha():
        s = s[0].upper() + s[1:]
    return s


def enhance_dismissal_reason(user_input: str) -> str:
    """
    Produce the full sentence that will replace `{{ DismissalReason }}` at the end of
    paragraph 3 of the Motion to Extend Automatic Stay. The LLM is shown the actual
    surrounding template text so it can tailor the sentence to flow with what comes
    before and after.

    The template supplies the final period — this function must NOT return one.
    """
    if not user_input or not user_input.strip():
        return ""

    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        prompt = f"""You are drafting a sentence that will be inserted into a Motion to Extend Automatic Stay (Chapter 13 bankruptcy).

Paragraph 3 of the motion reads as follows (your sentence replaces <<DISMISSAL_REASON_SENTENCE>>):

\"\"\"
{_TEMPLATE_PARAGRAPH_3}
\"\"\"

Paragraph 4 (for coherence with what follows):

\"\"\"
{_TEMPLATE_PARAGRAPH_4}
\"\"\"

The user provided this raw description of why the prior case was dismissed:
"{user_input.strip()}"

Your task — produce ONE complete sentence that slots in at <<DISMISSAL_REASON_SENTENCE>>:

REQUIREMENTS:
1. Begin with: "The Debtor's previous case was dismissed because"
2. Subject handling — introduce the debtor as "the Debtor" at the FIRST reference in your sentence, then use third-person plural pronouns ("they", "them", "their") for subsequent references in the same sentence. The goal is natural legal prose, not mechanical repetition of "the Debtor" three or four times. Do NOT use "he", "she", "his", or "her". Do NOT use contractions ("they're", "they've", "they'll", "they'd") — always spell out as "they are", "they have", "they will", "they would". Style example:
   • STIFF (avoid): "The Debtor's previous case was dismissed because the Debtor missed payments after the Debtor lost the Debtor's job."
   • NATURAL (target): "The Debtor's previous case was dismissed because the Debtor missed payments after they lost their job."
3. Third-person, formal legal tone.
4. Preserve EVERY fact the user mentioned (dates, amounts, reasons, circumstances). Do not add new facts.
5. Do NOT duplicate information already stated in the preceding sentence — the case number, dismissal date, trustee's reason, and docket number are already given via the placeholders {{{{ DismissedCaseNumber }}}}, {{{{ DismissalDate }}}}, {{{{ TrusteesReason }}}}, {{{{ DocketEntryNo }}}}. Do not restate them.
6. The sentence should flow naturally into paragraph 4, which introduces the change in circumstances.
7. Do NOT end with a period — the template supplies it.

Return ONLY the sentence. No quotes, no commentary."""

        response = client.messages.create(
            model=CLAUDE_MODEL_STANDARD,
            max_tokens=600,
            temperature=0.3,
            system="You are a legal writing assistant specializing in bankruptcy motions. Produce sentences tailored to slot into specific template positions while preserving all user-provided facts.",
            messages=[{"role": "user", "content": prompt}],
        )

        enhanced_text = response.content[0].text.strip()
        if enhanced_text:
            enhanced_text = _force_third_person(enhanced_text)
            enhanced_text = _finalize_slot_sentence(enhanced_text)
            enhanced_text = _heal_sentence(enhanced_text)

        return enhanced_text if enhanced_text else user_input

    except Exception as e:
        print(f"WARNING: Failed to enhance dismissal reason: {e}. Using original input.")
        return user_input


def enhance_change_in_circumstances(user_input: str, dismissal_reason_context: str = "") -> str:
    """
    Produce the full sentence that will replace `{{ ChangeInCircum }}` at the start of
    paragraph 4 of the Motion to Extend Automatic Stay. The LLM is shown the actual
    surrounding template text so it can tailor the sentence to flow into "As a result…".

    The template supplies the final period — this function must NOT return one.
    """
    if not user_input or not user_input.strip():
        return ""

    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        coherence_section = ""
        if dismissal_reason_context and dismissal_reason_context.strip():
            coherence_section = (
                "\nCOHERENCE WITH PARAGRAPH 3 — the dismissal reason (raw user input) was:\n"
                f'"{dismissal_reason_context.strip()}"\n'
                "Your sentence must address how that specific issue has been resolved or improved, so paragraphs 3 and 4 read as a coherent cause → remedy narrative.\n"
            )

        prompt = f"""You are drafting a sentence that will be inserted into a Motion to Extend Automatic Stay (Chapter 13 bankruptcy).

Paragraph 4 of the motion reads as follows (your sentence replaces <<CHANGE_IN_CIRCUMSTANCES_SENTENCE>>):

\"\"\"
{_TEMPLATE_PARAGRAPH_4}
\"\"\"

Paragraph 3 (for context of what precedes your sentence) — the last sentence of paragraph 3 explains why the prior case was dismissed:

\"\"\"
{_TEMPLATE_PARAGRAPH_3}
\"\"\"
{coherence_section}
The user provided this raw description of the change in circumstances:
"{user_input.strip()}"

Your task — produce ONE complete sentence that slots in at <<CHANGE_IN_CIRCUMSTANCES_SENTENCE>>:

REQUIREMENTS:
1. Begin with the EXACT phrase: "The Debtor will now be able to afford their Chapter 13 plan due to a substantial change in circumstances, as the Debtor has"
2. The word immediately following "as the Debtor has" MUST be a past participle (e.g., "secured", "obtained", "received", "established", "recovered"). It MUST NOT be a present-tense verb ("is", "was", "earns", "is earning") and MUST NOT restart with "the Debtor" — the subject + auxiliary "has" are already supplied by the required opening phrase.
3. Subject handling — the required opening phrase already establishes "the Debtor" TWICE. For any subsequent references in the rest of your sentence, use third-person plural pronouns ("they", "them", "their") rather than repeating "the Debtor" again. The goal is natural legal prose. Do NOT use "he", "she", "his", or "her". Do NOT use contractions ("they're", "they've", "they'll", "they'd") — always spell out as "they are", "they have", "they will", "they would". Style example:
   • STIFF (avoid): "…as the Debtor has secured new employment, and the Debtor now earns $4,500 per month, up from the Debtor's prior $3,200."
   • NATURAL (target): "…as the Debtor has secured new employment, and they now earn $4,500 per month, up from their prior $3,200."
4. Third-person, formal legal tone.
5. Preserve EVERY fact the user mentioned (income amounts, expense changes, dates). Do not add new facts.
6. The sentence must flow into "As a result, the Debtor now has sufficient grounds…" — state the change as an accomplished fact.
7. Do NOT end with a period — the template supplies it.

Return ONLY the sentence. No quotes, no commentary."""

        response = client.messages.create(
            model=CLAUDE_MODEL_STANDARD,
            max_tokens=600,
            temperature=0.3,
            system="You are a legal writing assistant specializing in bankruptcy motions. Produce sentences tailored to slot into specific template positions while preserving all user-provided facts.",
            messages=[{"role": "user", "content": prompt}],
        )

        enhanced_text = response.content[0].text.strip()
        if enhanced_text:
            enhanced_text = _finalize_slot_sentence(enhanced_text)
            enhanced_text = _heal_sentence(enhanced_text)

        return enhanced_text if enhanced_text else user_input

    except Exception as e:
        print(f"WARNING: Failed to enhance change in circumstances: {e}. Using original input.")
        return user_input

# ---------- context build ----------

def _format_proper_case(text: str) -> str:
    """Convert text to proper case, keeping 'of' lowercase in phrases like 'District of'."""
    if not text:
        return text
    # Convert to title case first
    text = text.strip().title()
    # Lowercase common prepositions/articles in legal contexts
    text = re.sub(r'\bOf\b', 'of', text)
    text = re.sub(r'\bThe\b', 'the', text)
    return text

def _parse_district_division_from_court_type(ct: str) -> tuple[str, str]:
    """Best-effort parser for e.g. 'Southern District of Florida Fort Lauderdale Division'."""
    if not ct:
        return "", ""
    ct_u = ct.upper()
    # District like 'SOUTHERN DISTRICT OF FLORIDA'
    m_dist = re.search(r'([A-Z ]*DISTRICT OF [A-Z ]+)', ct_u)
    district = (m_dist.group(1).strip() if m_dist else "").strip()
    # Division like 'FORT LAUDERDALE' --> add ' DIVISION'
    m_div = re.search(r'([A-Z ]+?)\s+DIVISION', ct_u)
    division_core = (m_div.group(1).strip() if m_div else "")
    division = (division_core + " DIVISION").strip() if division_core else ""
    return district, division


def _default_na(value: str) -> str:
    """Return 'N/A' if value is empty/None, otherwise return the value."""
    if not value or not str(value).strip():
        return "N/A"
    return str(value).strip()

def build_context(ai: dict) -> dict:
    # District / Division: prefer explicit fields; else try to parse from 'court_type'; else defaults.
    district = (ai.get("court_district") or "").strip()
    division = (ai.get("court_division")  or "").strip()
    if not (district and division) and ai.get("court_type"):
        d2, v2 = _parse_district_division_from_court_type(str(ai["court_type"]))
        district = district or d2
        division = division or v2
    # Format district and division in proper case (not all caps)
    district = _format_proper_case(district or "Southern District of Florida")
    division = _format_proper_case(division or "Fort Lauderdale Division")
    court_type = f"{district} {division}"  # kept for any legacy {{ CourtType }} usage

    # Debtor name in title case
    debtor = (ai.get("debtor_name") or "").strip().title()

    # Dates
    motion_cal      = fmt_long(ai.get("motion_calendar_date"))
    petition_dt_obj = parse_date(ai.get("petition_date"))
    petition_str    = fmt_long(petition_dt_obj)
    petition_plus30 = fmt_long(petition_dt_obj + timedelta(days=30) if petition_dt_obj else "")
    dismissal_str   = fmt_long(ai.get("dismissal_date"))

    # Flexible sources
    docket_no = (
        ai.get("docket_entry_no")
        or ai.get("docket_entry_number")
        or ai.get("docket_no")
        or ai.get("docket")
        or ""
    )
    trustees_reason = (
        ai.get("trustees_reason")
        or ai.get("trustee_reason")
        or ai.get("trustee_s_reason")
        or ai.get("trustees_reason_text")
        or ""
    )

    # Enhance user-provided legal text with AI
    raw_dismissal_reason = ai.get("dismissal_reason") or ""
    enhanced_dismissal_reason = (
        enhance_dismissal_reason(raw_dismissal_reason) 
        if raw_dismissal_reason.strip() 
        else ""
    )
    
    raw_change_in_circum = ai.get("change_in_circum") or ai.get("change_in_circumstances") or ""
    enhanced_change_in_circum = (
        enhance_change_in_circumstances(raw_change_in_circum, dismissal_reason_context=raw_dismissal_reason)
        if raw_change_in_circum.strip()
        else ""
    )

    # Split "A and B" or "A, B, and C" into one name per line
    import re as _re
    debtor1 = (ai.get("debtor_name") or "").strip()
    _parts = [p.strip() for p in _re.split(r',\s*(?:and\s+)?|\s+and\s+', debtor1) if p.strip()]
    header_debtor_name = "\n".join(_parts) if _parts else debtor1

    ctx = {
        "HeaderDebtorName":     header_debtor_name,
        "CourtDistrict":        district,
        "CourtDivision":        division,
        "CourtType":            court_type,
        "MotionCalendarDate":   _default_na(motion_cal),
        "PetitionDate":         _default_na(petition_str),
        "PetitionDatePlus30":   _default_na(petition_plus30),
        "DebtorName":           _default_na(debtor),
        "DismissedCaseNumber":  _default_na(ai.get("dismissed_case_number") or ai.get("dismissed_case_no")),
        "DismissalDate":        _default_na(dismissal_str),
        "CaseNumber":           _default_na(ai.get("case_no") or ai.get("case_number")),
        "DismissalReason":      _default_na(enhanced_dismissal_reason),
        "ChangeInCircum":       _default_na(enhanced_change_in_circum),
        "ChapterNumber":        _default_na(ai.get("chapter") or ai.get("chapter_number")),
        "DocketEntryNo":        _default_na(docket_no),
        "TrusteesReason":       _default_na(trustees_reason),
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

def generate_both_formats(template_docx: Path, ctx: dict, name_slug: str) -> tuple[Path, Path]:
    """
    Generate both DOCX and PDF files from the template.
    
    Returns:
        tuple[Path, Path]: (docx_path, pdf_path)
    """
    # Generate DOCX
    docx_path = render_docx(template_docx, ctx, name_slug)
    
    # Generate PDF
    pdf_path = convert_to_pdf(docx_path)
    
    return docx_path, pdf_path


def generate_document_from_payload(payload_data: dict, output_basename: str = None, output_type: str = "pdf") -> Path:
    default_basename = globals().get("OUTPUT_BASENAME", "motion_extend_filled")
    return generate_document(
        payload_data=payload_data,
        output_basename=output_basename,
        output_type=output_type,
        default_basename=default_basename,
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
    name_slug = output_basename or globals().get("OUTPUT_BASENAME", "motion_extend_filled")
    out_docx = render_docx(template, ctx, name_slug)
    out_pdf = convert_to_pdf(out_docx)
    return out_docx, out_pdf


def generate_extend_suggestions(motion_payload: dict, session_id: str) -> dict[str, list[str]]:
    """
    Generate AI-powered suggestion chips for extend motion fields.

    Uses the GmailMotionExtendAgent's generate_recommendations method which follows the ticket flow:
    1. Get old petition context (check DB first, then Gmail)
    2. Get current petition context (Schedule I/J)
    3. Get Chapter 13 Plan context from Gmail
    4. Generate ChangeInCircum FIRST (using both petitions + plan)
    5. Generate DismissalReason SECOND (using TrusteeReason + ChangeInCircum)

    Args:
        motion_payload: Extracted motion payload with case info
        session_id: Session identifier for context retrieval

    Returns:
        Dict with keys:
        - dismissal_reason: List of 3 suggestion strings
        - change_in_circum: List of 3 suggestion strings
    """
    from ..gmail.agents.extend import GmailMotionExtendAgent

    result = {
        "dismissal_reason": [],
        "change_in_circum": [],
    }

    try:
        trustees_reason = motion_payload.get("trustees_reason", "N/A")
        case_no = motion_payload.get("case_no", "")
        dismissed_case_number = motion_payload.get("dismissed_case_number", "")

        print(f"\n{'='*70}")
        print(f"GENERATING EXTEND SUGGESTIONS (using GmailMotionExtendAgent)")
        print(f"{'='*70}")
        print(f"Session ID: {session_id}")
        print(f"Case Number: {case_no}")
        print(f"Dismissed Case Number: {dismissed_case_number}")
        print(f"Trustees Reason: {trustees_reason}")

        # Initialize the agent
        agent = GmailMotionExtendAgent(session_id=session_id)

        # Get context using agent methods
        current_petition_context = agent._get_current_petition_schedule_context()
        chapter_13_plan_context, _ = agent._get_chapter_13_plan_context(case_no)

        # Generate recommendations using the ticket-compliant flow
        recommendations = agent.generate_recommendations(
            trustees_reason=trustees_reason,
            current_petition_context=current_petition_context,
            chapter_13_plan_context=chapter_13_plan_context,
            dismissed_case_number=dismissed_case_number,
        )

        # Extract chips from recommendations
        if recommendations.dismissal_reason_chips:
            result["dismissal_reason"] = recommendations.dismissal_reason_chips

        if recommendations.change_in_circum_chips:
            result["change_in_circum"] = recommendations.change_in_circum_chips

        # Log context warnings
        if recommendations.context_warnings:
            print(f"\n⚠ Context warnings:")
            for warning in recommendations.context_warnings:
                print(f"  • {warning}")

        # Final summary with full chip content
        print(f"\n{'='*70}")
        print(f"FINAL SUGGESTION CHIPS SUMMARY")
        print(f"{'='*70}")
        print(f"\n[DISMISSAL REASON CHIPS] (derived from TrusteeReason + ChangeInCircum):")
        for i, chip in enumerate(result.get("dismissal_reason", [])):
            print(f"  [{i+1}] {chip}")
        print(f"\n[CHANGE IN CIRCUM CHIPS] (derived from current petition + old petition + Chapter 13 plan):")
        for i, chip in enumerate(result.get("change_in_circum", [])):
            print(f"  [{i+1}] {chip}")
        print(f"\n{'='*70}")

    except Exception as e:
        print(f"WARNING: Failed to generate extend suggestions using agent: {e}")
        import traceback
        traceback.print_exc()

    return result


# -------------------- main --------------------
if __name__ == "__main__":
    test_payload = {
        "court_district":        "Southern District of Florida",
        "court_division":        "Fort Lauderdale",
        "debtor_name":           "Laura Marie Cavazos and Moises Rafael Cavazos",
        "case_no":               "25-21814-PDR",
        "chapter":               "13",
        "motion_calendar_date":  "April 6, 2026",
        "petition_date":         "September 26, 2025",
        "dismissal_date":        "March 1, 2026",
        "dismissed_case_number": "24-99999-PDR",
        "docket_entry_no":       "15",
        "expedite":              "expedite",
        "trustees_reason":       "Failure to make plan payments",
        "dismissal_reason":      "The Debtor fell behind on plan payments due to a temporary loss of employment.",
        "change_in_circum":      "The Debtor has secured new employment and can now maintain regular plan payments.",
    }

    print("Testing motion to extend functionality...")

    docx_path, pdf_path = generate_both_formats_from_payload(test_payload)
    print(f"DOCX generated: {docx_path}")
    print(f"PDF generated: {pdf_path}")
