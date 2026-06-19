import json
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


def test_fetch_missing_cache_no_live_returns_none(tmp_path):
    assert fetch_canonical("9999999999", cache_dir=tmp_path, live=False) is None
