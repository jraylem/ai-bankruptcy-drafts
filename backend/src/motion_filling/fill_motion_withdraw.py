from pathlib import Path
from .generator_common import generate_document
from zipfile import ZipFile
import subprocess, shutil, re
from docxtpl import DocxTemplate
from ..config import settings

BASE_DIR = Path(__file__).parent.resolve()
OUT_DIR  = BASE_DIR / "out"

# Template for motion to withdraw
TEMPLATE_CANDIDATES = [
    BASE_DIR.parent / "templates" / "motion_to_withdraw.docx",
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

# ---------- AI enhancement helpers ----------

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

# ---------- shared helpers (order / motion) ----------

def build_context(ai: dict) -> dict:
    """
    Build context dictionary for motion to withdraw template.
    
    Expected payload fields:
    - DebtorName: Debtor's full name
    - CaseNumber: Case number (may include judge initial)
    - Chapter: Chapter number (e.g., "13")
    - Judge: Judge initial (e.g., "JCC")
    - DebtorCurrentAddy: Debtor's current address
    """
    # Extract fields from payload
    debtor_name = (ai.get("DebtorName") or "").strip()
    case_number = (ai.get("CaseNumber") or "").strip()
    chapter = str(ai.get("Chapter") or "").strip()
    judge = (ai.get("Judge") or "").strip()
    debtor_address = (ai.get("DebtorCurrentAddy") or "").strip()

    import re as _re
    _parts = [p.strip().title() for p in _re.split(r',\s*(?:and\s+)?|\s+and\s+', debtor_name) if p.strip()]
    header_debtor_name = "\n".join(_parts) if _parts else (debtor_name.title() if debtor_name else "")

    ctx = {
        "HeaderDebtorName": header_debtor_name,
        "DebtorName": debtor_name.title() if debtor_name else "",
        "CaseNumber": case_number,
        "ChapterNumb": chapter,
        "Judge": judge,
        "DebtorCurrentAddy": debtor_address,
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
        default_basename="motion_withdraw",
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
    name_slug = output_basename or "motion_withdraw"
    out_docx = render_docx(template, ctx, name_slug)
    
    # Convert DOCX to PDF
    out_pdf = convert_to_pdf(out_docx)
    
    return out_docx, out_pdf


# -------------------- main --------------------
if __name__ == "__main__":
    test_payload = {
        "DebtorName":        "Laura Marie Cavazos and Moises Rafael Cavazos",
        "CaseNumber":        "25-21814-PDR",
        "Chapter":           "13",
        "Judge":             "PDR",
        "DebtorCurrentAddy": "123 Main Street, Hollywood, FL 33020",
    }

    print("Testing motion to withdraw functionality...")

    docx_path, pdf_path = generate_both_formats_from_payload(test_payload)
    print(f"DOCX generated: {docx_path}")
    print(f"PDF generated: {pdf_path}")
