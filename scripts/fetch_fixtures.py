"""Operator-run: refresh demo fixtures with REAL captures.

- NPI Registry is a free public API: safe to fetch live and cache.
- Practice websites: fetched politely (robots.txt respected, 1 req / 3s).
Run intentionally; not part of the test/demo path.
"""
import json
import sys
import time
import urllib.robotparser as robotparser
from pathlib import Path
from urllib.parse import urlsplit
import httpx

ROOT = Path(__file__).resolve().parents[1] / "data" / "fixtures"
UA = "provider-pipeline-research/0.1 (Kaggle submission prototype)"


def fetch_npi(npi: str) -> None:
    r = httpx.get("https://npiregistry.cms.hhs.gov/api/",
                  params={"version": "2.1", "number": npi}, timeout=20.0)
    r.raise_for_status()
    out = ROOT / "npi" / f"{npi}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(r.json()), encoding="utf-8")
    print(f"npi {npi} -> {out}")


def _allowed(url: str) -> bool:
    parts = urlsplit(url)
    rp = robotparser.RobotFileParser()
    rp.set_url(f"{parts.scheme}://{parts.netloc}/robots.txt")
    try:
        rp.read()
    except Exception:
        return False
    return rp.can_fetch(UA, url)


def fetch_site(slug: str, url: str) -> None:
    if not _allowed(url):
        print(f"SKIP {slug}: robots.txt disallows {url}")
        return
    time.sleep(3.0)
    r = httpx.get(url, headers={"User-Agent": UA}, timeout=20.0, follow_redirects=True)
    r.raise_for_status()
    out = ROOT / "websites" / f"{slug}.html"
    out.write_text(r.text, encoding="utf-8")
    print(f"site {slug} -> {out}")


if __name__ == "__main__":
    # Usage: python scripts/fetch_fixtures.py npi 1234567890
    #        python scripts/fetch_fixtures.py site SLUG https://example.com/contact
    kind = sys.argv[1]
    if kind == "npi":
        fetch_npi(sys.argv[2])
    elif kind == "site":
        fetch_site(sys.argv[2], sys.argv[3])
    else:
        print("usage: fetch_fixtures.py {npi <npi> | site <slug> <url>}")
