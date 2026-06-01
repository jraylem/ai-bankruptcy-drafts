from __future__ import annotations
from pathlib import Path
from .generator_common import generate_document
from zipfile import ZipFile
import json
import re
from datetime import date
from dateutil.parser import parse
from docxtpl import DocxTemplate
from langchain.chat_models import init_chat_model
from ..config import settings
from ..ai_models import CLAUDE_MODEL_STANDARD, CLAUDE_PROVIDER

# -------------------- paths --------------------
BASE_DIR = Path(__file__).parent.resolve()
DATAFILE = BASE_DIR / "data" / "payload.reinstate.json"
OUT_DIR = BASE_DIR / "out"

TEMPLATE_CANDIDATES = [
    BASE_DIR.parent / "templates" / "motion_to_reinstate.docx",
]

OUTPUT_BASENAME = "Motion_to_Reinstate_FILLED"

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
    raise SystemExit("Template not found. Place 'motion_to_reinstate.docx' under templates/.")


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
        doc.ExportAsFixedFormat(str(pdf_path.resolve()), 17)  # wdExportFormatPDF = 17
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


# -------------------- AI suggestions --------------------

# Called by: tasks/pleading_tasks._enrich_prefilled() (reinstate motion type only)
def generate_why_dismissed_suggestions(motion_payload: dict = None, session_id: str = None) -> list:
    """
    Generate 3 distinct suggestions for WhyDismissedDetailed shown as clickable chips at AWAITING_INPUT.

    Searches the petition PDF vectorstore for case context, incorporates DismissalReason
    from the payload, then uses Claude to draft 3 distinct 2-3 sentence explanations
    in formal legal tone.

    Returns a list of 3 suggestion strings, or [] on failure.
    """
    try:
        # Step 1 — pull case context from the petition PDF
        pdf_context = ""
        if session_id:
            from ..chatbot.vectorestore import search_vectorstore
            pdf_collection = f"bankruptcy_knowledge_{session_id}"
            try:
                docs = search_vectorstore(
                    "dismissal delinquency plan payments income employment hardship financial difficulty",
                    collection_name=pdf_collection,
                    k=5,
                )
                if docs:
                    pdf_context = "\n".join(
                        d.page_content for d in docs if hasattr(d, "page_content")
                    )
            except Exception as search_err:
                print(f"WARNING: Could not search PDF for case context: {search_err}")

        debtor_name = (motion_payload or {}).get("DebtorName", "")
        debtor_ref = f"The Debtor, {debtor_name}," if debtor_name and debtor_name != "N/A" else "The Debtor"

        dismissal_reason = (motion_payload or {}).get("DismissalReason", "")
        dismissal_section = (
            f"\n\nDismissal reason on record: {dismissal_reason}"
            if dismissal_reason and dismissal_reason.upper() != "N/A"
            else ""
        )
        context_section = f"\n\nPetition data:\n{pdf_context}" if pdf_context else ""

        # Step 2 — generate 3 distinct explanations using Claude
        model = init_chat_model(
            CLAUDE_MODEL_STANDARD,
            model_provider=CLAUDE_PROVIDER,
            api_key=settings.ANTHROPIC_API_KEY,
            temperature=0.4,
        )

        no_dismissal_reason = not dismissal_section
        primary_source_rule = (
            "- No dismissal reason on record is available. Generate explanations assuming the most "
            "common Ch. 13 dismissal cause: the Debtor fell behind on plan payments due to a "
            "temporary financial hardship (e.g. loss of income, unexpected expense, or reduced "
            "employment). Do NOT reference specific causes not supported by petition data.\n"
            if no_dismissal_reason
            else "- The dismissal reason on record is the PRIMARY source — base the explanation on it\n"
        )

        prompt = (
            f"Write 3 distinct explanations for why a bankruptcy case was dismissed, "
            f"for use in a Motion to Reinstate. Each must begin with '{debtor_ref}'. Rules:\n"
            "- Each explanation is 2 to 3 sentences\n"
            "- Be vague but factual — do NOT mention specific dates, chapter numbers, or legal code citations\n"
            + primary_source_rule +
            "- Use petition data ONLY if it directly relates to why the case was dismissed (e.g. income, employment, hardship) — ignore anything unrelated such as exemptions, credit counseling, or assets\n"
            "- Formal third-person legal tone, no filler words\n"
            "- Make each of the 3 explanations meaningfully different in phrasing and emphasis\n"
            "- Return ONLY a valid JSON array of 3 strings, nothing else\n\n"
            "Example:\n"
            "[\n"
            f"  \"{debtor_ref} was out of work for some time following an injury which led to a loss of "
            "income and prevented them from catching up on their plan payments before the notice of "
            "delinquency expired.\",\n"
            f"  \"{debtor_ref} experienced a sudden reduction in household income that made it impossible "
            "to maintain the required plan payments, ultimately resulting in the dismissal of the case "
            "before the Debtor could cure the arrears.\",\n"
            f"  \"{debtor_ref} encountered unforeseen financial hardship that disrupted their ability to "
            "remain current on plan obligations, and the case was dismissed before the Debtor had a "
            "meaningful opportunity to address the delinquency.\"\n"
            "]\n\n"
            "Return only the JSON array, nothing else."
            f"{dismissal_section}"
            f"{context_section}"
        )

        response = model.invoke(prompt)
        result = (response.content or "").strip()

        match = re.search(r'\[.*\]', result, re.DOTALL)
        if match:
            suggestions = json.loads(match.group())
            if isinstance(suggestions, list) and all(isinstance(s, str) for s in suggestions):
                return suggestions[:3]
        return [result] if result else []

    except Exception as e:
        print(f"WARNING: Failed to generate WhyDismissedDetailed suggestions: {e}")
        return []


# -------------------- context builder --------------------
def build_context(ai: dict) -> dict:
    """Build template context from MotionReinstatePayload fields (src/tasks/schemas.py)."""
    date_filed = (ai.get("DateFiled") or "N/A").strip()
    dismissed_date = (ai.get("DismissedDate") or "N/A").strip()

    import re as _re
    _raw_debtor = (ai.get("DebtorName") or "N/A").strip()
    _parts = [p.strip() for p in _re.split(r',\s*(?:and\s+)?|\s+and\s+', _raw_debtor) if p.strip()]
    header_debtor_name = "\n".join(_parts) if _parts else _raw_debtor

    return {
        "HeaderDebtorName": header_debtor_name,
        "DebtorName": _raw_debtor,
        "CaseNumber": (ai.get("CaseNumber") or "N/A").strip(),
        "ChapterNumb": str(ai.get("ChapterNumb") or "N/A").strip(),
        "DateFiled": fmt_long(parse_date(date_filed)) if date_filed else date_filed,
        "DismissedDate": fmt_long(parse_date(dismissed_date)) if dismissed_date else dismissed_date,
        "DismissalReason": (ai.get("DismissalReason") or "n/a").strip().lower(),
        "WhyDismissedDetailed": (ai.get("WhyDismissedDetailed") or "N/A").strip(),
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


# -------------------- orchestration --------------------
def resolve_template_from_payload(payload: dict) -> Path:
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
    sample = {
        "DebtorName": "Laura Marie Cavazos and Moises Rafael Cavazos",
        "CaseNumber": "25-12793-PDR",
        "ChapterNumb": "13",
        "DateFiled": "September 26, 2025",
        "DismissedDate": "September 18, 2025",
        "DismissalReason": "Upon Denial of Confirmation of Plan",
        "WhyDismissedDetailed": "The Debtor, Benjamin Wendell Ingram, was unable to secure confirmation of the reorganization plan, resulting in the dismissal of the case before the Debtor had a sufficient opportunity to cure the deficiencies and present a plan that met the applicable confirmation standards.",
    }
    ctx = build_context(sample)
    out_docx = render_docx(template, ctx, OUTPUT_BASENAME)
    print("DOCX generated:", out_docx.resolve())
    out_pdf = convert_to_pdf(out_docx)
    print("PDF generated:", out_pdf.resolve())


if __name__ == "__main__":
    test_payload = {
        "DebtorName":           "Laura Marie Cavazos and Moises Rafael Cavazos",
        "CaseNumber":           "25-12793-PDR",
        "ChapterNumb":          "13",
        "DateFiled":            "September 26, 2025",
        "DismissedDate":        "September 18, 2025",
        "DismissalReason":      "Upon Denial of Confirmation of Plan",
        "WhyDismissedDetailed": "The Debtor, Benjamin Wendell Ingram, was unable to secure confirmation of the reorganization plan, resulting in the dismissal of the case before the Debtor had a sufficient opportunity to cure the deficiencies and present a plan that met the applicable confirmation standards.",
    }

    print("Testing motion to reinstate functionality...")

    docx_path, pdf_path = generate_both_formats_from_payload(test_payload)
    print(f"DOCX generated: {docx_path}")
    print(f"PDF generated: {pdf_path}")
