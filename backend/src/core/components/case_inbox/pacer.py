"""PACER PDF downloader (async, in-memory only).

Ported from `ecf-petition-downloader/src/pacer_downloader.py:download_document`,
with two changes:
  1. httpx.AsyncClient instead of `requests`
  2. Returns `bytes | None` instead of writing to disk

The 2-GET dance is unchanged:
  - GET #1 fetches the ECF link. If response is PDF (Content-Type OR
    `%PDF` magic bytes), return content.
  - Otherwise treat the response as the HTML viewer page; locate the
    embedded PDF URL via `find_pdf_url_in_html`; GET #2 fetches it.

Returns `None` on:
  - Network/HTTP error
  - HTML response with no embeddable PDF URL (dead link, paywall, etc.)
  - Second GET errors
"""

from __future__ import annotations

import logging
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Chrome UA + Accept header — PACER blocks requests with default
# `python-httpx/*` user-agents.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/pdf,*/*",
}


def find_pdf_url_in_html(html: str, base_url: str) -> str | None:
    """Locate the embedded PDF URL inside a PACER HTML viewer page.

    Priority chain:
      1. <iframe|embed|object> src/data
      2. <a href> matching uscourts.gov/doc1/
      3. <a href> ending in .pdf

    Relative URLs are resolved against base_url via urljoin.
    """
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup.find_all(["iframe", "embed", "object"]):
        src = tag.get("src") or tag.get("data", "")
        if src:
            return urljoin(base_url, src)

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "uscourts.gov" in href and "/doc1/" in href:
            return urljoin(base_url, href)
        if href.lower().endswith(".pdf"):
            return urljoin(base_url, href)

    return None


async def download_document(url: str, *, timeout: float = 60.0) -> bytes | None:
    """Fetch a PACER ECF document; return PDF bytes or None.

    Streams in memory only — never writes to disk. Caller hashes /
    uploads / parses the bytes.

    The PACER "free look" link is valid for ~1 minute. Calling this
    consumes the link; subsequent fetches return the paywall page,
    which `find_pdf_url_in_html` will fail to extract a PDF from →
    function returns None.
    """
    try:
        async with httpx.AsyncClient(
            headers=HEADERS, timeout=timeout, follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "").lower()
            # Two-pronged sniff: header OR magic bytes. Some PACER deployments
            # serve PDFs with application/octet-stream.
            if "pdf" in content_type or resp.content.startswith(b"%PDF"):
                return resp.content

            # HTML viewer fallback — find embedded PDF URL + fetch again.
            logger.info("PACER viewer page; looking for embedded PDF URL")
            pdf_url = find_pdf_url_in_html(resp.text, str(resp.url))
            if not pdf_url:
                logger.info("No embedded PDF URL — link likely dead or paywalled")
                return None
            pdf_resp = await client.get(pdf_url)
            pdf_resp.raise_for_status()
            # Sanity-check the second response — same content-type/magic logic.
            ct2 = pdf_resp.headers.get("Content-Type", "").lower()
            if "pdf" in ct2 or pdf_resp.content.startswith(b"%PDF"):
                return pdf_resp.content
            logger.info("Second GET returned non-PDF; treating as dead link")
            return None
    except httpx.HTTPError as e:
        logger.warning("PACER fetch failed: %s", e)
        return None
