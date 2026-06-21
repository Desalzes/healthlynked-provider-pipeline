"""NPI structural validation — the CMS check-digit algorithm.

A National Provider Identifier is 10 digits; the 10th is a Luhn check digit
computed over the constant prefix ``80840`` followed by the first 9 digits
(CMS NPI Check Digit specification). Validating it is a free, deterministic
pre-filter: a structurally-impossible NPI can be rejected before any NPI
Registry call, LLM extraction, or human review is spent on the record.
"""
from __future__ import annotations
from typing import Optional

_NPI_PREFIX = "80840"


def validate_npi(npi: Optional[str]) -> bool:
    """Return True iff ``npi`` is 10 digits with a valid CMS Luhn check digit."""
    if not npi or not npi.isdigit() or len(npi) != 10:
        return False
    base = _NPI_PREFIX + npi[:9]
    check = int(npi[9])
    total = 0
    # The check digit sits to the right of ``base``; doubling every second digit
    # from the right of ``base`` therefore starts with ``base``'s last digit.
    for i, ch in enumerate(reversed(base)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (total + check) % 10 == 0
