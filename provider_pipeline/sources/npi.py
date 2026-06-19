from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import httpx
from ..schemas import CanonicalRecord, AddressTuple
from ..normalize import normalize_phone

API = "https://npiregistry.cms.hhs.gov/api/"


def parse_npi_response(payload: dict) -> Optional[CanonicalRecord]:
    if not payload.get("result_count") or not payload.get("results"):
        return None
    r = payload["results"][0]
    basic = r.get("basic", {})
    name = " ".join(p for p in [basic.get("first_name"), basic.get("last_name")] if p).title()
    taxes = r.get("taxonomies", [])
    taxonomy = next((t["desc"] for t in taxes if t.get("primary")), taxes[0]["desc"] if taxes else "")
    addrs, phone = [], None
    for a in r.get("addresses", []):
        if a.get("address_purpose") == "LOCATION":
            addrs.append(AddressTuple(
                street=(a.get("address_1") or "").lower().strip(),
                city=(a.get("city") or "").lower().strip(),
                state=(a.get("state") or "").lower().strip(),
                zip=(a.get("postal_code") or "")[:5],
            ))
            if a.get("telephone_number") and phone is None:
                phone = normalize_phone(a["telephone_number"])
    return CanonicalRecord(
        npi=str(r.get("number")),
        full_name=name,
        taxonomy=taxonomy,
        addresses=addrs,
        phone=phone,
        is_active=(basic.get("status") == "A"),
        fetched_at=datetime.now(timezone.utc),
    )


def fetch_canonical(npi: str, *, cache_dir: Path, live: bool = False,
                    client: Optional[httpx.Client] = None) -> Optional[CanonicalRecord]:
    cache_dir = Path(cache_dir)
    cache_file = cache_dir / f"{npi}.json"
    if cache_file.exists():
        return parse_npi_response(json.loads(cache_file.read_text(encoding="utf-8")))
    if not live:
        return None
    owns = client is None
    client = client or httpx.Client(timeout=20.0)
    try:
        resp = client.get(API, params={"version": "2.1", "number": npi})
        resp.raise_for_status()
        payload = resp.json()
    finally:
        if owns:
            client.close()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(payload), encoding="utf-8")
    return parse_npi_response(payload)
