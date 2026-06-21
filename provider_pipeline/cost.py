from __future__ import annotations
from copy import deepcopy
from pathlib import Path
from .config import Config
from .confidence import route


def per_1k_estimate(summary: dict, *, price_per_1k_tokens: float,
                    reviewer_minutes_each: float, reviewer_rate_per_hour: float,
                    mean_tokens_per_call: int = 400,
                    basis: str = "decision") -> dict:
    if basis not in {"decision", "record"}:
        raise ValueError("basis must be 'decision' or 'record'")
    if basis == "record":
        n = summary.get("records_total") or summary["decisions_total"] or 1
    else:
        n = summary["decisions_total"] or 1
    scale = 1000.0 / n
    gated_calls_per_1k = summary.get("gated_calls_total", 0) * scale
    observed_tokens_per_1k = summary["total_llm_tokens"] * scale
    # Inference dollars are modeled from the MEASURED count of gated LLM-stage calls
    # (website + snippet). A non-fake LLM run records real token usage and we use
    # that; the offline demo spends $0, so we estimate from measured gated calls x
    # mean tokens/call rather than a hand-picked fraction.
    modeled_tokens_per_1k = gated_calls_per_1k * mean_tokens_per_call
    tokens_per_1k = observed_tokens_per_1k if observed_tokens_per_1k > 0 else modeled_tokens_per_1k
    reviews_per_1k = summary["counts"]["human_review"] * scale
    inference = (tokens_per_1k / 1000.0) * price_per_1k_tokens
    review = (reviews_per_1k * reviewer_minutes_each / 60.0) * reviewer_rate_per_hour
    return {"basis": basis, "denominator": n,
            "inference_usd": round(inference, 6), "review_usd": round(review, 4),
            "total_usd": round(inference + review, 4),
            "tokens_per_1k": round(tokens_per_1k, 1),
            "gated_calls_per_1k": round(gated_calls_per_1k, 1),
            "observed_tokens_per_1k": round(observed_tokens_per_1k, 1),
            "reviews_per_1k": round(reviews_per_1k, 1)}


def llm_everywhere_baseline(summary: dict, *, price_per_1k_tokens: float,
                            mean_tokens_per_call: int) -> dict:
    # one LLM call per record, every field -> approx 2 calls/record for address+phone
    tokens_per_1k = 1000 * 2 * mean_tokens_per_call
    inference = (tokens_per_1k / 1000.0) * price_per_1k_tokens
    return {"inference_usd": round(inference, 6), "tokens_per_1k": tokens_per_1k}


def _is_conflict_forced(r: dict) -> bool:
    # Conflict is the only routing path that forces human_review regardless of
    # score, and it always leaves npi/website disagreeing in per_source — so this
    # uniquely identifies a deterministic, threshold-independent review.
    ps = r["per_source"]
    return (r["decision"] == "human_review"
            and ps.get("npi") is not None and ps.get("website") is not None
            and ps["npi"] != ps["website"])


def sweep_thresholds(rows: list[dict], thresholds: list[float], cfg: Config) -> list[dict]:
    out = []
    for t in thresholds:
        c = deepcopy(cfg)
        object.__setattr__(c, "auto_threshold", t)
        counts = {"auto_update": 0, "human_review": 0, "no_change": 0}
        for r in rows:
            if _is_conflict_forced(r):
                counts["human_review"] += 1
                continue
            counts[route(r["final_score"], c)] += 1
        out.append({"auto_threshold": t, **counts})
    return out
