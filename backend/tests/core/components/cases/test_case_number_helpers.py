"""Tests for _normalize_case_number and _sanitize_case_id — pure regex logic."""

import pytest
from fastapi import HTTPException

from src.core.components.cases.service import _normalize_case_number, _sanitize_case_id


# ─── _normalize_case_number ───────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw, expected",
    [
        # _CASE_WITH_CHAPTER branch (leading chapter digit)
        ("0:26-bk-10700", "26-10700"),
        ("1:25-bk-15244-KKS", "25-15244"),
        ("0 26 bk 10700", "26-10700"),
        # _CASE_BK branch
        ("26-bk-11993", "26-11993"),
        ("26 bk 11993", "26-11993"),
        ("25-bk-14567-ABC", "25-14567"),
        # _CASE_SHORT branch
        ("26-10700", "26-10700"),
        ("25-31154-KKS", "25-31154"),
        ("25_31154", "25-31154"),
    ],
)
def test_normalize_case_number_accepts_known_formats(raw, expected):
    assert _normalize_case_number(raw) == expected


@pytest.mark.unit
def test_normalize_case_number_strips_surrounding_whitespace():
    assert _normalize_case_number("  26-10700  ") == "26-10700"


@pytest.mark.unit
@pytest.mark.parametrize(
    "bad",
    [
        "",
        "not a case number",
        "12345",            # too short
        "abc-def-ghi",      # no digits
        "26/10700",         # unsupported separator
    ],
)
def test_normalize_case_number_rejects_unknown_formats(bad):
    with pytest.raises(HTTPException) as exc:
        _normalize_case_number(bad)
    assert exc.value.status_code == 422
    assert "Could not normalize case number" in exc.value.detail


# ─── _sanitize_case_id ─────────────────────────────────────────────────


@pytest.mark.unit
def test_sanitize_case_id_converts_dash_to_underscore():
    assert _sanitize_case_id("26-10700") == "26_10700"


@pytest.mark.unit
def test_sanitize_case_id_lowercases():
    assert _sanitize_case_id("25-31154-KKS") == "25_31154_kks"


@pytest.mark.unit
def test_sanitize_case_id_collapses_runs_of_non_alnum():
    assert _sanitize_case_id("26--10700") == "26_10700"


@pytest.mark.unit
def test_sanitize_case_id_strips_leading_trailing_underscores():
    assert _sanitize_case_id("-26-10700-") == "26_10700"


@pytest.mark.unit
def test_sanitize_case_id_rejects_empty_result():
    with pytest.raises(HTTPException) as exc:
        _sanitize_case_id("---")
    assert exc.value.status_code == 422
    assert "Could not derive case_id" in exc.value.detail
