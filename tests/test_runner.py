from pathlib import Path
from datetime import date, datetime, timezone
from provider_pipeline.config import Config
from provider_pipeline.pipeline import Deps, run_record
from provider_pipeline.schemas import ProviderRecord, ContactTuple, CanonicalRecord, AddressTuple
from provider_pipeline.runner import build_deps, run_batch
from provider_pipeline.synth import generate
from provider_pipeline.audit import AuditLog


def test_run_batch_over_showcase(tmp_path):
    # Use the committed showcase fixtures shipped in the repo.
    fixtures = Path(__file__).resolve().parents[1] / "data" / "fixtures"
    cache = tmp_path / "_llm_cache"
    deps = build_deps(fixtures_dir=fixtures, cache_dir=cache, live=False, fake_contacts=True)
    recs = [r for r in generate(seed=7) if r.provider_id.startswith("SHOW")]
    db = tmp_path / "audit.db"
    log = AuditLog(db)
    summary = run_batch(recs, deps, log)
    log.close()
    assert summary["decisions_total"] >= 3
    assert summary["counts"]["auto_update"] >= 1
    assert summary["counts"]["human_review"] >= 1


def _rec(pid, npi="1"):
    return ProviderRecord(provider_id=pid, provider_name="J S", npi=npi, specialty="FM",
                          practice_name="Clinic", address="123 Main St, Naples, FL 34102",
                          phone="2395550000", last_verified_date=date(2024, 1, 1))


def test_run_batch_continues_past_a_failing_record(tmp_path):
    # A single record that raises (e.g. a live LLM/network error) must not abort the
    # whole batch. It is recorded as an error and the following valid record is processed.
    bad_then_good = [_rec("BAD", "bad"), _rec("GOOD", "good")]

    def fetch(npi):
        if npi == "bad":
            raise RuntimeError("simulated source failure")
        return CanonicalRecord(
            npi=npi,
            full_name="J S",
            taxonomy="FM",
            addresses=[AddressTuple(street="123 Main St", city="Naples", state="FL", zip="34102")],
            phone="2395550000",
            is_active=True,
            fetched_at=datetime.now(timezone.utc),
        )

    deps = Deps(cfg=Config(), fetch_canonical=fetch,
                extract_website=lambda r: (ContactTuple(), 0),
                extract_snippet=lambda r: (ContactTuple(), 0),
                cache_dir=tmp_path)
    log = AuditLog(tmp_path / "audit.db")
    summary = run_batch(bad_then_good, deps, log)
    log.close()

    assert len(summary["errors"]) == 1
    assert summary["errors"][0]["provider_id"] == "BAD"
    assert [r.provider_id for r in summary["recommendations"]] == ["GOOD"]
    assert summary["decisions_total"] == 2
    assert summary["counts"]["no_change"] == 2
    assert summary["input_records_total"] == 2
    assert summary["processed_records_total"] == 1
    assert summary["error_records_total"] == 1
