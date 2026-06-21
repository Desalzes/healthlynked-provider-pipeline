from provider_pipeline.normalize import (
    normalize_address, normalize_address_str, normalize_phone, agreement,
)


def test_normalize_phone_strips_formatting():
    assert normalize_phone("(239) 555-1212") == "2395551212"
    assert normalize_phone("239.555.1212 ext 4") == "2395551212"
    assert normalize_phone("+1 239 555 1212") == "2395551212"


def test_normalize_phone_junk_is_none_not_empty():
    # Digit-less junk must be None, not "" — otherwise two broken phones compare
    # equal and a missing number reads as "verified, no change".
    assert normalize_phone("N/A") is None
    assert normalize_phone("see website") is None
    assert normalize_phone("") is None


def test_agreement_two_unparseable_phones_do_not_agree():
    assert agreement("N/A", new="see website", old="2395550000", field="phone") == 0.0


def test_partial_phone_is_not_a_match():
    assert normalize_phone("555-1212") is None
    assert agreement("555-1212", new="2395551212", old="2395550000", field="phone") == 0.0


def test_normalize_address_lowercases_and_orders():
    a = normalize_address("123 Main St.", "Naples", "FL", "34102-1234")
    assert a.street and a.city == "naples" and a.state == "fl"
    assert a.zip == "34102"
    assert a.key().startswith("123 main st")


def test_normalize_address_str_parses_single_line():
    a = normalize_address_str("100 Main St, Naples, FL 34102")
    assert a.city == "naples"
    assert a.state == "fl"
    assert a.zip == "34102"
    assert a.key().startswith("100 main st")


def test_normalize_address_str_handles_zip4():
    a = normalize_address_str("250 Health Park Dr, Fort Myers, FL 33908-1234")
    assert a.zip == "33908"
    assert a.state == "fl"
    assert a.city == "fort myers"


def test_normalize_address_str_none():
    assert normalize_address_str(None) is None
    assert normalize_address_str("") is None


def test_agreement_exact_new_is_one():
    assert agreement("2395551212", new="2395551212", old="2395550000", field="phone") == 1.0


def test_agreement_exact_old_is_zero():
    assert agreement("2395550000", new="2395551212", old="2395550000", field="phone") == 0.0


def test_agreement_partial_address_is_fractional():
    # same street/zip, different suite -> between 0 and 1
    obs = "500 oak ave ste 200|naples|fl|34102"
    new = "500 oak ave ste 300|naples|fl|34102"
    old = "123 main st|naples|fl|34102"
    score = agreement(obs, new=new, old=old, field="address")
    assert 0.0 < score < 1.0


def test_agreement_none_observed_is_zero():
    assert agreement(None, new="x", old="y", field="address") == 0.0
