from __future__ import annotations
import argparse
import json
from pathlib import Path
from datetime import date
from .config import Config
from .schemas import ProviderRecord
from .pipeline import select_stale
from .runner import build_deps, run_batch
from .audit import AuditLog


def _load_records(path: Path) -> list[ProviderRecord]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [ProviderRecord(**r) for r in raw]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Run the provider-directory update pipeline.")
    p.add_argument("--data", default="data/synthetic_providers.json")
    p.add_argument("--fixtures", default="data/fixtures")
    p.add_argument("--db", default="out/audit.db")
    p.add_argument("--cache", default="data/fixtures/_llm_cache")
    p.add_argument("--live", action="store_true", help="allow live NPI + LLM calls")
    p.add_argument("--fake-contacts", action="store_true",
                   help="offline regex extractor instead of the LLM (demo/CI)")
    p.add_argument("--show-examples", action="store_true")
    args = p.parse_args(argv)

    all_records = _load_records(args.data)
    # Stage 1: only records past the re-verification horizon enter the pipeline.
    records = select_stale(all_records, Config())
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    deps = build_deps(fixtures_dir=Path(args.fixtures), cache_dir=Path(args.cache),
                      live=args.live, fake_contacts=args.fake_contacts)
    log = AuditLog(args.db, fresh=True)
    summary = run_batch(records, deps, log)

    counts = summary["counts"]
    total = summary["decisions_total"]
    print(f"loaded={len(all_records)} stale_selected={len(records)} decisions={total} "
          f"auto={counts['auto_update']} review={counts['human_review']} "
          f"no_change={counts['no_change']}")
    print(f"llm_calls={summary['llm_calls']} total_tokens={summary['total_llm_tokens']} "
          f"mean_wall_ms={summary['mean_wall_ms']:.1f}")

    if args.show_examples:
        by_id = {rec.provider_id: rec for rec in summary["recommendations"]}
        for sid in ("SHOW-MOVE", "SHOW-AUTO", "SHOW-REVIEW", "SHOW-CONFLICT"):
            rec = by_id.get(sid)
            if rec:
                print(f"\n=== {sid} ===")
                print(json.dumps(rec.model_dump(mode="json"), indent=2))
    log.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
