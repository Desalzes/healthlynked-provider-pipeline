from __future__ import annotations
import random
from datetime import date, timedelta
from .schemas import ProviderRecord

_FIRST = ["Jane", "John", "Maria", "David", "Aisha", "Liang", "Sofia", "Omar"]
_LAST = ["Smith", "Patel", "Nguyen", "Garcia", "Cohen", "Okafor", "Rossi", "Khan"]
_SPECIALTY = ["Family Medicine", "Internal Medicine", "Pediatrics", "Cardiology"]
_STREETS = ["Main St", "Oak Ave", "Pine Rd", "Elm Blvd", "Cedar Ln"]
_CITIES = [("Naples", "FL", "34102"), ("Austin", "TX", "78701"),
           ("Denver", "CO", "80202"), ("Tampa", "FL", "33602")]


def _phone(rng):
    d = "".join(str(rng.randint(0, 9)) for _ in range(10))
    return f"{d[:3]}-{d[3:6]}-{d[6:]}"


def _npi(rng):
    return "1" + "".join(str(rng.randint(0, 9)) for _ in range(9))


def _showcase() -> list[ProviderRecord]:
    return [
        ProviderRecord(provider_id="SHOW-AUTO", provider_name="Jane Smith, MD", npi="1111111111",
                       specialty="Family Medicine", practice_name="Naples Family Care",
                       address="123 Main St, Naples, FL 34102", phone="239-555-0000",
                       is_active=True, last_verified_date=date(2024, 1, 1)),
        ProviderRecord(provider_id="SHOW-REVIEW", provider_name="John Patel, MD", npi="2222222222",
                       specialty="Cardiology", practice_name="Austin Heart Institute",
                       address="9 Pine Rd, Austin, TX 78701", phone="512-555-0000",
                       is_active=True, last_verified_date=date(2024, 6, 1)),
        ProviderRecord(provider_id="SHOW-CONFLICT", provider_name="Maria Garcia, MD", npi="3333333333",
                       specialty="Pediatrics", practice_name="Denver Pediatric Group",
                       address="4 Oak Ave, Denver, CO 80202", phone="720-555-0000",
                       is_active=True, last_verified_date=date(2024, 3, 1)),
        # HL_001-shaped movement scenario: same changed fields and new values, but
        # with a demo id/NPI. SHOW-MOVE includes board corroboration for phone too,
        # so it demonstrates the safer three-source auto-update path.
        ProviderRecord(provider_id="SHOW-MOVE", provider_name="John Smith, MD", npi="4444444444",
                       specialty="Cardiology", practice_name="ABC Heart Group",
                       address="100 Main St, Naples, FL 34102", phone="239-555-1234",
                       is_active=True, last_verified_date=date(2023, 9, 1)),
    ]


def generate(*, seed: int = 7, n: int = 50) -> list[ProviderRecord]:
    rng = random.Random(seed)
    recs: list[ProviderRecord] = []
    for i in range(n):
        city, state, zip_ = rng.choice(_CITIES)
        recs.append(ProviderRecord(
            provider_id=f"P{i:04d}", npi=_npi(rng),
            provider_name=f"{rng.choice(_FIRST)} {rng.choice(_LAST)}, MD",
            specialty=rng.choice(_SPECIALTY),
            practice_name=f"{city} Medical Group",
            address=f"{rng.randint(1, 999)} {rng.choice(_STREETS)}, {city}, {state} {zip_}",
            phone=_phone(rng), is_active=True,
            last_verified_date=date(2025, 1, 1) - timedelta(days=rng.randint(0, 400)),
        ))
    return recs + _showcase()
