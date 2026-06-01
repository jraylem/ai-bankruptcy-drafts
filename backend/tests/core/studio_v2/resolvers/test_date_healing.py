"""Tests for DateHealingResolverV2 — covers every supported input
format, the canonical-format passthrough, the empty-value passthrough,
and the note-annotation when a value is rewritten."""

import pytest

from src.core.studio_v2.resolvers.date_healing import (
    DEFAULT_DATE_FORMAT_V2,
    DateHealingResolverV2,
)
from src.core.studio_v2.types.resolution import ResolvedTemplateValueV2


@pytest.mark.unit
def test_default_format_is_firm_default():
    assert DEFAULT_DATE_FORMAT_V2 == "%B %-d, %Y"


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("01/21/2026", "January 21, 2026"),
        ("2026-01-21", "January 21, 2026"),
        ("2026/01/21", "January 21, 2026"),
        ("21-01-2026", "January 21, 2026"),
        ("January 21, 2026", "January 21, 2026"),  # canonical → passthrough
        ("Jan 21, 2026", "January 21, 2026"),
        ("21 January 2026", "January 21, 2026"),
        ("21 Jan 2026", "January 21, 2026"),
        ("01-21-2026", "January 21, 2026"),
    ],
)
def test_recognized_formats_normalize_to_canonical(raw, expected):
    rv = ResolvedTemplateValueV2(template_variable="x", value=raw)
    healed = DateHealingResolverV2.apply([rv])
    assert healed[0].value == expected


@pytest.mark.unit
def test_canonical_format_passes_through_unchanged():
    """If the value already renders identically to the canonical
    format, the resolver returns the SAME row (no note annotation)."""
    rv = ResolvedTemplateValueV2(
        template_variable="x", value="January 21, 2026", note="original note",
    )
    healed = DateHealingResolverV2.apply([rv])
    assert healed[0] is rv  # identity preserved
    assert healed[0].note == "original note"


@pytest.mark.unit
def test_non_date_values_pass_through_unchanged():
    rv = ResolvedTemplateValueV2(template_variable="x", value="Jane Doe")
    healed = DateHealingResolverV2.apply([rv])
    assert healed[0] is rv


@pytest.mark.unit
def test_empty_value_passes_through_unchanged():
    rv = ResolvedTemplateValueV2(template_variable="x", value="")
    healed = DateHealingResolverV2.apply([rv])
    assert healed[0] is rv


@pytest.mark.unit
def test_rewritten_value_appends_to_note():
    rv = ResolvedTemplateValueV2(
        template_variable="x", value="01/21/2026", note="existing note",
    )
    healed = DateHealingResolverV2.apply([rv])
    assert healed[0].value == "January 21, 2026"
    assert "existing note" in healed[0].note
    assert "date healed from '01/21/2026'" in healed[0].note


@pytest.mark.unit
def test_rewritten_value_starts_note_when_originally_empty():
    rv = ResolvedTemplateValueV2(
        template_variable="x", value="01/21/2026", note="",
    )
    healed = DateHealingResolverV2.apply([rv])
    assert healed[0].note == "date healed from '01/21/2026'"


@pytest.mark.unit
def test_mixed_list_only_dates_change():
    rows = [
        ResolvedTemplateValueV2(template_variable="a", value="01/21/2026"),
        ResolvedTemplateValueV2(template_variable="b", value="Jane Doe"),
        ResolvedTemplateValueV2(template_variable="c", value=""),
        ResolvedTemplateValueV2(template_variable="d", value="not a date 1/2/3/4"),
    ]
    healed = DateHealingResolverV2.apply(rows)
    assert healed[0].value == "January 21, 2026"
    assert healed[1].value == "Jane Doe"
    assert healed[2].value == ""
    assert healed[3].value == "not a date 1/2/3/4"


@pytest.mark.unit
def test_returns_new_list_not_mutating_original():
    rows = [ResolvedTemplateValueV2(template_variable="x", value="01/21/2026")]
    healed = DateHealingResolverV2.apply(rows)
    assert healed is not rows
    assert rows[0].value == "01/21/2026"  # original unchanged


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("on 3/20/2026", "on March 20, 2026"),
        ("Hearing scheduled for 3/20/2026 at 10am", "Hearing scheduled for March 20, 2026 at 10am"),
        ("Initial: 3/20/2026; Continued: 04-15-2026", "Initial: March 20, 2026; Continued: April 15, 2026"),
        ("April 30, 2026 and 5/1/2026", "April 30, 2026 and May 1, 2026"),
        ("Filed 2026-03-20.", "Filed March 20, 2026."),
    ],
)
def test_embedded_dates_normalize_inside_larger_strings(raw, expected):
    rv = ResolvedTemplateValueV2(template_variable="x", value=raw)
    healed = DateHealingResolverV2.apply([rv])[0]
    assert healed.value == expected
    assert "embedded date(s) healed" in healed.note


@pytest.mark.unit
def test_embedded_no_match_passes_through_unchanged():
    rv = ResolvedTemplateValueV2(
        template_variable="x",
        value="Lori Creswell and Robert Creswell",
        note="orig",
    )
    healed = DateHealingResolverV2.apply([rv])[0]
    assert healed.value == "Lori Creswell and Robert Creswell"
    assert healed.note == "orig"  # no embedded-date annotation


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw,expected",
    [
        # 2-digit year (Y2K pivot: 00-68 → 20xx)
        ("01/21/26", "January 21, 2026"),
        ("02/04/26", "February 4, 2026"),
        ("12/31/99", "December 31, 1999"),
        ("01-21-26", "January 21, 2026"),
        # 2-digit year embedded
        ("On 01/21/26, the Debtor filed", "On January 21, 2026, the Debtor filed"),
        ("Payment Advice on 02/04/26.", "Payment Advice on February 4, 2026."),
        # Ordinal suffix
        ("January 21st, 2026", "January 21, 2026"),
        ("21st January 2026", "January 21, 2026"),
        ("March 3rd, 2026", "March 3, 2026"),
        # Abbreviation period
        ("Mar. 20, 2026", "March 20, 2026"),
        ("Jan. 1, 2026", "January 1, 2026"),
    ],
)
def test_short_year_ordinal_and_abbreviation_variants(raw, expected):
    rv = ResolvedTemplateValueV2(template_variable="x", value=raw)
    healed = DateHealingResolverV2.apply([rv])[0]
    assert healed.value == expected


@pytest.mark.unit
def test_chapter_number_not_misread_as_date():
    """Guard against '13' (chapter number) being interpreted as a date."""
    rv = ResolvedTemplateValueV2(template_variable="chapter", value="13")
    healed = DateHealingResolverV2.apply([rv])[0]
    assert healed.value == "13"
