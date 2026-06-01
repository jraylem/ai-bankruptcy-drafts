import asyncio
import base64
import logging
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urljoin

logger = logging.getLogger(__name__)

DISTRICT_SLUGS = {
    "southern": "flsbke",
    "middle": "flmbke",
    "northern": "flnbke",
}
DEFAULT_DISTRICT_ORDER = ["southern", "middle", "northern"]

# Uploads folder is at the project root (3 levels up from src/courtdrive/)
UPLOADS_DIR = Path(__file__).parent.parent.parent / "uploads"

VOLUNTARY_PETITION_SENDERS = [
    "BKECF@flnb.uscourts.gov",
    "FLSB_ECF_Notification@flsb.uscourts.gov",
    "bnc@flmb.uscourts.gov",
    "Courtmail@pawb.uscourts.gov",
]

# ECF notification senders only (excludes BNC) — used for petition link extraction
# with subject filter to ensure we only get the actual Voluntary Petition document link
ECF_PETITION_SENDERS = [
    "BKECF@flnb.uscourts.gov",
    "FLSB_ECF_Notification@flsb.uscourts.gov",
    "Courtmail@pawb.uscourts.gov",
    "bnc@flmb.uscourts.gov",
    "nickf@cvhlawgroup.com"
]


class PetitionNotFoundError(Exception):
    """Raised when a petition PDF cannot be located, with a specific reason."""

    def __init__(self, message: str, reason: str):
        # reason: "link_expired" | "not_found"
        super().__init__(message)
        self.reason = reason


class PetitionAvailableForDownload(Exception):
    """Raised when a petition download link is found in a court notification email but not yet downloaded."""

    def __init__(self, case_number: str):
        super().__init__(f"Petition available for download from court notification for case {case_number}")
        self.case_number = case_number


def _build_petition_case_variants(case_number: str) -> list[str]:
    """Return case number variants for Gmail search matching."""
    raw = (case_number or "").strip()
    if not raw:
        return []

    variants: list[str] = [raw]

    # X:YY-bk-ZZZZZ -> YY-ZZZZZ (e.g. 6:26-bk-01903 -> 26-01903)
    match = re.fullmatch(r"(\d):([0-9]{2})-bk-([0-9]{5})", raw, flags=re.IGNORECASE)
    if match:
        _, yy, serial = match.groups()
        variants.append(f"{yy}-{serial}")

    # YY-ZZZZZ -> also add with leading digit prefix if missing
    match2 = re.fullmatch(r"([0-9]{2})-([0-9]{5})(?:-[A-Za-z]{3})?", raw)
    if match2:
        yy, serial = match2.group(1), match2.group(2)
        variants.append(f"{yy}-{serial}")

    # Deduplicate preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for v in variants:
        if v.lower() not in seen:
            seen.add(v.lower())
            deduped.append(v)
    return deduped


def _decode_email_body(payload: dict) -> str:
    """Decode Gmail message payload to get HTML or plain-text body."""
    body = ""
    if "parts" in payload:
        for part in payload["parts"]:
            if part["mimeType"] == "text/html":
                if "data" in part.get("body", {}):
                    body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                    break
            elif part["mimeType"] == "text/plain" and not body:
                if "data" in part.get("body", {}):
                    body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
    else:
        if "body" in payload and "data" in payload["body"]:
            body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
    return body


def _extract_debtor_name_from_text(text: str) -> str:
    """Extract debtor name from petition PDF text."""
    # Pattern 1: "In re" followed by name
    match = re.search(
        r'(?i)\bIn\s+re[:\s]+([A-Za-z][A-Za-z\s,\.\'-]{1,50}?)(?=\s*\n|\s{2,}|,?\s*(?:aka|also known|Case\s*No|Debtor|$))',
        text,
    )
    if match:
        name = match.group(1).strip().strip(",").strip()
        if 2 < len(name) < 60:
            return name

    # Pattern 2: "Debtor 1" or "Debtor:" label followed by name
    match = re.search(
        r'(?i)Debtor\s*1?\s*[:\-]?\s*([A-Z][a-zA-Z\s,\.\'-]{2,50}?)(?=\n|$)',
        text,
    )
    if match:
        name = match.group(1).strip()
        if 2 < len(name) < 60:
            return name

    return ""


def _infer_district_from_url(url: str) -> str:
    """Infer court district code from a PACER ECF URL."""
    host = urlparse(url).netloc.lower()
    if "flsb" in host:
        return "FLSB"
    if "flmb" in host:
        return "FLMB"
    if "flnb" in host:
        return "FLNB"
    if "pawb" in host:
        return "PAWB"
    return ""


def _extract_ecf_links_from_body(html: str) -> list[str]:
    """Extract PACER ECF document links from email body HTML using regex."""
    return re.findall(r'href=["\']?(https://[^\s"\'<>]*uscourts\.gov/doc1/[^\s"\'<>]*)["\']?', html)


def _extract_petition_links_from_email(case_number: str) -> tuple[list[str], bool]:
    """
    Search Gmail for court notification emails for this case number and extract ECF document links.

    Returns:
        (links, email_found): links is list of ECF document URLs found in matching emails;
        email_found indicates whether any matching email exists at all (used to distinguish
        link_expired vs not_found when links list is empty).
    """
    try:
        from ..gmail.auth import get_gmail_service

        service = get_gmail_service()
        variants = _build_petition_case_variants(case_number)
        if not variants:
            logger.debug("Gmail check: no case variants generated for '%s'", case_number)
            return [], False

        sender_clause = " OR ".join(f"from:{s}" for s in ECF_PETITION_SENDERS)
        case_clause = " OR ".join(f'"{v}"' for v in variants)
        query = f'({sender_clause}) subject:"Voluntary Petition" ({case_clause})'

        logger.debug("Gmail petition link search query: %s", query)

        result = service.users().messages().list(userId="me", q=query, maxResults=5).execute()
        messages = result.get("messages", [])
        if not messages:
            logger.debug("No Gmail emails found for '%s'", case_number)
            return [], False

        logger.info("Found %d email(s) for '%s', extracting links...", len(messages), case_number)
        all_links: list[str] = []

        for msg_ref in messages:
            try:
                msg = service.users().messages().get(userId="me", id=msg_ref["id"], format="full").execute()
                body = _decode_email_body(msg["payload"])
                links = _extract_ecf_links_from_body(body)
                all_links.extend(links)
            except Exception as e:
                logger.warning("Error reading message %s: %s", msg_ref["id"], e)

        # Deduplicate preserving order
        seen: set[str] = set()
        deduped: list[str] = []
        for link in all_links:
            if link not in seen:
                seen.add(link)
                deduped.append(link)

        logger.info("Extracted %d ECF link(s) for '%s'", len(deduped), case_number)
        return deduped, True

    except Exception as e:
        logger.exception("Gmail link extraction error for '%s': %s", case_number, e)
        return [], False


def parse_petition_filename(filename: str) -> dict:
    """
    Parse CASE_NAME, CASE_NUMBER, and SS_NUMBER from a petition PDF filename.

    Filename convention:
        Bankruptcy_Petition_<CASE_NAME>_<CASE_NUMBER>_SS_<SS_NUMBER>.pdf

    Supported CASE_NUMBER formats (as they appear in the filename):
        3_26-bk-00635   → denormalized to 3:26-bk-00635
        26-11929
        25-31154-KKS

    Returns:
        dict with keys: case_name (str), case_number (str), ss_number (str), district (str)
        All values are empty strings if parsing fails.
    """
    stem = Path(filename).stem  # strip .pdf

    prefix = "Bankruptcy_Petition_"
    if not stem.startswith(prefix):
        return {"case_name": "", "case_number": "", "ss_number": "", "district": ""}

    remainder = stem[len(prefix):]  # e.g. Kim_T_Brown_3_26-bk-00635_SS_7978_FLSB

    # Strip _SS_<number> and optional _<DISTRICT> from the end
    ss_match = re.search(r"_SS_(\d+)(?:_([A-Z]{2,5}))?$", remainder)
    ss_number = ss_match.group(1) if ss_match else ""
    district = ss_match.group(2) if ss_match and ss_match.group(2) else ""
    if ss_match:
        remainder = remainder[:ss_match.start()]  # e.g. Kim_T_Brown_3_26-bk-00635

    # Match case number patterns (order matters: most specific first)
    case_number_pattern = re.search(
        r"(\d_\d{2}-bk-\d+|\d{2}-\d+-[A-Za-z]{3}|\d{2}-\d+)$",
        remainder
    )

    if not case_number_pattern:
        return {"case_name": remainder.replace("_", " ").strip(), "case_number": "", "ss_number": ss_number, "district": district}

    raw_case_number = case_number_pattern.group(1)
    case_name_raw = remainder[:case_number_pattern.start()].rstrip("_")

    from .service import normalize_to_short_case_number

    # Normalize case number to XX-XXXXX format
    denormalized = re.sub(r"^(\d)_(\d{2}-bk-)", r"\1:\2", raw_case_number)
    case_number_val = normalize_to_short_case_number(denormalized)

    case_name = case_name_raw.replace("_", " ").strip()

    return {"case_name": case_name, "case_number": case_number_val, "ss_number": ss_number, "district": district}


async def extract_petition_pdf(
    case_number: str,
    district: Optional[str] = None,
) -> Path:
    """
    Locate a Voluntary Petition PDF in the uploads folder by case number.

    PDF files follow the naming convention:
        Bankruptcy_Petition_<CASE_NAME>_<CASE_NUMBER>_SS_<SS_NUMBER>.pdf

    Supported case number formats:
        x:xx-bk-xxxxx  e.g. 3:26-bk-00635  (stored in filename as 3_26-bk-00635)
        xx-xxxxx        e.g. 26-11993
        xx-xxxxx-[AAA]  e.g. 25-31154-KKS

    Args:
        case_number: The bankruptcy case number to search for.
        district: Kept for backwards compatibility, not used.
        output_path: If provided, the matched PDF is copied here and that path is returned.
                     If None, the original file path in uploads is returned directly.

    Returns:
        Path to the petition PDF.

    Raises:
        FileNotFoundError: If no matching PDF is found in the uploads folder.
    """
    # Backwards compatibility: callers might still pass output_path as second positional argument
    if district is not None and not isinstance(district, str):
        district = None

    from .service import normalize_to_short_case_number

    normalized = normalize_to_short_case_number(case_number)

    # Step 1: Check uploads/ root and uploads/active/ for previously downloaded files.
    for search_dir in (UPLOADS_DIR, UPLOADS_DIR / "active"):
        for pdf_file in search_dir.glob("Bankruptcy_Petition_*.pdf"):
            parsed = parse_petition_filename(pdf_file.name)
            if parsed.get("case_number") and normalize_to_short_case_number(parsed["case_number"]) == normalized:
                logger.info("Found in %s/: %s", search_dir.name, pdf_file.name)
                return pdf_file

    # Step 2: Download from Google Drive
    logger.info("Not found locally, retrieving petition from Google Drive for '%s'", case_number)
    try:
        from ..gmail.drive_service import retrieve_petition_from_drive
        drive_path = retrieve_petition_from_drive(case_number)
        if drive_path and drive_path.exists():
            logger.info("Retrieved from Drive: %s", drive_path.name)
            return drive_path
    except Exception as e:
        logger.warning("Drive retrieval error: %s", e)

    # Step 3: Check Gmail for a court notification email for this case number.
    # If a downloadable link is found, surface it to the user for confirmation.
    # If an email exists but no link, the link was already consumed. If no email,
    # the petition was never received.
    links, email_found = _extract_petition_links_from_email(case_number)
    if links:
        raise PetitionAvailableForDownload(case_number)
    if email_found:
        raise PetitionNotFoundError(
            f"We found a court notification for case {case_number}, "
            "but the file is no longer available for download. "
            "The download link may have already been used. Please contact your administrator.",
            reason="link_expired",
        )
    raise PetitionNotFoundError(
        f"No petition file was found for case {case_number}. "
        "Please check the case number and try again.",
        reason="not_found",
    )


async def download_petition_from_email(case_number: str) -> Path:
    """
    Attempt to download a Voluntary Petition PDF from a court notification email.

    Searches Gmail for ECF document links for this case, then downloads the PDF,
    extracts the SSN last four, and saves the file to uploads/ using the standard
    naming convention.

    Returns:
        Path to the saved petition PDF.

    Raises:
        PetitionNotFoundError: If no links are found or all download attempts fail.
    """
    from pypdf import PdfReader

    links, email_found = _extract_petition_links_from_email(case_number)
    if not links:
        if email_found:
            raise PetitionNotFoundError(
                f"The petition file for case {case_number} was received but the download link has expired.",
                reason="link_expired",
            )
        raise PetitionNotFoundError(
            f"No petition file was found for case {case_number}. "
            "Please check the case number and try again.",
            reason="not_found",
        )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/pdf,*/*",
    }

    for link in links:
        try:
            logger.info("Attempting petition download: %s", link)
            req = urllib.request.Request(link, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as response:
                content_type = response.headers.get("Content-Type", "")
                content = response.read()

            if "pdf" in content_type.lower() or content.startswith(b"%PDF"):
                pdf_bytes = content
            else:
                # HTML viewer page — extract embedded PDF URL
                html_text = content.decode("utf-8", errors="replace")
                pdf_url_match = re.search(
                    r'(?:src|href)=["\']?(https://[^\s"\'<>]*uscourts\.gov/doc1/[^\s"\'<>]*)["\']?',
                    html_text,
                )
                if not pdf_url_match:
                    pdf_url_match = re.search(
                        r'(?:src|data)=["\']?([^\s"\'<>]+\.pdf[^\s"\'<>]*)["\']?', html_text, re.I
                    )
                if not pdf_url_match:
                    logger.warning("No embedded PDF URL found in viewer page for: %s", link)
                    continue
                pdf_url = pdf_url_match.group(1)
                if not pdf_url.startswith("http"):
                    parsed = urlparse(link)
                    base_url = f"{parsed.scheme}://{parsed.netloc}"
                    pdf_url = urljoin(base_url, pdf_url)
                logger.info("HTML viewer detected, fetching PDF from: %s", pdf_url)
                req2 = urllib.request.Request(pdf_url, headers=headers)
                with urllib.request.urlopen(req2, timeout=60) as resp2:
                    pdf_bytes = resp2.read()

            if not pdf_bytes.startswith(b"%PDF"):
                logger.warning("Response was not a valid PDF for: %s", link)
                continue

            # Extract SSN, debtor name from PDF
            ssn = "0000"
            debtor_name = ""
            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                    tmp.write(pdf_bytes)
                    tmp_path = tmp.name
                reader = PdfReader(tmp_path)
                text = "".join(page.extract_text() or "" for page in reader.pages)
                ssn_match = re.search(r'\b\d{3}-\d{2}-(\d{4})\b', text)
                if ssn_match:
                    ssn = ssn_match.group(1)
                debtor_name = _extract_debtor_name_from_text(text)
            except Exception as e:
                logger.warning("PDF extraction failed: %s", e)
            finally:
                if tmp_path:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass

            district = _infer_district_from_url(link)
            safe_case = case_number.replace(":", "_")
            safe_name = re.sub(r"[^\w\s-]", "", debtor_name).replace(" ", "_").strip("_") if debtor_name else ""
            name_part = f"{safe_name}_" if safe_name else ""
            district_part = f"_{district}" if district else ""
            filename = f"Bankruptcy_Petition_{name_part}{safe_case}_SS_{ssn}{district_part}.pdf"
            output_path = UPLOADS_DIR / filename
            output_path.write_bytes(pdf_bytes)
            logger.info("Saved petition from email: %s", output_path)
            return output_path

        except urllib.error.HTTPError as e:
            logger.warning("HTTP %s downloading %s: %s", e.code, link, e.reason)
        except Exception as e:
            logger.warning("Error downloading %s: %s", link, e)

    raise PetitionNotFoundError(
        f"We found a court notification for case {case_number}, "
        "but the download link has already been used and the file could not be retrieved.",
        reason="link_expired",
    )


async def run(case_number: str, district: Optional[str] = None):
    """Command-line wrapper for extract_petition_pdf."""
    output_path = await extract_petition_pdf(case_number, district=district)
    print(f"PDF path: {output_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python petition_extractor.py <CASE_NUMBER>")
    else:
        asyncio.run(run(sys.argv[1]))
