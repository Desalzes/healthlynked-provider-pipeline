"""$0 deterministic data-quality pre-pass — two named Bonus Points from the brief:

  * NPI validation: a check-digit (Luhn over the "80840"-prefixed 9-digit base)
    structural validator. Catches malformed/typo'd NPIs before any source lookup
    is spent on them.
  * Duplicate detection: record linkage over NPI, normalized phone, and
    normalized (name + address), unioned so duplicates surfaced by different
    signals collapse into one cluster.

Both run before the pipeline and cost nothing (no LLM, no network)."""
from __future__ import annotations
import re
from .schemas import ProviderRecord
from .normalize import normalize_phone, normalize_address_str

# CMS NPI check-digit constant: the 9-digit identifier is prefixed with this
# issuer code before the Luhn check, per the NPI standard (ISO 7812 / Luhn).
_NPI_PREFIX = "80840"
_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[.,]")


def validate_npi(npi) -> bool:
    """True iff `npi` is a 10-digit string whose final digit is the correct
    Luhn check digit over "80840" + the first nine digits. Surrounding whitespace
    is trimmed first (dirty ingest), but a non-string or any non-digit content is
    rejected."""
    if not isinstance(npi, str):
        return False
    npi = npi.strip()
    if len(npi) != 10 or not npi.isdigit():
        return False
    digits = _NPI_PREFIX + npi[:9]
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 0:        # double every second digit from the right
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (10 - total % 10) % 10 == int(npi[9])


def _name_key(name: str) -> str:
    return _WS.sub(" ", _PUNCT.sub("", (name or "").lower())).strip()


def find_duplicate_clusters(records: list[ProviderRecord]) -> list[list[str]]:
    """Cluster provider_ids that are likely the same provider/listing. Two records
    link if they share an NPI, a parseable phone, or a (name + address key);
    linkage is transitive (union-find), so a chain A~B~C collapses to one cluster.
    Returns only clusters with >1 member, ordered by first appearance.

    Precision note: this is a high-recall *candidate* flagger for human review, not
    an identity oracle. The signals trade precision for recall — a shared clinic
    switchboard phone can co-cluster distinct physicians, and exact name+address can
    over-merge same-named providers at one building. Production would add fuzzy
    blocking + probabilistic match scoring (e.g. Splink/Dedupe); see WRITEUP §8."""
    order = [r.provider_id for r in records]
    rank = {pid: i for i, pid in enumerate(order)}
    parent = {pid: pid for pid in order}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    by_npi: dict[str, list[str]] = {}
    by_phone: dict[str, list[str]] = {}
    by_name_addr: dict[tuple[str, str], list[str]] = {}
    for r in records:
        npi = (r.npi or "").strip()
        if npi:
            by_npi.setdefault(npi, []).append(r.provider_id)
        phone = normalize_phone(r.phone)
        if phone:
            by_phone.setdefault(phone, []).append(r.provider_id)
        name_key = _name_key(r.provider_name)
        addr = normalize_address_str(r.address)
        if name_key and addr:
            by_name_addr.setdefault((name_key, addr.key()), []).append(r.provider_id)

    for group in (*by_npi.values(), *by_phone.values(), *by_name_addr.values()):
        for other in group[1:]:
            union(group[0], other)

    clusters: dict[str, list[str]] = {}
    for pid in order:
        clusters.setdefault(find(pid), []).append(pid)
    result = [sorted(members, key=rank.__getitem__)
              for members in clusters.values() if len(members) > 1]
    result.sort(key=lambda c: rank[c[0]])
    return result


def data_quality_report(records: list[ProviderRecord]) -> dict:
    """A single $0 pre-pass report: which records have invalid NPIs and which are
    likely duplicates. Suitable for serializing to out/data_quality.json."""
    invalid = [r.provider_id for r in records if not validate_npi(r.npi)]
    clusters = find_duplicate_clusters(records)
    return {
        "records_total": len(records),
        "invalid_npi": invalid,
        "invalid_npi_count": len(invalid),
        "duplicate_clusters": clusters,
        "duplicate_record_count": sum(len(c) for c in clusters),
    }
