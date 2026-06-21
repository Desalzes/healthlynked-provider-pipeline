"""Batch duplicate detection — a $0 deterministic pre-pass over the directory.

The core safety property: two records with the SAME NPI are the same provider
(auto-merge candidate); records that merely share a name + location but have
DISTINCT NPIs are different clinicians and must NEVER be auto-merged — they are
held for human review. The synthetic directory contains exactly the second case
(e.g. three "John Cohen, MD" in Tampa Medical Group, distinct NPIs).
"""
import json
from datetime import date
from pathlib import Path
from provider_pipeline.schemas import ProviderRecord
from provider_pipeline.dedupe import find_duplicate_candidates

ROOT = Path(__file__).resolve().parents[1]


def _rec(pid, name, npi, practice, address, phone="813-555-0000"):
    return ProviderRecord(provider_id=pid, provider_name=name, npi=npi,
                          specialty="Cardiology", practice_name=practice,
                          address=address, phone=phone, last_verified_date=date(2023, 1, 1))


def test_same_npi_is_auto_merge_candidate():
    a = _rec("P1", "John Cohen, MD", "1030824628", "Tampa Medical Group", "100 Main St, Tampa, FL 33602")
    b = _rec("P2", "J. Cohen MD", "1030824628", "Tampa Medical Group", "100 Main St, Tampa, FL 33602")
    cands = find_duplicate_candidates([a, b])
    assert len(cands) == 1
    c = cands[0]
    assert set(c.provider_ids) == {"P1", "P2"}
    assert c.merge_action == "auto_merge"
    assert "npi" in c.matched_keys


def test_same_name_zip_distinct_npi_is_review_never_auto_merge():
    a = _rec("P0001", "John Cohen, MD", "1030824628", "Tampa Medical Group", "10 A St, Tampa, FL 33602")
    b = _rec("P0002", "John Cohen, MD", "1579754323", "Tampa Medical Group", "20 B St, Tampa, FL 33602")
    c = _rec("P0036", "John Cohen, MD", "1046557210", "Tampa Medical Group", "30 C St, Tampa, FL 33602")
    cands = find_duplicate_candidates([a, b, c])
    assert len(cands) == 1
    cand = cands[0]
    assert set(cand.provider_ids) == {"P0001", "P0002", "P0036"}
    assert cand.merge_action == "human_review"
    assert cand.merge_action != "auto_merge"   # the hard safety rule


def test_unrelated_records_produce_no_candidate():
    a = _rec("P1", "John Cohen, MD", "1030824628", "Tampa Medical Group", "10 A St, Tampa, FL 33602")
    b = _rec("P2", "Maria Garcia, MD", "1579754323", "Denver Medical Group", "99 Z St, Denver, CO 80202")
    assert find_duplicate_candidates([a, b]) == []


def test_full_synthetic_set_holds_clusters_with_zero_false_auto_merge():
    recs = [ProviderRecord(**r) for r in
            json.loads((ROOT / "data" / "synthetic_providers.json").read_text(encoding="utf-8"))]
    cands = find_duplicate_candidates(recs)
    assert cands, "expected the known same-name clusters to surface"
    # Every real cluster has distinct NPIs -> not a single auto-merge may fire.
    assert all(c.merge_action == "human_review" for c in cands)
    flat_ids = {pid for c in cands for pid in c.provider_ids}
    assert {"P0001", "P0002", "P0036"} <= flat_ids   # the John Cohen cluster is caught
