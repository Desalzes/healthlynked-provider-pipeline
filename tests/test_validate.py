"""NPI check-digit (Luhn, prefix 80840) validation — a $0 structural pre-filter.

CMS computes the 10th NPI digit as a Luhn check over "80840" + the first 9 digits.
A directory can reject structurally-impossible NPIs before spending any API/LLM call.
"""
from provider_pipeline.validate import validate_npi


def test_known_valid_npi_passes():
    # 1234567893 is a standard valid example NPI (check digit 3 over base 123456789).
    assert validate_npi("1234567893") is True


def test_sponsor_placeholder_npi_fails_check_digit():
    # The sponsor's example uses 1234567890 — same base, wrong check digit.
    assert validate_npi("1234567890") is False


def test_wrong_length_fails():
    assert validate_npi("123456789") is False      # 9 digits
    assert validate_npi("12345678901") is False     # 11 digits


def test_non_digit_fails():
    assert validate_npi("12345abcde") is False
    assert validate_npi("") is False
    assert validate_npi(None) is False  # type: ignore[arg-type]
