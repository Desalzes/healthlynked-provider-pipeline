from datetime import date, datetime, timezone
from pathlib import Path
from provider_pipeline.config import Config
from provider_pipeline.schemas import ProviderRecord, CanonicalRecord, AddressTuple, ContactTuple
from provider_pipeline.pipeline import Deps, run_record, to_recommendation, select_stale


def _rec(**o):
    base = dict(provider_id="P1", provider_name="J S", npi="1", specialty="FM",
                practice_name="Clinic", address="123 Main St, Naples, FL 34102",
                phone="2395550000", is_active=True, last_verified_date=date(2025, 1, 1))
    base.update(o)
    return ProviderRecord(**base)


def _canon(addr_street="123 main st", phone="2395550000", is_active=True):
    return CanonicalRecord(npi="1", full_name="J S", taxonomy="FM",
                           addresses=[AddressTuple(street=addr_street, city="naples", state="fl", zip="34102")],
                           phone=phone, is_active=is_active, fetched_at=datetime.now(timezone.utc))


def _deps(canonical, website=ContactTuple(), snippet=ContactTuple(),
          board=ContactTuple(), cache=Path(".")):
    return Deps(
        cfg=Config(),
        fetch_canonical=lambda npi: canonical,
        extract_website=lambda record: (website, 30),
        extract_snippet=lambda record: (snippet, 20),
        extract_board=lambda record: (board, 0),
        cache_dir=cache,
    )


def test_clean_record_is_no_change_zero_tokens(tmp_path):
    rec, _rows, telem = run_record(_rec(), _deps(_canon(), cache=tmp_path))
    assert all(c.decision == "no_change" for c in rec.changes)
    assert telem["llm_tokens"] == 0


def test_conflict_forces_human_review(tmp_path):
    # NPI says new phone, website says a THIRD value -> conflict
    canon = _canon(phone="2395559999")
    deps = _deps(canon, website=ContactTuple(phone="2395558888"), cache=tmp_path)
    rec, _rows, _t = run_record(_rec(), deps)
    phone_change = next(c for c in rec.changes if c.field == "phone")
    assert phone_change.decision == "human_review"


def test_board_three_authoritative_sources_auto_without_snippet(tmp_path):
    # NPI + Website + State Medical Board agree -> 1.0 -> auto, and the snippet
    # stage is never invoked (no token spend beyond the website call).
    canon = _canon(phone="2395559999")
    deps = _deps(canon, website=ContactTuple(phone="2395559999"),
                 board=ContactTuple(phone="2395559999"), cache=tmp_path)
    rec, rows, telem = run_record(_rec(), deps)
    phone_change = next(c for c in rec.changes if c.field == "phone")
    assert phone_change.decision == "auto_update"
    assert phone_change.confidence == 1.0
    assert telem["llm_tokens"] == 30   # website only; snippet skipped
    phone_row = next(r for r in rows if r.field == "phone")
    assert phone_row.gated_calls == 1  # one paid stage (website), board is free


def test_snippet_fallback_auto_updates_when_board_silent(tmp_path):
    # Board silent: NPI + Website = 0.80 < 0.85, so the snippet runs and tips it
    # to 0.90 -> auto. Two paid stages.
    canon = _canon(phone="2395559999")
    deps = _deps(canon, website=ContactTuple(phone="2395559999"),
                 snippet=ContactTuple(phone="2395559999"), cache=tmp_path)
    rec, rows, telem = run_record(_rec(), deps)
    phone_change = next(c for c in rec.changes if c.field == "phone")
    assert phone_change.decision == "auto_update"
    assert telem["llm_tokens"] == 50   # website(30) + snippet(20)
    phone_row = next(r for r in rows if r.field == "phone")
    assert phone_row.gated_calls == 2


def test_false_alarm_board_confirming_npi_is_human_review(tmp_path):
    # Website still shows the old value, but NPI and State Medical Board agree on
    # a new value. That is not a no-change false alarm; it needs review.
    canon = _canon(phone="2395559999")
    deps = _deps(canon, website=ContactTuple(phone="2395550000"),
                 board=ContactTuple(phone="2395559999"), cache=tmp_path)
    result, rows, _t = run_record(_rec(), deps)
    rec = to_recommendation(result, _rec())
    phone_row = next(r for r in rows if r.field == "phone")
    assert phone_row.decision == "human_review"
    assert rec.change_detected is True
    assert rec.recommended_action == "human_review"
    assert "disagree" in rec.reason


def test_board_disagreement_blocks_snippet_auto_update(tmp_path):
    # The weak snippet fallback must not outvote an authoritative board value.
    calls = {"snippet": 0}

    def snippet(_record):
        calls["snippet"] += 1
        return ContactTuple(phone="2395559999"), 20

    canon = _canon(phone="2395559999")
    deps = Deps(cfg=Config(), fetch_canonical=lambda npi: canon,
                extract_website=lambda record: (ContactTuple(phone="2395559999"), 30),
                extract_board=lambda record: (ContactTuple(phone="2395550000"), 0),
                extract_snippet=snippet, cache_dir=tmp_path)
    result, rows, _t = run_record(_rec(), deps)
    rec = to_recommendation(result, _rec())
    phone_row = next(r for r in rows if r.field == "phone")
    assert calls["snippet"] == 0
    assert phone_row.decision == "human_review"
    assert rec.recommended_action == "human_review"
    assert "State Medical Board" not in rec.changes[0].supporting_sources
    assert "disagree" in rec.reason


def test_stale_npi_freshness_reduces_confidence(tmp_path):
    old_canon = _canon(phone="2395559999")
    old_canon.fetched_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    deps = _deps(old_canon, website=ContactTuple(phone="2395559999"),
                 board=ContactTuple(phone="2395559999"), cache=tmp_path)
    _result, rows, _t = run_record(_rec(), deps)
    phone_row = next(r for r in rows if r.field == "phone")
    assert phone_row.per_source_freshness["npi"] < 0.01
    assert phone_row.final_score < Config().auto_threshold
    assert phone_row.decision == "human_review"


def test_no_change_row_reports_stale_npi_freshness(tmp_path):
    old_canon = _canon(phone="2395550000")
    old_canon.fetched_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    deps = _deps(old_canon, cache=tmp_path)
    _result, rows, _t = run_record(_rec(), deps)
    phone_row = next(r for r in rows if r.field == "phone")
    assert phone_row.decision == "no_change"
    assert phone_row.per_source_freshness["npi"] < 0.01


def test_is_active_flip_is_deterministic_auto_update(tmp_path):
    canon = _canon(is_active=False)
    rec, _rows, telem = run_record(_rec(is_active=True), _deps(canon, cache=tmp_path))
    active_change = next(c for c in rec.changes if c.field == "is_active")
    assert active_change.decision == "auto_update"
    assert active_change.confidence == 1.0
    assert telem["llm_tokens"] == 0   # deterministic, no LLM


def test_to_recommendation_auto_update_shape(tmp_path):
    canon = _canon(phone="2395559999")
    deps = _deps(canon, website=ContactTuple(phone="2395559999"),
                 board=ContactTuple(phone="2395559999"), cache=tmp_path)
    rec_in = _rec()
    result, _rows, _t = run_record(rec_in, deps)
    rec = to_recommendation(result, rec_in)
    assert rec.change_detected is True
    assert rec.recommended_action == "auto_update"
    phone_change = next(c for c in rec.changes if c.field == "phone")
    assert phone_change.confidence_score == 1.0
    assert "NPI Registry" in phone_change.supporting_sources
    assert "Practice Website" in phone_change.supporting_sources
    assert "State Medical Board" in phone_change.supporting_sources
    assert set(rec.model_dump().keys()) == {
        "provider_id", "npi", "change_detected", "changes",
        "overall_confidence", "recommended_action", "reason"}


def test_to_recommendation_conflict_is_human_review(tmp_path):
    canon = _canon(phone="2395559999")
    deps = _deps(canon, website=ContactTuple(phone="2395558888"), cache=tmp_path)
    rec_in = _rec()
    result, _rows, _t = run_record(rec_in, deps)
    rec = to_recommendation(result, rec_in)
    assert rec.recommended_action == "human_review"
    assert rec.change_detected is True
    # Genuine three-way disagreement -> "disagree" wording.
    assert "disagree" in rec.reason


def test_under_corroborated_review_reason_says_agree_not_disagree(tmp_path):
    # NPI and website AGREE on a new phone, but with no third source the score
    # caps at 0.80 (< auto) -> human_review that is NOT a disagreement.
    canon = _canon(phone="2395559999")
    deps = _deps(canon, website=ContactTuple(phone="2395559999"), cache=tmp_path)
    rec_in = _rec()
    result, _rows, _t = run_record(rec_in, deps)
    rec = to_recommendation(result, rec_in)
    assert rec.recommended_action == "human_review"
    assert "agree" in rec.reason and "disagree" not in rec.reason


def test_select_stale_filters_fresh_records():
    cfg = Config()  # stale_days=180
    today = date(2025, 1, 1)
    fresh = _rec(provider_id="FRESH", last_verified_date=date(2024, 12, 1))   # ~31d
    stale = _rec(provider_id="STALE", last_verified_date=date(2024, 1, 1))    # ~366d
    selected = select_stale([fresh, stale], cfg, today=today)
    ids = [r.provider_id for r in selected]
    assert ids == ["STALE"]


def test_to_recommendation_address_change_is_human_readable(tmp_path):
    canon = _canon(addr_street="500 oak ave", phone="2395550000")
    deps = _deps(canon, website=ContactTuple(address_line="500 Oak Ave", city="Naples",
                 state="FL", zip="34102"), cache=tmp_path)
    rec_in = _rec()
    result, _rows, _t = run_record(rec_in, deps)
    rec = to_recommendation(result, rec_in)
    addr_change = next(c for c in rec.changes if c.field == "address")
    assert "|" not in addr_change.old_value
    assert "|" not in (addr_change.new_value or "")
    assert addr_change.old_value == "123 Main St, Naples, FL 34102"
