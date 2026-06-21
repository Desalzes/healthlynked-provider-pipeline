"""Batch duplicate detection — a $0, deterministic pre-pass over the directory.

Runs before any LLM source extraction. Two blocking passes:

1. **Exact NPI collision** — two records carrying the same NPI are, by definition,
   the same provider -> ``auto_merge`` candidate.
2. **Same name + ZIP, distinct NPIs** — clinicians who merely share a name in one
   location are *different people*. They are surfaced as ``human_review`` candidates
   and **never auto-merged** (the core safety rule). A shared practice (or identical
   normalized address) is required as location corroboration so that common names in
   a ZIP are not over-linked.

Output is kept separate from the sponsor's field-change ``ChangeRecommendation`` so
it cannot collide with that contract.
"""
from __future__ import annotations
import re
from collections import defaultdict
from itertools import combinations
from rapidfuzz import fuzz
from .schemas import ProviderRecord, DuplicateCandidate
from .normalize import normalize_address_str

_CRED = re.compile(r"\b(md|do|dds|dmd|np|pa|rn|phd)\b", re.IGNORECASE)
_PUNCT = re.compile(r"[.,]")
_WS = re.compile(r"\s+")


def _name_key(name: str) -> str:
    """Normalize a provider name for blocking: drop punctuation and credential
    suffixes so 'John Cohen, MD' and 'John Cohen MD' collide."""
    s = _CRED.sub(" ", _PUNCT.sub(" ", (name or "").lower()))
    return _WS.sub(" ", s).strip()


def _zip_of(address: str) -> str:
    parsed = normalize_address_str(address)
    return parsed.zip if parsed else ""


def _addr_key(address: str) -> str:
    parsed = normalize_address_str(address)
    return parsed.key() if parsed else ""


def _practice_key(practice: str) -> str:
    return _WS.sub(" ", _PUNCT.sub(" ", (practice or "").lower())).strip()


def find_duplicate_candidates(records: list[ProviderRecord]) -> list[DuplicateCandidate]:
    candidates: list[DuplicateCandidate] = []

    # 1) Exact NPI collision -> same provider -> auto-merge.
    by_npi: dict[str, list[ProviderRecord]] = defaultdict(list)
    for r in records:
        if r.npi:
            by_npi[r.npi].append(r)
    for npi, group in by_npi.items():
        if len(group) > 1:
            ids = sorted(r.provider_id for r in group)
            candidates.append(DuplicateCandidate(
                provider_ids=ids, candidate_type="provider",
                matched_keys=["npi"], score_components={"npi_match": 1.0},
                merge_action="auto_merge",
                reason=f"Identical NPI {npi} on {len(ids)} records - the same provider."))

    # 2) Same name + ZIP, distinct NPIs -> different clinicians -> human review.
    by_identity: dict[tuple[str, str], list[ProviderRecord]] = defaultdict(list)
    for r in records:
        key = (_name_key(r.provider_name), _zip_of(r.address))
        if key[0] and key[1]:
            by_identity[key].append(r)
    for (_name, zip_), group in by_identity.items():
        if len(group) < 2 or len({r.npi for r in group}) < 2:
            continue
        practices = {_practice_key(r.practice_name) for r in group}
        addrs = {_addr_key(r.address) for r in group}
        if len(practices) > 1 and len(addrs) == len(group):
            continue  # no shared practice and every address differs -> too weak to flag
        ids = sorted(r.provider_id for r in group)
        ratio = max((fuzz.token_set_ratio(_name_key(a.provider_name), _name_key(b.provider_name))
                     for a, b in combinations(group, 2)), default=100) / 100.0
        candidates.append(DuplicateCandidate(
            provider_ids=ids, candidate_type="provider",
            matched_keys=["provider_name", "zip", "practice_name"],
            score_components={"npi_match": 0.0, "provider_name_ratio": round(ratio, 2)},
            merge_action="human_review",
            reason=(f"{len(ids)} records share name '{group[0].provider_name}' and ZIP "
                    f"{zip_} with distinct NPIs - manual verification; do not auto-merge.")))
    return candidates
