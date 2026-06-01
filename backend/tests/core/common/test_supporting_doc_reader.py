"""Tests for supporting_doc_reader — dispatch on file extension.

Covers:
  - PDF / DOCX / TXT / MD / PNG / JPG / JPEG → correct SupportingDoc variant
  - unknown extension → HTTPException(400)
  - empty content → HTTPException(400)
  - non-utf8 text file → HTTPException(400)
"""

import base64
from io import BytesIO

import pytest
from docx import Document
from fastapi import HTTPException

from src.core.common.documents.supporting_doc_reader import (
    AttachedImageDoc,
    AttachedPdfDoc,
    InlineTextDoc,
    read_supporting_doc,
)


def _simple_docx_bytes(paragraphs: list[str]) -> bytes:
    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest.mark.unit
def test_pdf_returns_attached_pdf_with_base64():
    content = b"%PDF-1.4 fake pdf bytes"
    result = read_supporting_doc("petition.pdf", content)

    assert isinstance(result, AttachedPdfDoc)
    assert result.filename == "petition.pdf"
    assert base64.standard_b64decode(result.base64_data) == content


@pytest.mark.unit
@pytest.mark.parametrize("ext,media_type", [
    ("png", "image/png"),
    ("jpg", "image/jpeg"),
    ("jpeg", "image/jpeg"),
])
def test_image_returns_attached_image_with_media_type(ext, media_type):
    content = b"fake image bytes"
    result = read_supporting_doc(f"photo.{ext}", content)

    assert isinstance(result, AttachedImageDoc)
    assert result.media_type == media_type
    assert base64.standard_b64decode(result.base64_data) == content


@pytest.mark.unit
def test_docx_returns_inline_text_with_extracted_body():
    content = _simple_docx_bytes(["First paragraph.", "Second paragraph."])
    result = read_supporting_doc("termination.docx", content)

    assert isinstance(result, InlineTextDoc)
    assert "First paragraph." in result.text
    assert "Second paragraph." in result.text


@pytest.mark.unit
def test_txt_returns_inline_text_decoded_utf8():
    content = "Plain text explanation.\nLine two.".encode("utf-8")
    result = read_supporting_doc("note.txt", content)

    assert isinstance(result, InlineTextDoc)
    assert result.text == "Plain text explanation.\nLine two."


@pytest.mark.unit
def test_md_returns_inline_text_decoded_utf8():
    content = "# Header\n\nSome markdown body.".encode("utf-8")
    result = read_supporting_doc("note.md", content)

    assert isinstance(result, InlineTextDoc)
    assert result.text.startswith("# Header")


@pytest.mark.unit
def test_unknown_extension_raises_400():
    with pytest.raises(HTTPException) as exc:
        read_supporting_doc("malware.exe", b"whatever")
    assert exc.value.status_code == 400
    assert "unsupported extension" in exc.value.detail


@pytest.mark.unit
def test_missing_extension_raises_400():
    with pytest.raises(HTTPException) as exc:
        read_supporting_doc("no_extension_file", b"whatever")
    assert exc.value.status_code == 400
    assert "no file extension" in exc.value.detail


@pytest.mark.unit
def test_empty_content_raises_400():
    with pytest.raises(HTTPException) as exc:
        read_supporting_doc("note.txt", b"")
    assert exc.value.status_code == 400


@pytest.mark.unit
def test_non_utf8_text_raises_400():
    # invalid UTF-8 continuation byte sequence
    with pytest.raises(HTTPException) as exc:
        read_supporting_doc("note.txt", b"\xff\xfe\xfa")
    assert exc.value.status_code == 400
    assert "UTF-8" in exc.value.detail
