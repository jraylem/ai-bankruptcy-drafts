"""SSN extraction from bankruptcy petition PDFs (Form B101).

Ported from `ecf-petition-downloader/src/pdf_parser.py`. Two changes:
  1. Accepts BytesIO instead of a file path
  2. Returns a typed `(ssn_last4, status)` tuple instead of a "SS_xxxx"
     string. Three statuses preserve the legacy distinction:
       - 'found'          → ssn_last4 has 4 digits
       - 'not_found'      → text extracted but SSN pattern didn't match
       - 'scanned_image'  → pdfplumber returned no text (image-only PDF)

Two regex variants cover both PACER PDF rendering formats:
  - Primary  : `xxx-xx-1879`     (standard hyphens)
  - Fallback : `xxx – xx – 9 8 2 3` (em dashes + inter-digit spaces)
"""

from __future__ import annotations

import logging
import re
from io import BytesIO
from typing import Literal

import pdfplumber

logger = logging.getLogger(__name__)

# Suppress noisy "Could not get FontBBox from font descriptor" warnings
# that pdfplumber/pdfminer emit on PACER PDFs with embedded subset fonts.
logging.getLogger("pdfminer").setLevel(logging.ERROR)

SsnExtractionStatus = Literal["found", "not_found", "scanned_image"]

# Primary: standard masked SSN
_SSN_PATTERN = re.compile(r"[xX*]{3}-[xX*]{2}-(\d{4})")
# Fallback: em dashes + inter-digit spaces, e.g. "xxx – xx – 9 8 2 3"
_SSN_PATTERN_ALT = re.compile(r"[xX*]{3}\s*–\s*[xX*]{2}\s*–\s*(\d\s?\d\s?\d\s?\d)")


def _extract_text(pdf_bytes: bytes) -> str:
    """Pull text from every page; concat with newlines. Empty string if
    pdfplumber can't extract anything (image-only PDF)."""
    chunks: list[str] = []
    try:
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    chunks.append(text)
    except Exception as e:
        # Corrupt PDF / unsupported format — treat as image-only so
        # the operator-facing label is the right one.
        logger.warning("pdfplumber failed to read PDF: %s", e)
        return ""
    return "\n".join(chunks)


def extract_ssn_last_four(pdf_bytes: bytes) -> tuple[str | None, SsnExtractionStatus]:
    """Return (ssn_last4, status).

    Status meaning:
      - 'found'         : ssn_last4 is the 4-digit string
      - 'not_found'     : text extracted but no SSN pattern matched
      - 'scanned_image' : pdfplumber returned no text → likely a scanned
                          PDF; SSN can't be auto-extracted. Paralegal
                          should review manually after Accept.
    """
    text = _extract_text(pdf_bytes)
    if not text:
        return (None, "scanned_image")

    match = _SSN_PATTERN.search(text)
    if match:
        return (match.group(1), "found")

    match_alt = _SSN_PATTERN_ALT.search(text)
    if match_alt:
        return (match_alt.group(1).replace(" ", ""), "found")

    return (None, "not_found")
