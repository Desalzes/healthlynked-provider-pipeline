"""TDD for the $0 data-quality pre-pass: NPI check-digit validation (Luhn,
prefix 80840) and duplicate detection (record linkage). Both are named Bonus
Points in the HealthLynked brief."""
from datetime import date
from provider_pipeline.schemas import ProviderRecord
from provider_pipeline.dataquality import (
    validate_npi, find_duplicate_clusters, data_quality_report,
)


def _rec(pid, *, npi="1234567893", name="Jane Smith, MD",
         practice="Acme Health", address="100 Main St, Naples, FL 34102",
         phone="239-555-1234"):
    return ProviderRecord(
        provider_id=pid, provider_name=name, npi=npi, specialty="Cardiology",
        practice_name=practice, address=address, phone=phone,
        last_verified_date=date(2023, 9, 1), is_active=True)


# --- NPI check-digit validation (Luhn over "80840" + 9-digit base) ---

def test_validate_npi_accepts_canonical_valid_number():
    # CMS textbook example: 1234567893 has a correct Luhn check digit (3).
    assert validate_npi("1234567893") is True


def test_validate_npi_rejects_wrong_check_digit():
    # 1234567890 is the brief's placeholder NPI; its check digit should be 3, not 0.
    assert validate_npi("1234567890") is False


def test_validate_npi_rejects_non_ten_digit():
    assert validate_npi("12345") is False
    assert validate_npi("123456789012") is False


def test_validate_npi_rejects_non_numeric():
    assert validate_npi("12345abcde") is False
    assert validate_npi("") is False
    assert validate_npi(None) is False


def test_validate_npi_accepts_a_second_independently_valid_number():
    # 1679576722 is a real, Luhn-valid NPI (independent of the textbook example).
    assert validate_npi("1679576722") is True


def test_validate_npi_tolerates_surrounding_whitespace():
    # Dirty ingest often pads values; a stray leading/trailing space is not a real
    # NPI error, so it is trimmed before validation.
    assert validate_npi("  1234567893 ") is True


def test_validate_npi_rejects_internal_space_and_int_input():
    assert validate_npi("12345 7893") is False   # internal space -> not 10 digits
    assert validate_npi(1234567893) is False      # non-str input (isinstance guard)


# --- Duplicate detection (record linkage / union-find) ---

def test_same_npi_is_a_duplicate_cluster():
    recs = [_rec("A", npi="1234567893"), _rec("B", npi="1234567893", name="J. Smith")]
    clusters = find_duplicate_clusters(recs)
    assert clusters == [["A", "B"]]


def test_same_phone_different_formatting_clusters():
    recs = [_rec("A", npi="1679576722", phone="(239) 555-1212"),
            _rec("B", npi="1234567893", phone="239.555.1212", name="Other Name",
                 address="9 Far Rd, Tampa, FL 33601")]
    clusters = find_duplicate_clusters(recs)
    assert clusters == [["A", "B"]]


def test_same_name_and_address_clusters_even_with_different_npi():
    recs = [_rec("A", npi="1679576722", phone="111-111-1111"),
            _rec("B", npi="1234567893", phone="222-222-2222")]
    # Same default name + same default address -> same physical listing.
    clusters = find_duplicate_clusters(recs)
    assert clusters == [["A", "B"]]


def test_empty_and_single_record_have_no_clusters():
    assert find_duplicate_clusters([]) == []
    assert find_duplicate_clusters([_rec("A")]) == []


def test_two_separate_clusters_ordered_by_first_appearance():
    # Interleaved input [A, C, B, D]: A~B (npi X), C~D (npi Y); clusters should be
    # ordered by their first member's appearance -> [[A,B],[C,D]].
    recs = [_rec("A", npi="1000000012", name="A", phone="111-111-1111",
                 address="1 A St, Miami, FL 33101"),
            _rec("C", npi="2000000028", name="C", phone="333-333-3333",
                 address="3 C St, Tampa, FL 33601"),
            _rec("B", npi="1000000012", name="B2", phone="222-222-2222",
                 address="2 B St, Ocala, FL 34470"),
            _rec("D", npi="2000000028", name="D2", phone="444-444-4444",
                 address="4 D St, Naples, FL 34102")]
    assert find_duplicate_clusters(recs) == [["A", "B"], ["C", "D"]]


def test_parseable_phone_does_not_pull_in_a_junk_phone_record():
    recs = [_rec("A", npi="1679576722", name="A", phone="305-555-1000",
                 address="1 A St, Miami, FL 33101"),
            _rec("B", npi="1234567893", name="B", phone="N/A",
                 address="2 B St, Tampa, FL 33601")]
    assert find_duplicate_clusters(recs) == []


def test_distinct_records_produce_no_cluster():
    recs = [_rec("A", npi="1679576722", name="Alice A", phone="111-111-1111",
                 address="1 First St, Naples, FL 34102"),
            _rec("B", npi="1234567893", name="Bob B", phone="222-222-2222",
                 address="2 Second St, Tampa, FL 33601")]
    assert find_duplicate_clusters(recs) == []


def test_linkage_is_transitive_across_signals():
    # A~B via phone, B~C via NPI -> A,B,C are one cluster.
    # (B and C share an arbitrary identical NPI STRING purely to exercise NPI-key
    # linkage; clustering keys on string equality, not check-digit validity.)
    recs = [_rec("A", npi="1679576722", name="A", phone="305-555-0001",
                 address="1 A St, Miami, FL 33101"),
            _rec("B", npi="1144544489", name="B", phone="(305) 555-0001",
                 address="2 B St, Miami, FL 33102"),
            _rec("C", npi="1144544489", name="C", phone="305-555-9999",
                 address="3 C St, Miami, FL 33103")]
    clusters = find_duplicate_clusters(recs)
    assert clusters == [["A", "B", "C"]]


def test_unparseable_phone_does_not_link_records():
    # Two records with junk phones must NOT cluster on the phone signal.
    recs = [_rec("A", npi="1679576722", name="A", phone="N/A",
                 address="1 A St, Miami, FL 33101"),
            _rec("B", npi="1234567893", name="B", phone="see website",
                 address="2 B St, Tampa, FL 33601")]
    assert find_duplicate_clusters(recs) == []


# --- Combined report ---

def test_data_quality_report_empty_input():
    assert data_quality_report([]) == {
        "records_total": 0, "invalid_npi": [], "invalid_npi_count": 0,
        "duplicate_clusters": [], "duplicate_record_count": 0,
    }


def test_data_quality_report_counts_invalid_and_duplicate():
    recs = [_rec("A", npi="1234567893"),
            _rec("B", npi="1234567893"),          # dup of A (same NPI)
            _rec("C", npi="1234567890",           # invalid check digit
                 name="Solo", address="5 Solo Rd, Ocala, FL 34470",
                 phone="352-555-7777")]
    report = data_quality_report(recs)
    assert report["records_total"] == 3
    assert report["invalid_npi"] == ["C"]
    assert report["duplicate_clusters"] == [["A", "B"]]
    assert report["invalid_npi_count"] == 1
    assert report["duplicate_record_count"] == 2
