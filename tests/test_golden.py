"""Golden test: locks the exact numbers WRITEUP.md cites against the committed
corpus, so the writeup's headline figures cannot silently drift. Runs the bundled
54-record synthetic set through the offline (fake-contacts) path.
"""
import json
from pathlib import Path
from provider_pipeline.schemas import ProviderRecord
from provider_pipeline.runner import build_deps, run_batch
from provider_pipeline.audit import AuditLog
from provider_pipeline.cost import per_1k_estimate

DATA = Path(__file__).resolve().parents[1] / "data"


def _run(tmp_path):
    records = [ProviderRecord(**r) for r in
               json.loads((DATA / "synthetic_providers.json").read_text(encoding="utf-8"))]
    deps = build_deps(fixtures_dir=DATA / "fixtures", cache_dir=tmp_path / "cache",
                      live=False, fake_contacts=True)
    log = AuditLog(tmp_path / "audit.db", fresh=True)
    summary = run_batch(records, deps, log)
    log.close()
    return records, summary


def test_offline_split_matches_writeup(tmp_path):
    records, summary = _run(tmp_path)
    # WRITEUP.md section 3.2: records=54 decisions=108 auto=11 review=9 no_change=88.
    assert len(records) == 54
    assert summary["decisions_total"] == 108
    assert summary["counts"] == {"auto_update": 11, "human_review": 9, "no_change": 88}
    # Offline path spends nothing — the reproducibility claim.
    assert summary["llm_calls"] == 0
    assert summary["total_llm_tokens"] == 0
    # Cost is measured from the count of gated LLM-stage calls actually invoked
    # (each paid source extracted at most once per record).
    assert summary["gated_calls_total"] == 24


def test_per_1k_cost_reconciles_decisions_and_records(tmp_path):
    _records, summary = _run(tmp_path)
    est = per_1k_estimate(summary, price_per_1k_tokens=0.0002,
                          reviewer_minutes_each=3.0, reviewer_rate_per_hour=30.0,
                          mean_tokens_per_call=400)
    record_est = per_1k_estimate(summary, price_per_1k_tokens=0.0002,
                                 reviewer_minutes_each=3.0, reviewer_rate_per_hour=30.0,
                                 mean_tokens_per_call=400, basis="record")
    # The tool reports per-1,000-DECISIONS: 83.3 reviews -> $125.00 (WRITEUP table note).
    assert est["reviews_per_1k"] == 83.3
    assert abs(est["review_usd"] - 125.0) < 1e-4
    # WRITEUP's per-1,000-RECORDS headline is exactly 2x (two tracked field-decisions
    # per record). Locking the relationship keeps the two numbers from contradicting.
    assert round(est["review_usd"] * 2) == 250
    # Gated inference is measured from the real call count, not a hand-picked fraction.
    assert est["gated_calls_per_1k"] == 222.2
    assert summary["records_total"] == 54
    assert record_est["gated_calls_per_1k"] == 444.4
    assert abs(record_est["inference_usd"] - 0.035556) < 1e-6
    assert round(record_est["review_usd"]) == 250
