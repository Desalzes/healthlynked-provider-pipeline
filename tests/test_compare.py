from datetime import date, datetime, timezone
from provider_pipeline.schemas import ProviderRecord, CanonicalRecord, AddressTuple
from provider_pipeline.compare import (
    field_existing, field_canonical, is_candidate_change, cross_source,
)


def _rec(**o):
    base = dict(provider_id="P1", provider_name="J S", npi="1", specialty="FM",
                practice_name="Clinic", address="123 Main St, Naples, FL 34102",
                phone="2395550000", is_active=True, last_verified_date=date(2025, 1, 1))
    base.update(o)
    return ProviderRecord(**base)


def _canon(street="500 oak ave", phone="2395559999"):
    return CanonicalRecord(npi="1", full_name="J S", taxonomy="FM",
                           addresses=[AddressTuple(street=street, city="naples", state="fl", zip="34102")],
                           phone=phone, is_active=True, fetched_at=datetime.now(timezone.utc))


def test_field_existing_address_and_phone():
    r = _rec()
    assert "123 main st" in field_existing(r, "address")
    assert field_existing(r, "phone") == "2395550000"


def test_field_canonical_silent_phone_is_none():
    assert field_canonical(_canon(phone=None), "phone") is None


def test_is_candidate_change_true_when_npi_differs():
    assert is_candidate_change(_rec(), _canon(), "phone") is True


def test_is_candidate_change_false_when_match():
    assert is_candidate_change(_rec(phone="2395559999"), _canon(), "phone") is False


def test_cross_source_cases():
    # npi == website == existing -> no_change
    assert cross_source("2395550000", "2395550000", "2395550000", "phone") == "no_change"
    # npi == website != existing -> strong_update
    assert cross_source("2395559999", "2395559999", "2395550000", "phone") == "strong_update"
    # npi != existing, website == existing -> false_alarm
    assert cross_source("2395559999", "2395550000", "2395550000", "phone") == "false_alarm"
    # npi != website -> conflict
    assert cross_source("2395559999", "2395558888", "2395550000", "phone") == "conflict"
