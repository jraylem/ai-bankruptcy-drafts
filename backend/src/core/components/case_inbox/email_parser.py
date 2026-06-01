"""PACER ECF notice email parser.

Ported from `ecf-petition-downloader/src/email_parser.py`. Three pure
functions extract:
  - extract_ecf_links(html)   → PACER doc URLs from the "Document Number"
                                  row of the notice table
  - extract_case_name(html)   → debtor name from "Case Name:" sibling td
  - extract_case_number(html) → case number from "Case Number:" sibling td

All functions tolerate non-HTML / malformed bodies — return "" / [] on
miss rather than raising. The ingest orchestrator handles the "missing
data" case downstream.

Why a precise BS4 table-row match (rather than a regex sweep across the
entire email body)? PACER notices include MANY uscourts.gov links —
amendments, related filings, ToS, etc. Only the one in the Document
Number row is the original petition we want to fetch.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup


def extract_ecf_links(html_content: str) -> list[str]:
    """Find the petition's PACER doc-1 URL in the notice email.

    Targets the canonical PACER notice table:
        <tr>
          <td><strong>Document Number:</strong></td>
          <td><a href="https://ecf...doc1/...">1</a></td>
        </tr>

    Walks every `<td>` with text matching "Document Number", grabs the
    next-sibling `<td>`, returns its anchor's href. Dedups while
    preserving order via `dict.fromkeys`.
    """
    doc_links: list[str] = []
    if not html_content:
        return doc_links
    soup = BeautifulSoup(html_content, "html.parser")

    for td in soup.find_all("td"):
        if re.search(r"Document Number", td.get_text(), re.I):
            next_td = td.find_next_sibling("td")
            if next_td:
                anchor = next_td.find("a", href=True)
                if anchor and anchor.get("href", "").startswith("http"):
                    doc_links.append(anchor["href"])

    return list(dict.fromkeys(doc_links))


def extract_case_name(html_content: str) -> str:
    """Debtor name from the 'Case Name:' field. Returns "" on miss."""
    if not html_content:
        return ""
    soup = BeautifulSoup(html_content, "html.parser")

    # HTML table layout: <td>Case Name:</td><td>Nicholas Earl Sampson</td>
    for text_node in soup.find_all(string=re.compile(r"Case Name", re.I)):
        parent = text_node.parent
        next_td = parent.find_next_sibling()
        if next_td and next_td.get_text(strip=True):
            return next_td.get_text(strip=True)
        # Inline layout: name follows in the same element after a tab/colon
        full_text = parent.get_text()
        match = re.search(r"Case Name[:\s\t]+(.+)", full_text, re.I)
        if match:
            return match.group(1).strip()

    # Plain-text fallback (tab-separated body)
    plain = soup.get_text()
    match = re.search(r"Case Name[:\s\t]+(.+)", plain, re.I)
    if match:
        return match.group(1).strip()
    return ""


def extract_case_number(html_content: str) -> str:
    """Case number from the 'Case Number:' field. Returns "" on miss."""
    if not html_content:
        return ""
    soup = BeautifulSoup(html_content, "html.parser")

    for text_node in soup.find_all(string=re.compile(r"Case Number", re.I)):
        parent = text_node.parent
        next_td = parent.find_next_sibling()
        if next_td and next_td.get_text(strip=True):
            return next_td.get_text(strip=True)
        full_text = parent.get_text()
        match = re.search(r"Case Number[:\s\t]+(.+)", full_text, re.I)
        if match:
            return match.group(1).strip()

    plain = soup.get_text()
    match = re.search(r"Case Number[:\s\t]+(.+)", plain, re.I)
    if match:
        return match.group(1).strip()
    return ""


def extract_sender_email(from_header: str) -> str:
    """`Foo Bar <user@x.com>` → `user@x.com`. Returns input as-is on miss."""
    if not from_header:
        return ""
    match = re.search(r"[\w.+-]+@[\w.-]+\.\w+", from_header)
    return match.group(0) if match else from_header
