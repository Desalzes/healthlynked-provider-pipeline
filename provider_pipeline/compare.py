from __future__ import annotations
from typing import Optional
from .schemas import ProviderRecord, CanonicalRecord
from .normalize import normalize_address_str, normalize_phone


def field_existing(record: ProviderRecord, field: str) -> str:
    if field == "phone":
        return normalize_phone(record.phone) or ""
    addr = normalize_address_str(record.address)
    return addr.key() if addr else ""


def field_canonical(canonical: CanonicalRecord, field: str) -> Optional[str]:
    if field == "phone":
        return canonical.phone
    if not canonical.addresses:
        return None
    return canonical.addresses[0].key()


def _eq(a: Optional[str], b: Optional[str], field: str) -> bool:
    if a is None or b is None:
        return False
    if field == "phone":
        na = normalize_phone(a)
        return na is not None and na == normalize_phone(b)
    return a.strip().lower() == b.strip().lower()


def is_candidate_change(record: ProviderRecord, canonical: CanonicalRecord, field: str) -> bool:
    canon = field_canonical(canonical, field)
    if canon is None:
        return False  # NPI silent on this field -> handled by the silent path, not stage 3
    return not _eq(field_existing(record, field), canon, field)


def cross_source(npi_val: Optional[str], website_val: Optional[str],
                 existing_val: Optional[str], field: str) -> str:
    npi_eq_existing = _eq(npi_val, existing_val, field)
    web_eq_existing = _eq(website_val, existing_val, field)
    npi_eq_web = _eq(npi_val, website_val, field)
    if npi_eq_existing and web_eq_existing:
        return "no_change"
    if npi_eq_web and not npi_eq_existing:
        return "strong_update"
    if not npi_eq_existing and web_eq_existing:
        return "false_alarm"
    return "conflict"
