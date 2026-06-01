"""
Order on Motion for Extension filling functionality.
This module handles the creation and filling of order on motion for extension documents.
"""

from __future__ import annotations
from pathlib import Path
from .generator_common import generate_document
from zipfile import ZipFile
import json, re
from typing import Dict, Any, Optional
from docxtpl import DocxTemplate

# -------------------- paths --------------------
BASE_DIR = Path(__file__).parent.resolve()
OUT_DIR  = BASE_DIR / "out"

TEMPLATE_CANDIDATES = [
    BASE_DIR.parent / "templates" / "order_motion_extension.docx",
]

OUTPUT_BASENAME = "Order_Motion_Extension_FILLED"

# -------------------- helpers --------------------
def ensure_docx_template() -> Path:
    for p in TEMPLATE_CANDIDATES:
        if p.exists():
            return p
    raise SystemExit("Template not found. Place 'order_motion_extension.docx' under templates/ .")


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

    This function formats the payload data for the template.
    """
    # Split "A and B" or "A, B, and C" into one name per line
    raw_debtor = payload.get("DebtorName", "")
    import re as _re
    _parts = [p.strip() for p in _re.split(r',\s*(?:and\s+)?|\s+and\s+', raw_debtor) if p.strip()]
    header_debtor_name = "\n".join(_parts) if _parts else raw_debtor

    ctx = {
        "HeaderDebtorName":      header_debtor_name,
        "DebtorName":            payload.get("DebtorName", ""),
        "CaseNumber":            payload.get("CaseNumber", ""),
        "ChapterNumber":         payload.get("ChapterNumber", ""),
        "DocketNumber":          payload.get("DocketNumber", "N/A"),
        "DateFiled":             payload.get("DateFiled", ""),
        "DateFiledPlusFourteen": payload.get("DateFiledPlusFourteen", "N/A"),
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
    """Resolve the template path. For order extension, we use a single template."""
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
        payload_data: Dictionary containing the order extension data
        output_basename: Optional custom output filename (without extension)

    Returns:
        tuple[Path, Path]: (docx_path, pdf_path)
    """
    print(f"INFO: Generating order extension documents...")
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
        "DebtorName":            "Laura Marie Cavazos and Moises Rafael Cavazos",
        "CaseNumber":            "25-14980-PDR",
        "ChapterNumber":         "13",
        "DocketNumber":          "42",
        "DateFiled":             "March 1, 2025",
        "DateFiledPlusFourteen": "March 21, 2025",
    }

    print("Testing order extension functionality...")

    docx_path, pdf_path = generate_both_formats_from_payload(test_payload)
    print(f"DOCX generated: {docx_path}")
    print(f"PDF generated: {pdf_path}")
