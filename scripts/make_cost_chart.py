import csv
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from provider_pipeline.config import Config
from provider_pipeline.audit import AuditLog
from provider_pipeline.cost import per_1k_estimate, llm_everywhere_baseline, sweep_thresholds

OUT = Path(__file__).resolve().parents[1] / "out"


def main() -> None:
    log = AuditLog(OUT / "audit.db")
    summary = log.summary()
    rows = log.all()
    log.close()

    if summary["decisions_total"] == 0:
        raise SystemExit(
            "out/audit.db is empty - run `python -m provider_pipeline.cli "
            "--fake-contacts` first to populate the audit log, then re-run this script."
        )

    decision_est = per_1k_estimate(summary, price_per_1k_tokens=0.0002,
                                   reviewer_minutes_each=3.0, reviewer_rate_per_hour=30.0,
                                   mean_tokens_per_call=400)
    record_est = per_1k_estimate(summary, price_per_1k_tokens=0.0002,
                                 reviewer_minutes_each=3.0, reviewer_rate_per_hour=30.0,
                                 mean_tokens_per_call=400, basis="record")
    base = llm_everywhere_baseline(summary, price_per_1k_tokens=0.0002, mean_tokens_per_call=400)

    # tier-split bar
    counts = summary["counts"]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(list(counts.keys()), list(counts.values()), color=["#2a9d8f", "#e9c46a", "#264653"])
    ax.set_title(f"Routing split ({summary['records_total']} records / {summary['decisions_total']} decisions)  "
                 f"inference ${record_est['inference_usd']:.4f}/1k records vs "
                 f"LLM-everywhere ${base['inference_usd']:.4f}/1k records")
    ax.set_ylabel("decisions")
    fig.tight_layout()
    fig.savefig(OUT / "cost_telemetry.png", dpi=120)

    # sensitivity sweep
    sweep = sweep_thresholds(rows, [0.75, 0.80, 0.85, 0.90], Config())
    with open(OUT / "sensitivity.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["auto_threshold", "auto_update", "human_review", "no_change"])
        w.writeheader()
        w.writerows(sweep)
    print("wrote out/cost_telemetry.png and out/sensitivity.csv")
    print("per-1k decisions:", decision_est)
    print("per-1k records:", record_est)
    print("baseline:", base)


if __name__ == "__main__":
    main()
