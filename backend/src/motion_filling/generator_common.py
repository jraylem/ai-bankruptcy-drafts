"""Shared document generation orchestration helpers."""

from pathlib import Path
from typing import Callable


def generate_document(
    payload_data: dict,
    output_basename: str | None,
    output_type: str,
    default_basename: str,
    resolve_template: Callable[[dict], Path],
    build_context: Callable[[dict], dict],
    render_docx: Callable[[Path, dict, str], Path],
    convert_to_pdf: Callable[[Path], Path],
) -> Path:
    """Render DOCX from payload and optionally convert it to PDF."""
    template = resolve_template(payload_data)
    context = build_context(payload_data)
    name_slug = output_basename or default_basename
    out_docx = render_docx(template, context, name_slug)

    if output_type == "docx":
        return out_docx
    if output_type == "pdf":
        return convert_to_pdf(out_docx)

    raise ValueError(
        f"Unsupported output_type: {output_type}. Expected 'pdf' or 'docx'."
    )
