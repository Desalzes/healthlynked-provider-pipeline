from __future__ import annotations
from datetime import date, datetime
from typing import Literal, Optional
from pydantic import BaseModel

Decision = Literal["auto_update", "human_review", "no_change"]

# Internal source key -> sponsor's human-readable source name (for output).
SOURCE_DISPLAY: dict[str, str] = {
    "npi": "NPI Registry",
    "website": "Practice Website",
    "board": "State Medical Board",
    "snippet": "Web Search",
}


class ProviderRecord(BaseModel):
    """Pipeline input — mirrors the competition's example provider record exactly."""
    provider_id: str
    provider_name: str
    npi: str
    specialty: str
    practice_name: str
    address: str
    phone: str
    last_verified_date: date
    is_active: bool = True


class AddressTuple(BaseModel):
    street: str
    city: str
    state: str
    zip: str

    def key(self) -> str:
        return "|".join((self.street, self.city, self.state, self.zip)).lower()


class CanonicalRecord(BaseModel):
    npi: str
    full_name: str
    taxonomy: str
    addresses: list[AddressTuple]
    phone: Optional[str]
    is_active: bool
    fetched_at: datetime


class ContactTuple(BaseModel):
    address_line: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    phone: Optional[str] = None


class SourceObservation(BaseModel):
    source: str            # "npi" | "website" | "board" | "snippet"
    field: str             # "address" | "phone"
    value: Optional[str]   # normalized observed value, or None if silent
    freshness: float       # [0, 1]
    observed_at: datetime


class FieldChange(BaseModel):
    """Output-facing — matches the sponsor's example change object."""
    field: str
    old_value: str
    new_value: Optional[str]
    confidence_score: float
    supporting_sources: list[str]


class ChangeRecommendation(BaseModel):
    """Output-facing — matches the sponsor's example recommendation exactly."""
    provider_id: str
    npi: str
    change_detected: bool
    changes: list[FieldChange]
    overall_confidence: float
    recommended_action: Decision
    reason: str


class AuditRow(BaseModel):
    provider_id: str
    field: str
    old_value: Optional[str]
    new_value: Optional[str]
    per_source: dict[str, Optional[str]]
    per_source_weights: dict[str, float]
    per_source_freshness: dict[str, float]
    final_score: float
    decision: Decision
    llm_tokens: int
    gated_calls: int = 0   # number of paid LLM extraction stages invoked (website + snippet)
    wall_time_ms: int
    timestamp: datetime
