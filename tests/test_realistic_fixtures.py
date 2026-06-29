"""Offline structural checks on the realistic practice-page fixtures (no LLM /
network, so they run in CI). The live extraction measurement that proves the LLM
pulls the current contact out of the noise lives in
scripts/measure_realistic_extraction.py.

These fixtures exist to demonstrate the extractor on production-shaped input:
nav menus, hours, insurance lists, labeled fax/billing decoys, suite numbers,
and a permanently-closed previous address (R3). The point is that a naive
first-match regex mis-handles them — so here we assert (a) the fixtures are
genuinely realistic (sized, contain decoys) and (b) the naive regex floor is in
fact insufficient on at least one, which is the reason the LLM stage exists."""
import json
import re
from pathlib import Path
from provider_pipeline.runner import _regex_contact
from provider_pipeline.sources.website import html_to_text

FIX = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "realistic"
EXPECTED = json.loads((FIX / "expected.json").read_text(encoding="utf-8"))


def test_every_fixture_has_expected_values():
    for slug in EXPECTED:
        assert (FIX / f"{slug}.html").exists(), f"missing fixture {slug}.html"


def test_fixtures_are_realistically_sized_not_toy():
    # Toy fixtures are ~100-200 chars; realistic practice pages are far larger.
    for slug in EXPECTED:
        html = (FIX / f"{slug}.html").read_text(encoding="utf-8")
        assert len(html) > 900, f"{slug} is too small to be realistic ({len(html)})"


def test_each_fixture_actually_contains_its_current_contact():
    for slug, exp in EXPECTED.items():
        text = html_to_text((FIX / f"{slug}.html").read_text(encoding="utf-8"))
        digits = re.sub(r"\D", "", text)
        assert exp["phone"] in digits, f"{slug} missing current phone"
        assert exp["zip"] in text, f"{slug} missing current zip"
        assert exp["street_number"] in text, f"{slug} missing street number"


def test_each_fixture_contains_decoys():
    # If a fixture has no decoy, it is not exercising real-world ambiguity.
    for slug, exp in EXPECTED.items():
        text = re.sub(r"\D", "", html_to_text((FIX / f"{slug}.html").read_text(encoding="utf-8")))
        decoys = exp.get("must_not_pick_phones", [])
        assert decoys, f"{slug} declares no decoy phones"
        for d in decoys:
            assert d in text, f"{slug} decoy phone {d} not present in page"


def test_naive_regex_floor_mis_extracts_the_address_on_realistic_input():
    """The reason the LLM stage exists, stated precisely: the offline first-match
    regex extractor mis-extracts the ADDRESS on realistic pages — it backtracks to a
    suite number ('210', '300') instead of the street number — even where it happens
    to get the phone right because the current number precedes the fax/billing decoys
    in document order. So we assert per-signal: >=1 page has a wrong street, and we do
    NOT claim the phone is fooled (it is not, on these fixtures)."""
    street_wrong = 0
    for slug, exp in EXPECTED.items():
        c = _regex_contact(html_to_text((FIX / f"{slug}.html").read_text(encoding="utf-8")))
        street_ok = bool(c.address_line) and exp["street_number"] in c.address_line
        if not street_ok:
            street_wrong += 1
    assert street_wrong >= 1, "expected the naive regex to mis-extract the street on >=1 page"
