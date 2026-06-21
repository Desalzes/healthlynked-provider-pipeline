from __future__ import annotations
import re
from pathlib import Path
from typing import Optional
from .config import Config
from .schemas import ProviderRecord, ContactTuple
from .pipeline import Deps, run_record, to_recommendation
from .audit import AuditLog
from .sources.npi import fetch_canonical
from .sources.website import extract_from_practice_site, load_fixture as load_html
from .sources.snippet import extract_from_snippets, load_fixture as load_snips
from .sources.board import load_board

_PHONE_RE = re.compile(r"\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}")
# "<street>, <city>, <ST> <zip>" — the single-line US address shape used in the
# fixtures and the sponsor's example record.
_ADDR_RE = re.compile(r"(\d+[^,<\n]+?),\s*([A-Za-z][A-Za-z .'-]+?),\s*([A-Z]{2})\s+(\d{5})")


def _regex_contact(text: str) -> ContactTuple:
    """Offline, $0 extractor (used by --fake-contacts) — a deterministic stand-in
    for the LLM that pulls a phone AND a single-line address from fixture text, so
    the offline demo exercises the address path, not just phone."""
    phone = _PHONE_RE.search(text)
    addr = _ADDR_RE.search(text)
    return ContactTuple(
        phone=phone.group(0) if phone else None,
        address_line=addr.group(1).strip() if addr else None,
        city=addr.group(2).strip() if addr else None,
        state=addr.group(3).strip() if addr else None,
        zip=addr.group(4).strip() if addr else None,
    )


def build_deps(*, fixtures_dir: Path, cache_dir: Path, live: bool,
               fake_contacts: bool = False) -> Deps:
    cfg = Config()
    fixtures_dir = Path(fixtures_dir)

    def fetch(npi: str):
        return fetch_canonical(npi, cache_dir=fixtures_dir / "npi", live=live)

    def website(record: ProviderRecord):
        html = load_html(record.provider_id, fixtures_dir=fixtures_dir / "websites")
        if html is None:
            return ContactTuple(), 0
        if fake_contacts:
            return _regex_contact(html), 0
        return extract_from_practice_site(html, model=cfg.llm_model, cache_dir=cache_dir)

    def snippet(record: ProviderRecord):
        snips = load_snips(record.provider_id, fixtures_dir=fixtures_dir / "snippets")
        if not snips:
            return ContactTuple(), 0
        if fake_contacts:
            return _regex_contact(" ".join(snips)), 0
        return extract_from_snippets(snips, model=cfg.llm_model, cache_dir=cache_dir)

    def board(record: ProviderRecord):
        # Free, deterministic authoritative source — no LLM, $0, even when live.
        return load_board(record.provider_id, fixtures_dir=fixtures_dir / "board"), 0

    return Deps(cfg=cfg, fetch_canonical=fetch, extract_website=website,
               extract_snippet=snippet, extract_board=board, cache_dir=cache_dir)


def run_batch(records: list[ProviderRecord], deps: Deps, log: AuditLog) -> dict:
    recommendations = []
    errors: list[dict] = []
    for r in records:
        try:
            rec, rows, _telem = run_record(r, deps)
        except Exception as exc:  # one bad record (e.g. a live LLM/network error)
            # must not abort the whole batch — log it, keep an auditable trace, continue.
            errors.append({"provider_id": r.provider_id, "error": f"{type(exc).__name__}: {exc}"})
            continue
        recommendations.append(to_recommendation(rec, r))
        for row in rows:
            log.write(row)
    summary = log.summary()
    summary["recommendations"] = recommendations
    summary["errors"] = errors
    summary["input_records_total"] = len(records)
    summary["processed_records_total"] = len(recommendations)
    summary["error_records_total"] = len(errors)
    return summary
