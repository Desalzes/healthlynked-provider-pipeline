import json
import os
from datetime import datetime, timezone
from provider_pipeline.sources.npi import fetch_canonical, parse_npi_response


SAMPLE = {
    "result_count": 1,
    "results": [{
        "number": "1234567890",
        "basic": {"first_name": "JANE", "last_name": "SMITH", "status": "A"},
        "taxonomies": [{"desc": "Family Medicine", "primary": True}],
        "addresses": [
            {"address_purpose": "LOCATION", "address_1": "500 OAK AVE",
             "city": "NAPLES", "state": "FL", "postal_code": "341023456",
             "telephone_number": "239-555-9999"},
        ],
    }],
}


def test_parse_extracts_location_address_and_phone():
    rec = parse_npi_response(SAMPLE)
    assert rec.npi == "1234567890"
    assert rec.is_active is True
    assert rec.taxonomy == "Family Medicine"
    assert rec.addresses[0].zip == "34102"
    assert rec.phone == "2395559999"


def test_parse_returns_none_for_no_results():
    assert parse_npi_response({"result_count": 0, "results": []}) is None


def test_fetch_uses_cache(tmp_path):
    cache = tmp_path / "npi"
    cache.mkdir()
    (cache / "1234567890.json").write_text(json.dumps(SAMPLE), encoding="utf-8")
    rec = fetch_canonical("1234567890", cache_dir=cache, live=False)
    assert rec is not None and rec.phone == "2395559999"


def test_fetch_cache_uses_file_mtime_as_fetched_at(tmp_path):
    cache = tmp_path / "npi"
    cache.mkdir()
    cached = cache / "1234567890.json"
    cached.write_text(json.dumps(SAMPLE), encoding="utf-8")
    observed_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    os.utime(cached, (observed_at.timestamp(), observed_at.timestamp()))

    rec = fetch_canonical("1234567890", cache_dir=cache, live=False)

    assert rec is not None
    assert abs((rec.fetched_at - observed_at).total_seconds()) < 1.0


def test_fixture_fresh_metadata_uses_current_fetch_time(tmp_path):
    cache = tmp_path / "npi"
    cache.mkdir()
    cached = cache / "1234567890.json"
    payload = {"_pipeline_fixture_fresh": True, **SAMPLE}
    cached.write_text(json.dumps(payload), encoding="utf-8")
    old = datetime(2020, 1, 1, tzinfo=timezone.utc)
    os.utime(cached, (old.timestamp(), old.timestamp()))

    before = datetime.now(timezone.utc)
    rec = fetch_canonical("1234567890", cache_dir=cache, live=False)
    after = datetime.now(timezone.utc)

    assert rec is not None
    assert before <= rec.fetched_at <= after


def test_fetch_missing_cache_no_live_returns_none(tmp_path):
    assert fetch_canonical("9999999999", cache_dir=tmp_path, live=False) is None
