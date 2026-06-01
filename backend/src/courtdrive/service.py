import logging
from pathlib import Path
import json
import re
from typing import Any, Dict, Optional
from sqlalchemy import create_engine, text as sql_text
from ..config import settings
from ..chatbot.agent import (
    DebtorNameAgent,
    CaseNumberAgent,
)

logger = logging.getLogger(__name__)


# Matches case patterns like (all normalized to XX-XXXXX on save):
# - 1:25-bk-15244  ->  25-15244
# - 9-26-bk-11158  ->  26-11158
# - 26-bk-11158    ->  26-11158
# - 26-11993       ->  26-11993
# - 25-31154-KKS   ->  25-31154
# - 23_18356_PDR   ->  23-18356
_CASE_WITH_CHAPTER_PATTERN = r"\d{1,2}[:\-_ ]\d{2}[-_ ]bk[-_ ]\d{4,7}(?:[-_ ][A-Za-z]{2,5})?"
_CASE_BK_PATTERN = r"\d{2}[-_ ]bk[-_ ]\d{4,7}(?:[-_ ][A-Za-z]{2,5})?"
_CASE_NON_BK_PATTERN = r"\d{2}[-_ ]\d{5}(?:[-_ ][A-Za-z]{2,5})?"

CASE_NUMBER_REGEX = re.compile(
    rf"(?i)(?<![A-Za-z0-9])(?:{_CASE_WITH_CHAPTER_PATTERN}|{_CASE_BK_PATTERN}|{_CASE_NON_BK_PATTERN})(?![A-Za-z0-9])"
)
TRAILING_CASE_SUFFIX_REGEX = re.compile(
    rf"(?i)[\s\-_]+(?:{_CASE_WITH_CHAPTER_PATTERN}|{_CASE_BK_PATTERN}|{_CASE_NON_BK_PATTERN})\s*$"
)

_MASKED_SSN_LAST4_REGEX = re.compile(r"[xX*]{3}\s*[-–]\s*[xX*]{2}\s*[-–]\s*(\d(?:\s*\d){3})")
_FULL_SSN_LAST4_REGEX = re.compile(r"\b\d{3}\s*[-–]\s*\d{2}\s*[-–]\s*(\d{4})\b")

_DEBTOR_NAME_REGEXES = [
    re.compile(
        r"(?m)\b[Dd]ebtor(?:\s*1)?(?:\s*\(.*?\))?\s*[:\-]?\s*([A-Z][A-Za-z ,.'\-]{2,80})"
    ),
    re.compile(
        r"(?im)\bdebtor'?s?\s*name\s*[:\-]?\s*([A-Za-z][A-Za-z ,.'\-]{2,80})"
    ),
]

_COURT_REGION_ALIASES = {
    "southern": "southern",
    "south": "southern",
    "s": "southern",
    "sdfla": "southern",
    "sdfl": "southern",
    "southerndistrictofflorida": "southern",
    "flsb": "southern",
    "flsbke": "southern",
    "middle": "middle",
    "mid": "middle",
    "m": "middle",
    "mdfla": "middle",
    "mdfl": "middle",
    "middledistrictofflorida": "middle",
    "flmb": "middle",
    "flmbke": "middle",
    "northern": "northern",
    "north": "northern",
    "n": "northern",
    "ndfla": "northern",
    "ndfl": "northern",
    "northerndistrictofflorida": "northern",
    "flnb": "northern",
    "flnbke": "northern",
}

def normalize_case_value(value: str) -> str:
    """Normalize case numbers for forgiving comparisons."""
    return "".join(ch.lower() for ch in (value or "") if ch.isalnum())


def strip_case_number_suffix(value: Optional[str]) -> str:
    """Remove trailing case-number-like suffixes from a debtor/client name."""
    text = (value or "").strip()
    if not text:
        return ""
    return TRAILING_CASE_SUFFIX_REGEX.sub("", text).strip()


def normalize_client_name(value: str) -> str:
    """Normalize client names for case-insensitive comparisons."""
    cleaned = strip_case_number_suffix(value).lower()
    # Normalize common multi-debtor separators into "and" for stable matching.
    cleaned = re.sub(r"\s*(?:&|/|\+)\s*", " and ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def normalize_court_region_identifier(value: Optional[str]) -> Optional[str]:
    """
    Normalize court region strings from filename identifiers.

    Returns normalized `northern|middle|southern` when recognized, otherwise
    returns the cleaned lowercase value for observability.
    """
    if not value:
        return None

    key = re.sub(r"[^a-z]", "", value.strip().lower())
    if not key:
        return None
    return _COURT_REGION_ALIASES.get(key, key)


_DISTRICT_EMAIL_CODES = ("flsb", "flmb", "flnb", "pawb")

_DISTRICT_TEXT_MAP = [
    ("southern district", "flsb"),
    ("middle district",   "flmb"),
    ("northern district", "flnb"),
    ("western district",  "pawb"),
]


def extract_district_from_pdf_path(pdf_path: str, fast_only: bool = False) -> Optional[str]:
    """Return the district code for a petition PDF.

    Strategy (in order — fastest to slowest):
    1. Filename suffix — e.g. Bankruptcy_Petition_..._FLSB.pdf (no I/O needed).
    2. Phrase matching — keyword scan of first two pages (no AI call).
    3. AI extraction — send first-page text to Claude as last resort.
       Skipped when fast_only=True.

    Returns flsb, flmb, flnb, or pawb — or None if not determinable.
    """
    # 1. Filename suffix check (fastest — zero I/O)
    stem = Path(pdf_path).stem.upper()
    for code in _DISTRICT_EMAIL_CODES:
        if stem.endswith(f"_{code.upper()}"):
            logger.debug("district from filename suffix: %s", code)
            return code

    # Extract text from first two pages for steps 2 and 3
    page_text: Optional[str] = None
    try:
        from pypdf import PdfReader
        logger.debug("pdf path: %s", pdf_path)
        reader = PdfReader(pdf_path)
        pages = reader.pages[:2]
        extracted = " ".join((p.extract_text() or "") for p in pages).strip()
        page_text = extracted if extracted else None
        logger.debug("district PDF text (%d chars): %r", len(extracted), extracted[:200])
    except Exception as e:
        logger.debug("district PDF extraction error for %s: %s", pdf_path, e)

    # 2. Phrase matching (fast — no AI call)
    # Normalize whitespace so "Southern   District" matches "southern district"
    if page_text:
        text_lower = re.sub(r"\s+", " ", page_text.lower())
        for phrase, code in _DISTRICT_TEXT_MAP:
            if phrase in text_lower:
                logger.debug("district from phrase match: %s", code)
                return code

    # 3. AI extraction (slowest — only if text is present but phrase match failed)
    if page_text and not fast_only:
        try:
            import anthropic
            from ..ai_models import CLAUDE_MODEL_FAST
            client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
            response = client.messages.create(
                model=CLAUDE_MODEL_FAST,
                max_tokens=30,
                temperature=0,
                system="You extract US Bankruptcy Court district names from petition text.",
                messages=[{
                    "role": "user",
                    "content": (
                        "What district is this bankruptcy court petition filed in? "
                        "Reply with only the district name as written in the document "
                        "(e.g. 'Southern District of Florida', 'Middle District of Florida').\n\n"
                        + page_text[:2000]
                    ),
                }],
            )
            ai_answer = response.content[0].text.strip().lower()
            logger.debug("district AI answer: %r", ai_answer)
            for phrase, code in _DISTRICT_TEXT_MAP:
                if phrase in ai_answer:
                    return code
        except Exception as e:
            logger.debug("district AI error: %s", e)

    return None


def extract_district_from_sender_emails(sender_emails: list[str]) -> Optional[str]:
    """Return the first district code found in a list of sender email addresses.

    Recognized codes: flsb, flmb, flnb, pawb.
    """
    for email in sender_emails:
        email_lower = (email or "").lower()
        for code in _DISTRICT_EMAIL_CODES:
            if code in email_lower:
                return code
    return None


def normalize_to_short_case_number(value: str) -> str:
    """Normalize any case number format to the canonical XX-XXXXX format.

    Accepted inputs:
    - 1:25-bk-15244  ->  25-15244
    - 26-bk-11993    ->  26-11993
    - 26-11993       ->  26-11993
    - 25-31154-KKS   ->  25-31154
    """
    candidate = (value or "").strip()
    if not candidate:
        return candidate

    normalized = re.sub(r"[_\s]+", "-", candidate)
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    normalized = re.sub(r"(?i)-bk-", "-bk-", normalized)

    # Pattern: chapter:year-bk-number (e.g. 1:25-bk-15244)
    chapter_match = re.fullmatch(
        r"(?i)(\d{1,2})[:-](\d{2})-bk-(\d{4,7})(?:-([A-Za-z]{2,5}))?",
        normalized,
    )
    if chapter_match:
        return f"{chapter_match.group(2)}-{chapter_match.group(3)}"

    # Pattern: year-bk-number (e.g. 26-bk-11993)
    bk_match = re.fullmatch(
        r"(?i)(\d{2})-bk-(\d{4,7})(?:-([A-Za-z]{2,5}))?",
        normalized,
    )
    if bk_match:
        return f"{bk_match.group(1)}-{bk_match.group(2)}"

    # Pattern: year-number with optional judge suffix (e.g. 26-11993, 25-31154-KKS)
    short_match = re.fullmatch(
        r"(?i)(\d{2})-(\d{5})(?:-([A-Za-z]{2,5}))?",
        normalized,
    )
    if short_match:
        return f"{short_match.group(1)}-{short_match.group(2)}"

    return candidate


def _canonicalize_case_number_match(value: str) -> str:
    """Normalize case separators and return canonical XX-XXXXX case-number formatting."""
    return normalize_to_short_case_number(value)


def extract_petition_metadata_from_filename(filename: str) -> dict[str, Optional[str]]:
    """
    Parse downloader filename pattern:
    Bankruptcy_Petition_{CaseName}_{CaseNumber}_{SSN}_{CourtRegion}.pdf
    """
    result: dict[str, Optional[str]] = {
        "client_name": None,
        "case_number": None,
        "ssn_last4": None,
        "court_region": None,
        "normalized_court_region": None,
    }

    if not filename:
        return result

    stem = Path(filename).stem
    stripped = re.sub(r"(?i)^bankruptcy[_\s-]*petition[_\s-]*", "", stem).strip("_- ")
    if stripped == stem:
        return result

    body_segment = stripped
    tokens = [token for token in stripped.split("_") if token != ""]
    label_pattern = re.compile(r"(?i)ssn?|ss")

    # Supported suffixes:
    # - ..._<SSN4>_<CourtRegion>
    # - ..._SS_<SSN4>_<CourtRegion>
    # - ..._SSN_<SSN4>_<CourtRegion>
    # - legacy variants without court region.
    if len(tokens) >= 4 and label_pattern.fullmatch(tokens[-3] or "") and re.fullmatch(r"\d{4}", tokens[-2] or ""):
        result["ssn_last4"] = tokens[-2]
        court_region = (tokens[-1] or "").strip()
        if court_region:
            result["court_region"] = court_region
            result["normalized_court_region"] = normalize_court_region_identifier(court_region)
        body_segment = "_".join(tokens[:-3])
    elif len(tokens) >= 3 and re.fullmatch(r"\d{4}", tokens[-2] or ""):
        result["ssn_last4"] = tokens[-2]
        court_region = (tokens[-1] or "").strip()
        if court_region:
            result["court_region"] = court_region
            result["normalized_court_region"] = normalize_court_region_identifier(court_region)
        body_segment = "_".join(tokens[:-2])
    elif len(tokens) >= 3 and label_pattern.fullmatch(tokens[-2] or "") and re.fullmatch(r"\d{4}", tokens[-1] or ""):
        result["ssn_last4"] = tokens[-1]
        body_segment = "_".join(tokens[:-2])
    elif len(tokens) >= 2 and re.fullmatch(r"\d{4}", tokens[-1] or ""):
        # Backward-compatible format: <name>_<case>_<ssn>
        result["ssn_last4"] = tokens[-1]
        body_segment = "_".join(tokens[:-1])

    # Parse case number from the body segment and derive case name from the left side.
    case_matches = list(CASE_NUMBER_REGEX.finditer(body_segment))
    raw_name = body_segment
    if case_matches:
        last_case_match = case_matches[-1]
        result["case_number"] = _canonicalize_case_number_match(last_case_match.group(0))
        raw_name = body_segment[: last_case_match.start()].strip("_- ")

    client_name = re.sub(r"[_\s]+", " ", raw_name).strip()
    # Normalize multi-debtor separators from filename to "and".
    client_name = re.sub(r"\s*(?:&|/|\+)\s*", " and ", client_name)
    client_name = re.sub(r"\s+", " ", client_name).strip()
    client_name = strip_case_number_suffix(client_name)
    if client_name:
        result["client_name"] = client_name

    return result


def extract_case_number_from_filename(filename: str) -> str | None:
    """Extract a bankruptcy case number from file name text."""
    if not filename:
        return None

    # Normalize separators first so names like Bankr.S.D.Fla._9-26-bk-11158_1.pdf still match.
    normalized_filename = re.sub(r"[._]+", " ", filename)
    match = CASE_NUMBER_REGEX.search(normalized_filename)
    if match:
        return _canonicalize_case_number_match(match.group(0))

    # Fallback: direct match on original filename.
    match = CASE_NUMBER_REGEX.search(filename)
    if match:
        return _canonicalize_case_number_match(match.group(0))

    return None


def extract_petition_identity_from_pdf_path(
    pdf_path: str,
    include_pdf_text_fallback: bool = True,
) -> dict[str, Optional[str]]:
    """
    Extract petition identity fields from one PDF file path.
    Uses filename metadata first, then optional PDF text fallback.
    """
    path_obj = Path(pdf_path or "")
    filename = path_obj.name if path_obj.name else ""

    metadata = extract_petition_metadata_from_filename(filename)
    case_number = metadata.get("case_number") or extract_case_number_from_filename(filename)
    client_name = metadata.get("client_name")
    ssn_last4 = metadata.get("ssn_last4")
    court_region = metadata.get("court_region")
    normalized_court_region = metadata.get("normalized_court_region")

    if include_pdf_text_fallback and path_obj.exists() and path_obj.is_file() and (
        not case_number or not client_name or not ssn_last4
    ):
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path_obj))
            text_excerpt = "\n".join((page.extract_text() or "") for page in reader.pages[:5])

            if text_excerpt:
                if not case_number:
                    case_match = CASE_NUMBER_REGEX.search(text_excerpt)
                    if case_match:
                        case_number = _canonicalize_case_number_match(case_match.group(0))

                if not client_name:
                    client_name = _extract_debtor_name_from_text(text_excerpt)
                if not ssn_last4:
                    ssn_last4 = _extract_ssn_last4_from_text(text_excerpt)
        except Exception as pdf_error:
            logger.warning("Failed identity extraction from %s: %s", pdf_path, pdf_error)

    clean_client_name = strip_case_number_suffix((client_name or "").strip()) or None
    clean_case_number = (case_number or "").strip() or None
    clean_ssn_last4 = (ssn_last4 or "").strip() or None

    return {
        "filename": filename or None,
        "path": str(path_obj) if pdf_path else None,
        "client_name": clean_client_name,
        "normalized_client_name": normalize_client_name(clean_client_name or ""),
        "case_number": clean_case_number,
        "normalized_case_number": normalize_case_value(clean_case_number or ""),
        "ssn_last4": clean_ssn_last4,
        "court_region": (court_region or "").strip() or None,
        "normalized_court_region": (normalized_court_region or "").strip() or None,
    }


def _extract_ssn_last4_from_text(text: str) -> str | None:
    match = _MASKED_SSN_LAST4_REGEX.search(text or "")
    if match:
        digits = re.sub(r"\D", "", match.group(1))
        if len(digits) == 4:
            return digits

    match = _FULL_SSN_LAST4_REGEX.search(text or "")
    if match:
        return match.group(1)

    return None


def _looks_like_person_name(value: str) -> bool:
    cleaned = re.sub(r"\s+", " ", (value or "")).strip(" :,-")
    if not cleaned:
        return False

    lowered = cleaned.lower()
    blocked_tokens = {
        "chapter",
        "district",
        "court",
        "petition",
        "case",
        "number",
        "address",
        "form",
        "forms",
        "official",
        "identify",
        "yourself",
        "all of the forms",
        "debtor 1",
        "debtor 2",
        "social security",
        "ssn",
        "first name",
        "middle name",
        "last name",
        "suffix",
        "all other names",
        # Form 101 boilerplate phrases that appear near "debtor 1" in extracted PDF text
        "filing alone",
        "filing jointly",
        "bankruptcy",
        "voluntary petition",
        "individuals filing",
        "amended filing",
        "about debtor",
    }
    if any(token in lowered for token in blocked_tokens):
        return False

    words = [w for w in cleaned.split(" ") if w]
    alpha_word_count = sum(1 for w in words if re.search(r"[A-Za-z]", w))
    return alpha_word_count >= 2


def _extract_debtor_name_from_text(text: str) -> str | None:
    if not text:
        return None

    lines = [line.strip() for line in text.splitlines() if line and line.strip()]

    def _clean_candidate(value: str) -> str:
        return re.sub(r"\s+", " ", (value or "")).strip(" :,-")

    def _looks_like_name_part(value: str) -> bool:
        candidate = _clean_candidate(value)
        if not candidate:
            return False
        lowered = candidate.lower()
        blocked_part_tokens = {
            "name",
            "debtor",
            "case",
            "number",
            "address",
            "form",
            "forms",
            "official",
            "identify",
            "yourself",
            "all",
            "other",
            "used",
        }
        if any(token in lowered for token in blocked_part_tokens):
            return False

        # Allow letters (incl. Latin-extended for accented names), apostrophes, periods,
        # spaces, and hyphens only.
        if not re.fullmatch(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ .'\-]{0,59}", candidate):
            return False

        words = [w for w in candidate.split() if w]
        if len(words) > 5:
            return False
        return True

    def _extract_inline_name(line: str) -> str | None:
        match = re.search(
            r"(?im)\b(?:your\s+full\s+name|debtor(?:\s*[12])?|debtor'?s?\s+name)\b(?:\s*\(.*?\))?\s*[:\-]?\s*(.+)$",
            line or "",
        )
        if not match:
            return None
        candidate = _clean_candidate(match.group(1))
        # Require the candidate to start with an uppercase letter — filters out
        if candidate and candidate[0].isupper() and _looks_like_person_name(candidate):
            return candidate
        return None

    def _extract_structured_name(start_idx: int) -> str | None:
        first_name = ""
        middle_name = ""
        last_name = ""

        def _extract_neighbor_value(idx: int, label_pattern: str) -> str:
            line = lines[idx]

            # Case 1: value appears on same line after label.
            inline_after = re.search(label_pattern + r"\s*[:\-]?\s*(.+)$", line, re.IGNORECASE)
            if inline_after:
                candidate = _clean_candidate(inline_after.group(1))
                if _looks_like_name_part(candidate):
                    return candidate

            # Case 2: value appears on same line before label (common in extracted Form 101 text).
            inline_before = re.search(r"^(.+?)\s*" + label_pattern + r"\b", line, re.IGNORECASE)
            if inline_before:
                candidate = _clean_candidate(inline_before.group(1))
                if _looks_like_name_part(candidate):
                    return candidate

            # Case 3: value appears on previous line.
            if idx - 1 >= start_idx:
                candidate = _clean_candidate(lines[idx - 1])
                if _looks_like_name_part(candidate):
                    return candidate

            # Case 4: value appears on next line.
            if idx + 1 < len(lines):
                candidate = _clean_candidate(lines[idx + 1])
                if _looks_like_name_part(candidate):
                    return candidate

            return ""

        # Search a small window after a debtor marker for Form 101 field labels.
        end_idx = min(len(lines), start_idx + 35)
        for idx in range(start_idx, end_idx):
            line = lines[idx]
            lowered = line.lower()

            if "first name" in lowered and not first_name:
                first_name = _extract_neighbor_value(idx, r"first\s+name")

            if "middle name" in lowered and not middle_name:
                middle_name = _extract_neighbor_value(idx, r"middle\s+name")

            if ("last name" in lowered or "last name and suffix" in lowered) and not last_name:
                last_name = _extract_neighbor_value(idx, r"last\s+name(?:\s+and\s+suffix)?")

        # When the middle name field is blank on the form, case 4 of
        # _extract_neighbor_value can steal the last name value (the candidate on
        # the next line) before the last-name label gets to claim it via case 3.
        # This produces "Tatiana Piedrahita Piedrahita" instead of "Tatiana Piedrahita".
        # Deduplicate: if middle equals last it was mis-extracted, not a real middle name.
        if middle_name and last_name and middle_name.lower() == last_name.lower():
            middle_name = ""

        full_name = _clean_candidate(" ".join(part for part in [first_name, middle_name, last_name] if part))
        if _looks_like_person_name(full_name):
            return full_name
        return None

    # 1) Prefer explicit "your full name / debtor name: ..." inline patterns.
    # Scan all lines to collect both Debtor 1 and Debtor 2 before returning.
    inline_d1 = None
    inline_d2 = None
    for line in lines[:120]:
        lowered_line = line.lower()
        candidate = _extract_inline_name(line)
        if not candidate:
            continue
        if inline_d2 is None and "debtor 2" in lowered_line:
            inline_d2 = candidate
        elif inline_d1 is None:
            inline_d1 = candidate

    if inline_d1 and inline_d2 and inline_d1.lower() != inline_d2.lower():
        return f"{inline_d1} and {inline_d2}"
    if inline_d1:
        return inline_d1

    # 2) Prefer structured Form 101 fields for Debtor 1 and Debtor 2.
    debtor_1_name = None
    debtor_2_name = None
    for idx, line in enumerate(lines[:220]):
        lowered = line.lower()
        if debtor_1_name is None and (
            "about debtor 1" in lowered or "debtor 1" in lowered or "your full name" in lowered
        ):
            debtor_1_name = _extract_structured_name(idx)

        if debtor_2_name is None and ("about debtor 2" in lowered or "debtor 2" in lowered):
            debtor_2_name = _extract_structured_name(idx)

    if debtor_1_name and debtor_2_name and debtor_1_name.lower() != debtor_2_name.lower():
        return f"{debtor_1_name} and {debtor_2_name}"
    if debtor_1_name:
        return debtor_1_name

    # 3) Fallback to broad regexes.
    for regex in _DEBTOR_NAME_REGEXES:
        match = regex.search(text)
        if not match:
            continue

        candidate = _clean_candidate(match.group(1))
        if _looks_like_person_name(candidate):
            return candidate

    # 4) Last-resort: line immediately after a debtor marker.
    for idx, line in enumerate(lines):
        lower_line = line.lower()
        if "debtor" not in lower_line:
            continue
        if idx + 1 >= len(lines):
            continue

        candidate = _clean_candidate(lines[idx + 1])
        if _looks_like_person_name(candidate):
            return candidate

    return None


def scan_uploaded_petition_identities(include_pdf_text_fallback: bool = True) -> dict[str, Any]:
    """
    Scan `/uploads` PDFs and extract best-effort identity fields used by inbox matching.
    Returns records containing filename, client_name, ssn_last4, case_number, and court region.

    When `include_pdf_text_fallback=False`, metadata is parsed from filenames only
    (fast path, no PDF text extraction).
    """
    try:
        PdfReader = None
        if include_pdf_text_fallback:
            try:
                from pypdf import PdfReader as _PdfReader
                PdfReader = _PdfReader
            except Exception as pdf_import_error:
                logger.warning("pypdf unavailable, skipping PDF text fallback: %s", pdf_import_error)
                include_pdf_text_fallback = False

        uploads_dir = Path(__file__).resolve().parent.parent.parent / "uploads"
        if not uploads_dir.exists():
            return {
                "status": "failed",
                "error": f"Uploads directory not found: {uploads_dir}",
                "records": [],
            }

        active_dir = uploads_dir / "active"
        pdf_files = sorted(
            [pdf_path for pdf_path in uploads_dir.glob("*.pdf") if pdf_path.is_file()]
            + [pdf_path for pdf_path in active_dir.glob("*.pdf") if active_dir.exists() and pdf_path.is_file()],
            key=lambda pdf_path: pdf_path.stat().st_mtime,
            reverse=True,
        )

        records: list[dict[str, Any]] = []
        for pdf_path in pdf_files:
            filename = pdf_path.name
            filename_metadata = extract_petition_metadata_from_filename(filename)
            case_number = filename_metadata.get("case_number") or extract_case_number_from_filename(filename)
            client_name = filename_metadata.get("client_name")
            ssn_last4 = filename_metadata.get("ssn_last4")
            court_region = filename_metadata.get("court_region")
            normalized_court_region = filename_metadata.get("normalized_court_region")
            text_excerpt = ""

            needs_text_fallback = include_pdf_text_fallback and PdfReader and (
                not case_number or not client_name or not ssn_last4
            )
            if needs_text_fallback:
                try:
                    reader = PdfReader(str(pdf_path))
                    text_excerpt = "\n".join((page.extract_text() or "") for page in reader.pages[:5])
                except Exception as pdf_error:
                    logger.warning("Failed to read PDF text from %s: %s", pdf_path, pdf_error)

            if text_excerpt:
                if not case_number:
                    case_match = CASE_NUMBER_REGEX.search(text_excerpt)
                    if case_match:
                        case_number = _canonicalize_case_number_match(case_match.group(0))

                if not client_name:
                    client_name = _extract_debtor_name_from_text(text_excerpt)
                if not ssn_last4:
                    ssn_last4 = _extract_ssn_last4_from_text(text_excerpt)

            records.append(
                {
                    "filename": filename,
                    "path": str(pdf_path),
                    "file_size": int(pdf_path.stat().st_size or 0),
                    "case_number": case_number,
                    "normalized_case_number": normalize_case_value(case_number or ""),
                    "client_name": client_name,
                    "normalized_client_name": normalize_client_name(client_name or ""),
                    "ssn_last4": ssn_last4,
                    "court_region": court_region,
                    "normalized_court_region": normalized_court_region,
                }
            )

        return {
            "status": "completed",
            "uploads_dir": str(uploads_dir),
            "total_files": len(pdf_files),
            "records": records,
        }
    except Exception as e:
        return {"status": "failed", "error": str(e), "records": []}




def extract_debtor_name_for_session(session_id: str) -> dict:
    """
    Use a minimal agent powered by context_tool to return ONLY the debtor name
    from the session's uploaded PDFs. The result is a dict with status and debtor_name.
    """
    try:
        agent = DebtorNameAgent(session_id=session_id)
        result = agent.extract_debtor_name()
        return result
    except Exception as e:
        return {"status": "failed", "error": str(e)}

def _debtor_name_is_suspicious(name: str) -> bool:
    """
    Return True when a regex-extracted debtor name is clearly not a real person's
    name and should be discarded so the AI fallback can run.

    Two failure modes seen in the wild:
    1. Form section title — e.g. "Part 3: Report About Any Businesses You Own as a Sole Proprie"
       (more than 5 words)
    2. Acronym field label — e.g. "EIN EIN"
       (every word is all-uppercase AND ≤ 4 characters)
    """
    if not name:
        return False
    words = [w for w in name.split() if re.search(r"[A-Za-z]", w)]
    if len(words) > 5:
        return True
    if words and all(w.isupper() and len(w) <= 4 for w in words):
        return True
    return False


def extract_debtor_name_from_pdf_via_session_extractor(pdf_path: str, session_id: str | None = None) -> dict:
    """
    Extract debtor/client name directly from a PDF path using the same text parsing
    logic used by session-level PDF identity extraction.

    If regex extraction returns a suspicious result (form section title or acronym),
    and session_id is provided, falls back to extract_debtor_name_for_session which
    uses DebtorNameAgent to search the already-ingested vectorstore.
    """
    try:
        if not pdf_path:
            return {"status": "failed", "error": "pdf_path is required"}

        try:
            from pypdf import PdfReader
        except Exception:
            return {"status": "failed", "error": "pypdf not available"}

        path_obj = Path(pdf_path)
        if not path_obj.exists() or not path_obj.is_file():
            return {"status": "failed", "error": f"PDF not found: {pdf_path}"}

        reader = PdfReader(str(path_obj))
        text_excerpt = "\n".join((page.extract_text() or "") for page in reader.pages[:5])
        debtor_name = _extract_debtor_name_from_text(text_excerpt)

        if debtor_name and _debtor_name_is_suspicious(debtor_name):
            logger.debug("Regex debtor name discarded (suspicious): '%s'", debtor_name)
            debtor_name = None

        if not debtor_name:
            if session_id:
                logger.debug("Falling back to AI debtor extraction for session %s", session_id)
                return extract_debtor_name_for_session(session_id)
            return {"status": "failed", "error": "Debtor name not found"}

        return {"status": "completed", "debtor_name": debtor_name}
    except Exception as e:
        return {"status": "failed", "error": str(e)}

def _extract_case_number_from_pdf_directly(session_id: str) -> dict:
    """
    Extract case number directly from uploaded petition PDFs using pypdf + regex.
    This bypasses the vectorstore entirely for reliable extraction of case numbers
    that may not rank highly in semantic search results (e.g. header text).
    """
    try:
        try:
            from pypdf import PdfReader
        except Exception:
            return {"status": "failed", "error": "pypdf not available"}

        uploads_dir = Path(__file__).resolve().parent.parent.parent / "uploads"
        candidates = []

        # Primary path: resolve file paths from active PDF metadata for this session.
        try:
            sync_database_url = settings.CHAT_DATABASE_URL.replace("+asyncpg", "+psycopg")
            engine = create_engine(sync_database_url, pool_pre_ping=True)
            try:
                with engine.connect() as connection:
                    result = connection.execute(
                        sql_text(
                            """
                            SELECT file_path
                            FROM pdf_documents
                            WHERE session_id = :session_id AND is_active = true
                            ORDER BY uploaded_at DESC
                            """
                        ),
                        {"session_id": session_id},
                    )
                    for row in result.fetchall():
                        file_path = (row._mapping.get("file_path") or "").strip()
                        if not file_path:
                            continue
                        path_obj = Path(file_path)
                        if path_obj.exists() and path_obj.is_file():
                            candidates.append(path_obj)
            finally:
                engine.dispose()
        except Exception as db_error:
            logger.warning("Failed to load session PDF paths from DB for %s: %s", session_id, db_error)

        # Backward-compatible fallback: filename patterns containing session_id.
        if not candidates and uploads_dir.exists():
            for pattern in [
                f"bankruptcy_petition_{session_id}.pdf",
                f"petition_{session_id}.pdf",
                f"*{session_id}*.pdf",
            ]:
                candidates.extend(uploads_dir.glob(pattern))

        candidates = sorted(
            {p.resolve() for p in candidates if p.is_file()},
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            return {"status": "failed", "error": f"No PDF files found for session {session_id}"}

        for pdf_path in candidates:
            try:
                reader = PdfReader(str(pdf_path))
                # Read first 5 pages — case number is typically on page 1
                text = "\n".join((page.extract_text() or "") for page in reader.pages[:5])
                if not text:
                    continue

                case_match = CASE_NUMBER_REGEX.search(text)
                if case_match:
                    case_number = normalize_to_short_case_number(case_match.group(0))
                    if case_number:
                        return {"status": "completed", "case_number": case_number}
            except Exception as pdf_error:
                logger.warning("Failed case number extraction from %s: %s", pdf_path, pdf_error)
                continue

        return {"status": "failed", "error": "Case number not found in uploaded PDFs"}
    except Exception as e:
        return {"status": "failed", "error": str(e)}


def extract_case_number_for_session(session_id: str) -> dict:
    """
    Extract the case number from the session's uploaded PDFs.
    Uses direct PDF text extraction (pypdf + regex) first for reliability,
    then falls back to CaseNumberAgent (vectorstore + AI) if needed.
    """
    # Primary: direct PDF regex extraction (fast and reliable)
    direct_result = _extract_case_number_from_pdf_directly(session_id)
    if direct_result.get("status") == "completed" and direct_result.get("case_number"):
        case_number = direct_result["case_number"].strip()
        if case_number and case_number != "N/A":
            logger.debug("Case number extracted directly from PDF: %s", case_number)
            return direct_result

    # Fallback: AI agent via vectorstore search
    try:
        agent = CaseNumberAgent(session_id=session_id)
        result = agent.extract_case_number()
        return result
    except Exception as e:
        return {"status": "failed", "error": str(e)}

def extract_ssn_from_uploaded_petition_pdfs(session_id: str) -> dict:
    """
    Extract SSN last 4 directly from uploaded petition PDFs for a session.
    This does not rely on any AI agent classes.
    """
    try:
        try:
            from pypdf import PdfReader
        except Exception:
            return {"status": "failed", "error": "pypdf not available"}

        uploads_dir = Path(__file__).resolve().parent.parent.parent / "uploads"
        if not uploads_dir.exists():
            return {"status": "failed", "error": f"Uploads directory not found: {uploads_dir}"}

        candidates = []

        # Primary path: resolve file paths from active PDF metadata for this session.
        try:
            sync_database_url = settings.CHAT_DATABASE_URL.replace("+asyncpg", "+psycopg")
            engine = create_engine(sync_database_url, pool_pre_ping=True)
            try:
                with engine.connect() as connection:
                    result = connection.execute(
                        sql_text(
                            """
                            SELECT file_path
                            FROM pdf_documents
                            WHERE session_id = :session_id AND is_active = true
                            ORDER BY uploaded_at DESC
                            """
                        ),
                        {"session_id": session_id},
                    )
                    for row in result.fetchall():
                        file_path = (row._mapping.get("file_path") or "").strip()
                        if not file_path:
                            continue
                        path_obj = Path(file_path)
                        if path_obj.exists() and path_obj.is_file():
                            candidates.append(path_obj)
            finally:
                engine.dispose()
        except Exception as db_error:
            logger.warning("Failed to load session PDF paths from DB for %s: %s", session_id, db_error)

        # Backward-compatible fallback: filename patterns containing session_id.
        if not candidates:
            candidate_patterns = [
                f"bankruptcy_petition_{session_id}.pdf",
                f"petition_{session_id}.pdf",
                f"*{session_id}*.pdf",
            ]
            for pattern in candidate_patterns:
                candidates.extend(uploads_dir.glob(pattern))

        # Deduplicate and prioritize newest files first.
        candidates = sorted(
            {p.resolve() for p in candidates if p.is_file()},
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            return {"status": "failed", "error": f"No PDF files found for session {session_id}"}

        # Supports masked SSN formats such as xxx-xx-1234 and xxx – xx – 1 2 3 4.
        ssn_pattern = re.compile(r"[xX*]{3}\s*[-–]\s*[xX*]{2}\s*[-–]\s*(\d(?:\s*\d){3})")

        for pdf_path in candidates:
            try:
                reader = PdfReader(str(pdf_path))
                full_text = "\n".join((page.extract_text() or "") for page in reader.pages)
                match = ssn_pattern.search(full_text)
                if not match:
                    continue

                digits = re.sub(r"\D", "", match.group(1))
                if len(digits) == 4:
                    return {"status": "completed", "ssn_last4": digits}
            except Exception as pdf_error:
                logger.warning("Failed SSN extraction from %s: %s", pdf_path, pdf_error)
                continue

        return {"status": "failed", "error": "SSN last 4 not found in uploaded PDFs"}
    except Exception as e:
        return {"status": "failed", "error": str(e)}

def extract_ssn_for_session(session_id: str) -> dict:
    """
    Use SSNAgent to return ONLY the last 4 digits of the Social Security Number
    from the session's uploaded PDFs. The result is a dict with status and ssn_last4.
    """
    try:
        # Primary path: use SSNAgent when available.
        try:
            from ..chatbot.agent import SSNAgent

            agent = SSNAgent(session_id=session_id)
            result = agent.extract_ssn()
            if result.get("status") == "completed" and result.get("ssn_last4"):
                return result
        except Exception as agent_error:
            logger.warning("SSNAgent unavailable/failed for session %s: %s", session_id, agent_error)

        # Fallback path: direct extraction from uploaded petition PDFs.
        return extract_ssn_from_uploaded_petition_pdfs(session_id)
    except Exception as e:
        return {"status": "failed", "error": str(e)}

