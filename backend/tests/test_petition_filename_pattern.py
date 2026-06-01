from src.courtdrive.service import (
    extract_case_number_from_filename,
    extract_petition_metadata_from_filename,
    normalize_client_name,
    normalize_court_region_identifier,
    strip_case_number_suffix,
)


def test_extract_petition_metadata_parses_new_filename_pattern():
    result = extract_petition_metadata_from_filename(
        "Bankruptcy_Petition_John_Javier_3_26-bk-00635_1234_FLSB.pdf"
    )

    assert result["client_name"] == "John Javier"
    assert result["case_number"] == "26-00635"
    assert result["ssn_last4"] == "1234"
    assert result["court_region"] == "FLSB"
    assert result["normalized_court_region"] == "southern"


def test_extract_petition_metadata_parses_ss_prefix_pattern():
    result = extract_petition_metadata_from_filename(
        "Bankruptcy_Petition_John_Michael_Doe_3_26-bk-00635_SS_1234_FLSB.pdf"
    )

    assert result["client_name"] == "John Michael Doe"
    assert result["case_number"] == "26-00635"
    assert result["ssn_last4"] == "1234"
    assert result["court_region"] == "FLSB"
    assert result["normalized_court_region"] == "southern"


def test_extract_petition_metadata_normalizes_multi_debtor_separator_to_and():
    result = extract_petition_metadata_from_filename(
        "Bankruptcy_Petition_John_Doe_&_Jane_Doe_3_26-bk-00635_SS_1234_FLSB.pdf"
    )

    assert result["client_name"] == "John Doe and Jane Doe"


def test_extract_petition_metadata_parses_short_case_number_format():
    result = extract_petition_metadata_from_filename(
        "Bankruptcy_Petition_John_Doe_26-11993_SS_1234_FLSB.pdf"
    )

    assert result["client_name"] == "John Doe"
    assert result["case_number"] == "26-11993"
    assert result["ssn_last4"] == "1234"


def test_extract_petition_metadata_parses_case_number_with_judge_suffix():
    result = extract_petition_metadata_from_filename(
        "Bankruptcy_Petition_Jane_Doe_25-31154-KKS_SS_5678_FLSB.pdf"
    )

    assert result["client_name"] == "Jane Doe"
    assert result["case_number"] == "25-31154"
    assert result["ssn_last4"] == "5678"


def test_extract_petition_metadata_parses_underscore_non_bk_case_pattern():
    result = extract_petition_metadata_from_filename(
        "Bankruptcy_Petition_Benjamin_Wendell_Ingram_23_18356_PDR_SS_2069_FLSB.pdf"
    )

    assert result["client_name"] == "Benjamin Wendell Ingram"
    assert result["case_number"] == "23-18356"
    assert result["ssn_last4"] == "2069"
    assert result["court_region"] == "FLSB"
    assert result["normalized_court_region"] == "southern"


def test_extract_petition_metadata_strips_accidental_trailing_case_from_name():
    result = extract_petition_metadata_from_filename(
        "Bankruptcy_Petition_John_Doe_26-11993_26-11993_SS_1234_FLSB.pdf"
    )

    assert result["client_name"] == "John Doe"
    assert result["case_number"] == "26-11993"


def test_extract_petition_metadata_handles_multi_debtor_with_chapter_prefix_case():
    result = extract_petition_metadata_from_filename(
        "Bankruptcy_Petition_Brittney_Temesha_Glass_and_Raven_Sloan_Glass_8_26-bk-01042-CPM_SS_4337.pdf"
    )

    assert result["client_name"] == "Brittney Temesha Glass and Raven Sloan Glass"
    assert result["case_number"] == "26-01042"
    assert result["ssn_last4"] == "4337"


def test_extract_petition_metadata_supports_legacy_pattern_without_region():
    result = extract_petition_metadata_from_filename(
        "Bankruptcy_Petition_Jane_Doe_8_26-bk-01330_5678.pdf"
    )

    assert result["client_name"] == "Jane Doe"
    assert result["case_number"] == "26-01330"
    assert result["ssn_last4"] == "5678"
    assert result["court_region"] is None
    assert result["normalized_court_region"] is None


def test_extract_case_number_from_filename_supports_underscore_judge_separator():
    case_number = extract_case_number_from_filename(
        "Bankruptcy_Petition_John_Doe_3_26-bk-00635_1234_FLSB.pdf"
    )

    assert case_number == "26-00635"


def test_extract_case_number_from_filename_supports_underscore_non_bk_pattern():
    case_number = extract_case_number_from_filename(
        "Bankruptcy_Petition_Benjamin_Wendell_Ingram_23_18356_PDR_SS_2069_FLSB.pdf"
    )

    assert case_number == "23-18356"


def test_normalize_court_region_identifier_handles_full_district_label():
    assert normalize_court_region_identifier("Southern District of Florida") == "southern"


def test_normalize_client_name_unifies_multi_debtor_separators():
    assert normalize_client_name("John Doe & Jane Doe") == "john doe and jane doe"
    assert normalize_client_name("John Doe / Jane Doe") == "john doe and jane doe"


def test_strip_case_number_suffix_removes_trailing_case_number():
    assert strip_case_number_suffix("John Doe 26-11993") == "John Doe"
    assert (
        strip_case_number_suffix("Brittney Temesha Glass and Raven Sloan Glass 8 26-bk-01042-CPM")
        == "Brittney Temesha Glass and Raven Sloan Glass"
    )
    assert strip_case_number_suffix("Benjamin Wendell Ingram 23 18356 PDR") == "Benjamin Wendell Ingram"
