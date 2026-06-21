"""Conformance against the sponsor's own contract file (data/example_record.json).
No prior test loaded it — which is exactly how the prototype came to diverge from
the sponsor's canonical auto_update example. This pins both the I/O shape and the
HL_001-shaped SHOW-MOVE demonstration scenario without claiming it is the literal
sample row.
"""
import json
from pathlib import Path
from provider_pipeline.schemas import ProviderRecord
from provider_pipeline.synth import generate
from provider_pipeline.runner import build_deps, run_batch
from provider_pipeline.audit import AuditLog

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = json.loads((ROOT / "data" / "example_record.json").read_text(encoding="utf-8"))


def test_sponsor_example_input_parses_as_provider_record():
    rec = ProviderRecord(**EXAMPLE["example_input"])
    assert rec.provider_id == "HL_001"
    assert rec.npi == "1234567890"


def test_our_output_keys_match_sponsor_example():
    want_top = set(EXAMPLE["example_output_auto_update"]) - {"changes"}
    want_change = set(EXAMPLE["example_output_auto_update"]["changes"][0])
    # Build any auto recommendation and compare key sets to the sponsor's.
    deps = build_deps(fixtures_dir=ROOT / "data" / "fixtures",
                      cache_dir=ROOT / "out" / "_t", live=False, fake_contacts=True)
    move = next(r for r in generate(seed=7) if r.provider_id == "SHOW-MOVE")
    log = AuditLog(":memory:")
    rec = run_batch([move], deps, log)["recommendations"][0]
    log.close()
    dumped = rec.model_dump(mode="json")
    assert want_top <= set(dumped)                       # all sponsor top-level keys present
    assert want_change <= set(dumped["changes"][0])      # all sponsor change keys present


def test_hl001_shaped_record_auto_updates_three_source_movement():
    """SHOW-MOVE demonstrates the sponsor's movement pattern: address + phone both
    change, confirmed by NPI + Practice Website + State Medical Board."""
    deps = build_deps(fixtures_dir=ROOT / "data" / "fixtures",
                      cache_dir=ROOT / "out" / "_t", live=False, fake_contacts=True)
    move = next(r for r in generate(seed=7) if r.provider_id == "SHOW-MOVE")
    log = AuditLog(":memory:")
    rec = run_batch([move], deps, log)["recommendations"][0]
    log.close()

    assert rec.recommended_action == "auto_update"
    assert rec.change_detected is True
    by_field = {c.field: c for c in rec.changes}
    assert set(by_field) == {"address", "phone"}
    assert by_field["address"].new_value == "250 Health Park Dr, Fort Myers, FL 33908"
    assert by_field["phone"].new_value == "239-555-9000"
    for c in rec.changes:
        assert "State Medical Board" in c.supporting_sources
        assert "NPI Registry" in c.supporting_sources
        assert "Practice Website" in c.supporting_sources


def test_submission_text_does_not_claim_literal_hl001_reproduction():
    writeup = (ROOT / "WRITEUP.md").read_text(encoding="utf-8")
    forbidden = "sponsor's own HL_001 reproduced end-to-end"
    assert forbidden not in writeup
    assert "HL_001-shaped" in writeup
    # The LEDGER lives in the monorepo parent; when this project is published as a
    # standalone repo it is intentionally absent, so only check it where present.
    ledger = ROOT.parents[1] / "LEDGER.md"
    if ledger.exists():
        assert forbidden not in ledger.read_text(encoding="utf-8")


# --- Literal HL_001 through the unmodified pipeline, at both thresholds ----------
# The sponsor's example cites a 3-source address (NPI + Website + Board) and a
# 2-source phone (Website + NPI). We encode exactly those sources and run the
# LITERAL HL_001 record so the submission can show — not dodge — what the pipeline
# does with the brief's own example.
import dataclasses
from provider_pipeline.config import Config
from provider_pipeline.sponsor_example import hl001_input, hl001_deps
from provider_pipeline.pipeline import run_record, to_recommendation


def _run_hl001(cfg: Config):
    rec = hl001_input()
    result, _rows, _telem = run_record(rec, hl001_deps(cfg))
    return to_recommendation(result, rec)


def test_literal_hl001_holds_two_source_phone_at_default_threshold():
    rec = _run_hl001(Config())  # default auto_threshold = 0.85
    assert rec.provider_id == "HL_001"
    assert rec.recommended_action == "human_review"   # phone held for a 3rd source
    assert rec.overall_confidence == 0.90             # (address 1.00 + phone 0.80) / 2
    by_field = {c.field: c for c in rec.changes}
    assert by_field["phone"].supporting_sources == ["NPI Registry", "Practice Website"]
    assert "State Medical Board" in by_field["address"].supporting_sources


def test_literal_hl001_matches_sponsor_auto_update_at_080_threshold():
    cfg = dataclasses.replace(Config(), auto_threshold=0.80)
    rec = _run_hl001(cfg)
    assert rec.recommended_action == "auto_update"    # matches the sponsor's example
    assert rec.overall_confidence == 0.90             # matches the sponsor's 0.90
