"""Conformance against the sponsor's own contract file (data/example_record.json).
No prior test loaded it — which is exactly how the prototype came to diverge from
the sponsor's canonical auto_update example. This pins both the I/O SHAPE and, via
the HL_001-shaped SHOW-MOVE record, that feeding the sponsor's example yields the
sponsor's expected auto_update output.
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


def test_hl001_shaped_record_reproduces_sponsor_auto_update():
    """SHOW-MOVE is shaped exactly like the sponsor's HL_001 example. The pipeline
    must reproduce the sponsor's expected auto_update: address + phone both change,
    confirmed by NPI + Practice Website + State Medical Board."""
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
