"""Run the sponsor's LITERAL HL_001 example through the unmodified pipeline at two
thresholds, so the divergence from the brief's example is shown, not hidden.

  default (0.85): the 2-source phone (Website + NPI) is held for human review,
                  so the record routes to human_review at overall_confidence 0.90.
  0.80          : the same record matches the sponsor's expected auto_update,
                  also at overall_confidence 0.90.

Run from the repo root:  python scripts/sponsor_example_demo.py
"""
import dataclasses
import json
from provider_pipeline.config import Config
from provider_pipeline.sponsor_example import hl001_input, hl001_deps
from provider_pipeline.pipeline import run_record, to_recommendation


def _run(cfg: Config):
    rec = hl001_input()
    result, _rows, _telem = run_record(rec, hl001_deps(cfg))
    return to_recommendation(result, rec)


def main() -> int:
    cases = [
        ("default auto_threshold = 0.85", Config()),
        ("auto_threshold = 0.80 (the sponsor's risk appetite)",
         dataclasses.replace(Config(), auto_threshold=0.80)),
    ]
    for label, cfg in cases:
        rec = _run(cfg)
        print(f"\n=== literal HL_001 @ {label} ===")
        print(f"recommended_action = {rec.recommended_action}   "
              f"overall_confidence = {rec.overall_confidence}")
        print(json.dumps(rec.model_dump(mode="json"), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
