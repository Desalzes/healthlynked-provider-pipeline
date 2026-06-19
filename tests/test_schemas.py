from datetime import date, datetime
from provider_pipeline.schemas import (
    ProviderRecord, FieldChange, ChangeRecommendation, SOURCE_DISPLAY,
)


def _record(**over):
    base = dict(
        provider_id="HL_001", provider_name="John Smith, MD", npi="1234567890",
        specialty="Cardiology", practice_name="ABC Heart Group",
        address="100 Main St, Naples, FL 34102", phone="239-555-1234",
        last_verified_date=date(2023, 9, 1),
    )
    base.update(over)
    return ProviderRecord(**base)


def test_provider_record_roundtrips():
    r = _record()
    assert r.npi == "1234567890"
    assert r.is_active is True  # defaults True when sponsor input omits it
    assert ProviderRecord.model_validate(r.model_dump()) == r


def test_field_change_matches_sponsor_shape():
    fc = FieldChange(
        field="address", old_value="100 Main St, Naples, FL 34102",
        new_value="250 Health Park Dr, Fort Myers, FL 33908",
        confidence_score=0.92,
        supporting_sources=["NPI Registry", "Practice Website"],
    )
    assert fc.confidence_score == 0.92
    assert "NPI Registry" in fc.supporting_sources


def test_change_recommendation_serializes_to_sponsor_keys():
    rec = ChangeRecommendation(
        provider_id="HL_001", npi="1234567890", change_detected=False,
        changes=[], overall_confidence=0.0, recommended_action="no_change",
        reason="No change detected.",
    )
    dumped = rec.model_dump(mode="json")
    assert dumped["provider_id"] == "HL_001"
    assert dumped["change_detected"] is False
    assert dumped["recommended_action"] == "no_change"
    assert dumped["changes"] == []
    assert set(dumped) == {
        "provider_id", "npi", "change_detected", "changes",
        "overall_confidence", "recommended_action", "reason",
    }


def test_source_display_map():
    assert SOURCE_DISPLAY["npi"] == "NPI Registry"
    assert SOURCE_DISPLAY["website"] == "Practice Website"
    assert SOURCE_DISPLAY["board"] == "State Medical Board"
    assert SOURCE_DISPLAY["snippet"] == "Web Search"
