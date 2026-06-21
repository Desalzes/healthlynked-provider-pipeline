from provider_pipeline.config import Config
from provider_pipeline.cost import per_1k_estimate, llm_everywhere_baseline, sweep_thresholds


def test_per_1k_scales_inference_and_review():
    summary = {"decisions_total": 100, "total_llm_tokens": 5000,
               "records_total": 50,
               "counts": {"auto_update": 10, "human_review": 5, "no_change": 85},
               "llm_calls": 15}
    est = per_1k_estimate(summary, price_per_1k_tokens=0.0002,
                          reviewer_minutes_each=3.0, reviewer_rate_per_hour=30.0)
    # tokens scaled to 1k records: 5000 * 10 = 50000 tokens -> 50 * 0.0002 = $0.01
    assert abs(est["inference_usd"] - 0.01) < 1e-6
    # reviewers: 5 reviews -> 50 per 1k -> 50 * 3 min = 150 min -> 2.5 h * $30 = $75
    assert abs(est["review_usd"] - 75.0) < 1e-6
    assert est["total_usd"] > est["inference_usd"]


def test_per_1k_can_report_record_basis():
    summary = {"decisions_total": 100, "records_total": 50, "total_llm_tokens": 5000,
               "gated_calls_total": 20,
               "counts": {"auto_update": 10, "human_review": 5, "no_change": 85},
               "llm_calls": 15}
    est = per_1k_estimate(summary, price_per_1k_tokens=0.0002,
                          reviewer_minutes_each=3.0, reviewer_rate_per_hour=30.0,
                          basis="record")

    assert est["basis"] == "record"
    assert est["denominator"] == 50
    assert est["gated_calls_per_1k"] == 400.0
    assert abs(est["inference_usd"] - 0.02) < 1e-6
    assert abs(est["review_usd"] - 150.0) < 1e-6


def test_llm_everywhere_costs_more():
    summary = {"decisions_total": 100, "total_llm_tokens": 5000, "llm_calls": 15,
               "counts": {"auto_update": 10, "human_review": 5, "no_change": 85}}
    ours = per_1k_estimate(summary, price_per_1k_tokens=0.0002,
                           reviewer_minutes_each=3.0, reviewer_rate_per_hour=30.0)
    base = llm_everywhere_baseline(summary, price_per_1k_tokens=0.0002,
                                   mean_tokens_per_call=400)
    assert base["inference_usd"] > ours["inference_usd"]


def test_sweep_holds_conflict_reviews_constant():
    rows = [
        # conflict-forced review (npi != website), sub-threshold score: must stay
        # human_review at every auto_threshold — a source conflict is irreducible.
        {"decision": "human_review", "final_score": 0.40,
         "per_source": {"npi": "A", "website": "B"}},
        # score-driven review (npi == website) at 0.80: should convert to auto_update
        # once the auto_threshold drops to 0.75.
        {"decision": "human_review", "final_score": 0.80,
         "per_source": {"npi": "X", "website": "X"}},
    ]
    by_t = {row["auto_threshold"]: row for row in sweep_thresholds(rows, [0.75, 0.85], Config())}
    assert by_t[0.85]["human_review"] == 2   # conflict held + 0.80 score in review band
    assert by_t[0.75]["human_review"] == 1   # 0.80 score crosses to auto; conflict persists
    assert by_t[0.75]["auto_update"] == 1
