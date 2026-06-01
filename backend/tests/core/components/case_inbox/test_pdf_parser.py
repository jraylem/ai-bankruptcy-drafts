"""SSN extraction from bankruptcy petition PDFs — 3-state return contract."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.core.components.case_inbox import pdf_parser


def _mock_extracted_text(text: str):
    """Patch the module's internal text-extraction helper to return `text`.

    Avoids needing real PDF fixtures — the SSN regex logic is what we're
    testing, not pdfplumber itself."""
    return patch.object(pdf_parser, "_extract_text", return_value=text)


@pytest.mark.unit
def test_extract_ssn_found_standard_format():
    with _mock_extracted_text("Debtor SSN: xxx-xx-1879 filed pro se"):
        ssn, status = pdf_parser.extract_ssn_last_four(b"%PDF-fake")
    assert (ssn, status) == ("1879", "found")


@pytest.mark.unit
def test_extract_ssn_found_uppercase_x_variant():
    with _mock_extracted_text("Debtor SSN: XXX-XX-4242"):
        ssn, status = pdf_parser.extract_ssn_last_four(b"%PDF-fake")
    assert (ssn, status) == ("4242", "found")


@pytest.mark.unit
def test_extract_ssn_found_em_dash_spaced_format():
    """PACER sometimes renders SSN with em dashes + inter-digit spaces."""
    with _mock_extracted_text("Debtor SSN: xxx – xx – 9 8 2 3"):
        ssn, status = pdf_parser.extract_ssn_last_four(b"%PDF-fake")
    assert (ssn, status) == ("9823", "found")


@pytest.mark.unit
def test_extract_ssn_not_found_when_text_present_but_no_match():
    with _mock_extracted_text("Voluntary Petition — no SSN visible on this page"):
        ssn, status = pdf_parser.extract_ssn_last_four(b"%PDF-fake")
    assert (ssn, status) == (None, "not_found")


@pytest.mark.unit
def test_extract_ssn_scanned_image_when_no_text_extractable():
    """pdfplumber returns nothing for image-only PDFs → status='scanned_image'."""
    with _mock_extracted_text(""):
        ssn, status = pdf_parser.extract_ssn_last_four(b"%PDF-fake")
    assert (ssn, status) == (None, "scanned_image")


@pytest.mark.unit
def test_extract_ssn_scanned_when_pdfplumber_raises():
    """Corrupt PDF that crashes pdfplumber should map to 'scanned_image'
    (treat as 'we don't know' rather than crashing the ingest)."""
    with patch.object(pdf_parser.pdfplumber, "open", side_effect=Exception("bad pdf")):
        ssn, status = pdf_parser.extract_ssn_last_four(b"not a real pdf")
    assert (ssn, status) == (None, "scanned_image")
