"""Run the $0 duplicate-detection pre-pass over the synthetic directory and print
each candidate with its merge action and reason.

  python scripts/duplicate_report.py

Demonstrates the safety property: the directory's same-name clusters (distinct
NPIs) are all held for review, never auto-merged.
"""
import json
from collections import Counter
from pathlib import Path
from provider_pipeline.schemas import ProviderRecord
from provider_pipeline.dedupe import find_duplicate_candidates

DATA = Path(__file__).resolve().parents[1] / "data" / "synthetic_providers.json"


def main() -> int:
    records = [ProviderRecord(**r) for r in json.loads(DATA.read_text(encoding="utf-8"))]
    cands = find_duplicate_candidates(records)
    counts = Counter(c.merge_action for c in cands)
    print(f"records={len(records)} duplicate_candidates={len(cands)} "
          f"auto_merge={counts['auto_merge']} human_review={counts['human_review']} "
          f"no_merge={counts['no_merge']}")
    for c in cands:
        print(f"\n[{c.merge_action}] {', '.join(c.provider_ids)}")
        print(f"  matched_keys = {c.matched_keys}")
        print(f"  scores       = {c.score_components}")
        print(f"  reason       = {c.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
