"""Run the sponsor's LITERAL HL_001 example through the unmodified pipeline.

The brief gives one concrete example (``data/example_record.json``): an address
change corroborated by NPI + Practice Website + State Medical Board (3 sources)
and a phone change corroborated by Practice Website + NPI (2 sources). Rather than
reshape that example, this module encodes *exactly* those sources and feeds the
literal record to ``run_record`` via the normal dependency seam — so the
submission can show, transparently, what the pipeline does with the brief's own
example at both the default and the sponsor's risk-appetite threshold.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import Config
from .pipeline import Deps
from .schemas import ProviderRecord, CanonicalRecord, ContactTuple
from .normalize import normalize_phone, normalize_address_str

_DATA = Path(__file__).resolve().parents[1] / "data" / "example_record.json"

# The sponsor's expected NEW values for HL_001 (from example_output_auto_update).
NEW_ADDRESS = "250 Health Park Dr, Fort Myers, FL 33908"
NEW_PHONE = "239-555-9000"


def hl001_input() -> ProviderRecord:
    """The sponsor's literal HL_001 input record (data/example_record.json)."""
    raw = json.loads(_DATA.read_text(encoding="utf-8"))
    return ProviderRecord(**raw["example_input"])


def _move_contact(*, with_phone: bool) -> ContactTuple:
    return ContactTuple(
        address_line="250 Health Park Dr", city="Fort Myers", state="FL", zip="33908",
        phone=NEW_PHONE if with_phone else None,
    )


def hl001_deps(cfg: Optional[Config] = None) -> Deps:
    """Deps wired to the sponsor's own cited corroboration for HL_001:

    - NPI Registry  -> new address AND new phone
    - Practice Website -> new address AND new phone
    - State Medical Board -> new ADDRESS only (no phone) — so phone has just 2 sources
    - Web snippet -> silent

    Nothing is reshaped: the phone deliberately has only the two sources the
    sponsor's example lists (Website + NPI), which is the case our default holds.
    """
    cfg = cfg or Config()
    now = datetime.now(timezone.utc)
    addr = normalize_address_str(NEW_ADDRESS)
    canonical = CanonicalRecord(
        npi="1234567890", full_name="John Smith, MD", taxonomy="Cardiology",
        addresses=[addr] if addr else [], phone=normalize_phone(NEW_PHONE),
        is_active=True, fetched_at=now,
    )
    return Deps(
        cfg=cfg,
        fetch_canonical=lambda npi: canonical,
        extract_website=lambda record: (_move_contact(with_phone=True), 0),
        extract_snippet=lambda record: (ContactTuple(), 0),
        extract_board=lambda record: (_move_contact(with_phone=False), 0),
        cache_dir=_DATA.parent,
    )
