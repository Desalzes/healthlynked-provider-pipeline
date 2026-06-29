"""Run the $0 data-quality pre-pass (NPI check-digit validation + duplicate
detection) over the planted demo set and write out/data_quality.json.

The planted set (data/dataquality_demo.json) deliberately contains one
invalid-check-digit NPI and two duplicate clusters (one surfaced by a shared
NPI, one by a shared name+address with different NPIs) so the pre-pass has
something to find. The pipeline's own 54-record synthetic corpus is left
untouched — this is a separate, focused demonstration of the validators.
"""
import json
from pathlib import Path
from provider_pipeline.schemas import ProviderRecord
from provider_pipeline.dataquality import data_quality_report

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "data" / "dataquality_demo.json"
OUT = ROOT / "out"


def main() -> None:
    records = [ProviderRecord(**r) for r in
               json.loads(DEMO.read_text(encoding="utf-8"))]
    report = data_quality_report(records)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "data_quality.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")

    print(f"records={report['records_total']} "
          f"invalid_npi={report['invalid_npi_count']} "
          f"duplicate_clusters={len(report['duplicate_clusters'])} "
          f"duplicate_records={report['duplicate_record_count']}")
    if report["invalid_npi"]:
        print("  invalid NPI:", ", ".join(report["invalid_npi"]))
    for cluster in report["duplicate_clusters"]:
        print("  duplicate cluster:", " == ".join(cluster))
    print("wrote out/data_quality.json")


if __name__ == "__main__":
    main()
