from pathlib import Path
from datetime import date
from provider_pipeline.config import Config
from provider_pipeline.pipeline import Deps, run_record
from provider_pipeline.schemas import ProviderRecord, ContactTuple
from provider_pipeline.runner import build_deps, run_batch
from provider_pipeline.synth import generate
from provider_pipeline.audit import AuditLog


def test_run_batch_over_showcase(tmp_path):
    # Use the committed showcase fixtures shipped in the repo.
    fixtures = Path("data/fixtures")
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


def _rec(pid):
    return ProviderRecord(provider_id=pid, provider_name="J S", npi="1", specialty="FM",
                          practice_name="Clinic", address="123 Main St, Naples, FL 34102",
                          phone="2395550000", last_verified_date=date(2024, 1, 1))


def test_run_batch_continues_past_a_failing_record(tmp_path):
    # A single record that raises (e.g. a live LLM/network error) must NOT abort the
    # whole batch — it is recorded as an error and processing continues.
    def boom(_npi):
        raise RuntimeError("simulated source failure")

    bad_then_good = [_rec("BAD"), _rec("GOOD")]

    def fetch(npi):
        # fail only for the first record's npi lookup; the dataclass calls per record
        raise RuntimeError("simulated source failure")

    deps = Deps(cfg=Config(), fetch_canonical=boom,
                extract_website=lambda r: (ContactTuple(), 0),
                extract_snippet=lambda r: (ContactTuple(), 0),
                cache_dir=tmp_path)
    log = AuditLog(tmp_path / "audit.db")
    summary = run_batch(bad_then_good, deps, log)
    log.close()
    # both records errored, but run_batch returned cleanly with an errors list
    assert len(summary["errors"]) == 2
    assert summary["errors"][0]["provider_id"] == "BAD"
