"""Parse user-uploaded supporting docs into content blocks for Claude's multimodal HumanMessage input.

Dispatches on file extension:
  - pdf              -> AttachedPdfDoc (base64, attached as document block)
  - png/jpg/jpeg     -> AttachedImageDoc (base64, attached as image block)
  - docx             -> InlineTextDoc (extracted text, inlined in the prompt)
  - txt/md           -> InlineTextDoc (decoded text, inlined in the prompt)

Unknown extensions raise HTTPException(400). Attachment vs. inlining is
chosen by what Claude can ingest natively: PDFs and images go as content
blocks (preserving layout/tables/visuals); DOCX has no native block type
so we extract text and rely on Docx2txtLoader; plain text files are
trivially decoded.

The output union (SupportingDoc) is consumed by ExplanationEnhanceAgent,
which interleaves the inline-text docs into the prompt preamble and
appends the attached-pdf / attached-image blocks to the HumanMessage
content list.
"""

import base64
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import HTTPException
from langchain_community.document_loaders import Docx2txtLoader
from pydantic import BaseModel


class InlineTextDoc(BaseModel):
    """Doc that gets inlined as text into the enhancement prompt."""
    kind: Literal["inline_text"] = "inline_text"
    filename: str
    text: str


class AttachedPdfDoc(BaseModel):
    """Doc that gets attached as a document content block (native PDF ingest)."""
    kind: Literal["attached_pdf"] = "attached_pdf"
    filename: str
    base64_data: str


class AttachedImageDoc(BaseModel):
    """Doc that gets attached as an image content block (native vision ingest)."""
    kind: Literal["attached_image"] = "attached_image"
    filename: str
    media_type: Literal["image/png", "image/jpeg"]
    base64_data: str


SupportingDoc = InlineTextDoc | AttachedPdfDoc | AttachedImageDoc


_IMAGE_MEDIA_TYPES: dict[str, Literal["image/png", "image/jpeg"]] = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
}


def _extension(filename: str) -> str:
    return Path(filename).suffix.lstrip(".").lower()


def read_supporting_doc(filename: str, content: bytes) -> SupportingDoc:
    """Turn raw bytes + a filename into the right SupportingDoc variant.

    Raises HTTPException(400) on empty content or unknown extension.
    """
    if not content:
        raise HTTPException(status_code=400, detail=f"Supporting doc '{filename}' is empty")

    ext = _extension(filename)
    if not ext:
        raise HTTPException(
            status_code=400,
            detail=f"Supporting doc '{filename}' has no file extension",
        )

    if ext == "pdf":
        return AttachedPdfDoc(
            filename=filename,
            base64_data=base64.standard_b64encode(content).decode("ascii"),
        )

    if ext in _IMAGE_MEDIA_TYPES:
        return AttachedImageDoc(
            filename=filename,
            media_type=_IMAGE_MEDIA_TYPES[ext],
            base64_data=base64.standard_b64encode(content).decode("ascii"),
        )

    if ext == "docx":
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=True) as tmp:
            tmp.write(content)
            tmp.flush()
            docs = Docx2txtLoader(tmp.name).load()
        text = "\n\n".join(d.page_content for d in docs).strip()
        return InlineTextDoc(filename=filename, text=text)

    if ext in {"txt", "md"}:
        try:
            text = content.decode("utf-8").strip()
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=400,
                detail=f"Supporting doc '{filename}' is not valid UTF-8",
            )
        return InlineTextDoc(filename=filename, text=text)

    raise HTTPException(
        status_code=400,
        detail=(
            f"Supporting doc '{filename}' has unsupported extension '{ext}'. "
            "Supported: pdf, docx, txt, md, png, jpg, jpeg."
        ),
    )
