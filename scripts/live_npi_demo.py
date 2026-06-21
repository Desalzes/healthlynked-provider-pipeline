"""Prove the NPI seam end-to-end against the REAL, free CMS NPI Registry.

Runs the $0 structural pre-filter (CMS check digit) and then a live NPPES lookup
for one NPI, printing the normalized CanonicalRecord the pipeline would consume.
Everywhere else the demo runs offline on fixtures for reproducibility; this script
is the one place that touches the live registry, to show the injected source is
real, not vaporware.

  python scripts/live_npi_demo.py [NPI]      # default: a real Fort Myers, FL org

Re-runs are free: the response is cached under out/_live_npi/ (the same
prompt/identity cache the production design relies on).
"""
import sys
from pathlib import Path
from provider_pipeline.sources.npi import validated_fetch

DEFAULT_NPI = "1760081806"  # a real organizational NPI (NPPES), not an individual
CACHE = Path(__file__).resolve().parents[1] / "out" / "_live_npi"


def main(argv: list[str]) -> int:
    npi = (argv[0] if argv else DEFAULT_NPI).strip()
    ok, rec = validated_fetch(npi, cache_dir=CACHE, live=True)
    print(f"NPI {npi}")
    print(f"  check_digit_valid : {ok}")
    if not ok:
        print("  -> rejected by the $0 pre-filter; no registry call made.")
        return 0
    if rec is None:
        print("  -> valid format, but no NPPES record found (result_count 0).")
        return 0
    addr = rec.addresses[0] if rec.addresses else None
    print(f"  full_name         : {rec.full_name}")
    print(f"  taxonomy          : {rec.taxonomy}")
    print(f"  is_active         : {rec.is_active}")
    print(f"  phone             : {rec.phone}")
    if addr:
        print(f"  location          : {addr.street}, {addr.city}, {addr.state} {addr.zip}")
    print(f"  fetched_at        : {rec.fetched_at.isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
