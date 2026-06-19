from __future__ import annotations
import json
from pathlib import Path
from .schemas import ProviderRecord
from .normalize import normalize_phone, normalize_address_str

SHOWCASE = {"SHOW-MOVE", "SHOW-AUTO", "SHOW-REVIEW", "SHOW-CONFLICT"}


def plan_routes(records: list[ProviderRecord]) -> dict[str, str]:
    routes: dict[str, str] = {}
    for i, r in enumerate(records):
        if r.provider_id in SHOWCASE:
            routes[r.provider_id] = {"SHOW-MOVE": "auto", "SHOW-AUTO": "auto",
                                     "SHOW-REVIEW": "review",
                                     "SHOW-CONFLICT": "conflict"}[r.provider_id]
        elif i % 7 == 0:
            routes[r.provider_id] = "auto"
        elif i % 11 == 0:
            routes[r.provider_id] = "review"
        elif i % 13 == 0:
            routes[r.provider_id] = "conflict"
        else:
            routes[r.provider_id] = "match"
    return routes


def _bump_phone(raw: str) -> str:
    return raw[:-4] + "9999"


def _third_phone(raw: str) -> str:
    return raw[:-4] + "8888"


def _fmt(raw: str) -> str:
    return f"({raw[:3]}) {raw[3:6]}-{raw[6:]}"


def _name_parts(provider_name: str) -> tuple[str, str]:
    toks = [t.strip(",").strip() for t in provider_name.split()]
    first = toks[0] if toks else ""
    last = toks[1] if len(toks) > 1 else ""
    return first, last


def _npi_payload(r: ProviderRecord, phone: str) -> dict:
    at = normalize_address_str(r.address)
    first, last = _name_parts(r.provider_name)
    return {"result_count": 1, "results": [{"number": r.npi,
            "basic": {"first_name": first.upper(), "last_name": last.upper(), "status": "A"},
            "taxonomies": [{"desc": r.specialty, "primary": True}],
            "addresses": [{"address_purpose": "LOCATION",
                           "address_1": (at.street if at else r.address),
                           "city": (at.city if at else ""),
                           "state": (at.state if at else ""),
                           "postal_code": (at.zip if at else ""),
                           "telephone_number": phone}]}]}


def build_fixtures(records: list[ProviderRecord], *, fixtures_dir: Path) -> dict[str, str]:
    fixtures_dir = Path(fixtures_dir)
    (fixtures_dir / "npi").mkdir(parents=True, exist_ok=True)
    (fixtures_dir / "websites").mkdir(parents=True, exist_ok=True)
    (fixtures_dir / "snippets").mkdir(parents=True, exist_ok=True)
    (fixtures_dir / "board").mkdir(parents=True, exist_ok=True)
    routes = plan_routes(records)
    for r in records:
        if r.provider_id in SHOWCASE:
            continue  # showcase fixtures are hand-pinned elsewhere
        kind = routes[r.provider_id]
        raw = normalize_phone(r.phone) or ""
        npi_phone = raw if kind == "match" else _bump_phone(raw)
        (fixtures_dir / "npi" / f"{r.npi}.json").write_text(
            json.dumps(_npi_payload(r, npi_phone)), encoding="utf-8")
        if kind == "match":
            continue
        web_phone = _third_phone(raw) if kind == "conflict" else _bump_phone(raw)
        (fixtures_dir / "websites" / f"{r.provider_id}.html").write_text(
            f"<html><body><h1>{r.provider_name}</h1>"
            f"<p>{r.address}</p>"
            f"<p>Call {_fmt(web_phone)}.</p></body></html>",
            encoding="utf-8")
        # "auto" records reach the auto bar via three AUTHORITATIVE sources
        # (NPI + Website + State Medical Board), so the snippet stage is never
        # needed for them. The board agrees on the new phone; the snippet stays
        # silent — demonstrating that the authoritative board, not the weak web
        # snippet, is the decisive third corroborator.
        if kind == "auto":
            (fixtures_dir / "board" / f"{r.provider_id}.json").write_text(
                json.dumps({"phone": _fmt(web_phone)}), encoding="utf-8")
        snippets = [f"{r.provider_name} {r.specialty} {r.address}"]
        (fixtures_dir / "snippets" / f"{r.provider_id}.json").write_text(
            json.dumps(snippets), encoding="utf-8")
    return routes
