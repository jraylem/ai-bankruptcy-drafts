"""BS4-based extraction of case name / number / doc links from PACER notices."""

from __future__ import annotations

import pytest

from src.core.components.case_inbox import email_parser

_PACER_NOTICE_HTML = """
<html><body>
  <table>
    <tr>
      <td>Case Name:</td>
      <td>Nicholas Earl Sampson</td>
    </tr>
    <tr>
      <td>Case Number:</td>
      <td>8:26-bk-01330</td>
    </tr>
    <tr>
      <td><strong>Document Number:</strong></td>
      <td><a href="https://ecf.flsb.uscourts.gov/doc1/123456789">1</a></td>
    </tr>
    <tr>
      <td>Some other link:</td>
      <td><a href="https://ecf.flsb.uscourts.gov/doc1/SHOULD_NOT_MATCH">amended</a></td>
    </tr>
  </table>
</body></html>
"""


@pytest.mark.unit
def test_extract_ecf_links_targets_document_number_row_only():
    """Verifies the BS4 sibling-td traversal picks up ONLY the Document
    Number row's anchor — not every uscourts.gov/doc1/ link in the body."""
    links = email_parser.extract_ecf_links(_PACER_NOTICE_HTML)
    assert links == ["https://ecf.flsb.uscourts.gov/doc1/123456789"]


@pytest.mark.unit
def test_extract_case_name_from_sibling_td():
    assert email_parser.extract_case_name(_PACER_NOTICE_HTML) == "Nicholas Earl Sampson"


@pytest.mark.unit
def test_extract_case_number_from_sibling_td():
    assert email_parser.extract_case_number(_PACER_NOTICE_HTML) == "8:26-bk-01330"


@pytest.mark.unit
def test_extract_case_name_plain_text_fallback():
    """When the HTML doesn't have the table layout, falls back to plain-text regex."""
    plain = "Case Name: Jane Q Debtor\nCase Number: 1:25-bk-15244"
    assert email_parser.extract_case_name(plain) == "Jane Q Debtor"
    assert email_parser.extract_case_number(plain) == "1:25-bk-15244"


@pytest.mark.unit
def test_extract_helpers_return_empty_on_missing_data():
    assert email_parser.extract_ecf_links("") == []
    assert email_parser.extract_case_name("") == ""
    assert email_parser.extract_case_number("") == ""
    assert email_parser.extract_ecf_links("<html></html>") == []


@pytest.mark.unit
def test_extract_ecf_links_dedups_preserving_order():
    """If a malformed email has the same link in multiple Document Number rows,
    we dedup but preserve insertion order."""
    html = """
      <table>
        <tr><td>Document Number:</td><td><a href="https://x.uscourts.gov/doc1/A">1</a></td></tr>
        <tr><td>Document Number:</td><td><a href="https://x.uscourts.gov/doc1/A">1</a></td></tr>
        <tr><td>Document Number:</td><td><a href="https://x.uscourts.gov/doc1/B">2</a></td></tr>
      </table>
    """
    assert email_parser.extract_ecf_links(html) == [
        "https://x.uscourts.gov/doc1/A",
        "https://x.uscourts.gov/doc1/B",
    ]


@pytest.mark.unit
def test_extract_sender_email_handles_display_name():
    assert email_parser.extract_sender_email("FLSB Court <BKECF@flsb.uscourts.gov>") == "BKECF@flsb.uscourts.gov"
    assert email_parser.extract_sender_email("plain@example.com") == "plain@example.com"
    assert email_parser.extract_sender_email("not-an-email") == "not-an-email"
    assert email_parser.extract_sender_email("") == ""
