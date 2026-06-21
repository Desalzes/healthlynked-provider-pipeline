from __future__ import annotations
import re
from typing import Optional
from rapidfuzz import fuzz
from .schemas import AddressTuple

try:
    import usaddress  # type: ignore
    _HAVE_USADDRESS = True
except Exception:  # pragma: no cover - environment dependent
    _HAVE_USADDRESS = False

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[.,]")


def _clean(s: str) -> str:
    s = _PUNCT.sub("", s.lower())
    return _WS.sub(" ", s).strip()


def normalize_phone(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s = re.sub(r"(?:ext\.?|x)\s*\d+\s*$", "", s, flags=re.IGNORECASE)
    digits = re.sub(r"\D", "", s)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    # Digit-less junk ("N/A", "see website") must not normalize to "" — otherwise
    # two unparseable phones would compare EQUAL and a missing number would read as
    # "verified, no change". Return None so _eq / agreement treat it as not-a-match.
    if len(digits) != 10:
        return None
    return digits


def normalize_address(line: str, city: str, state: str, zip_: str) -> AddressTuple:
    street = _clean(line)
    if _HAVE_USADDRESS:
        try:
            tagged, _ = usaddress.tag(f"{line}, {city}, {state} {zip_}")
            parts = [
                v for k, v in tagged.items()
                if k.startswith("Address") or k.startswith("Street")
                or k == "OccupancyIdentifier" or k == "OccupancyType"
            ]
            if parts:
                street = _clean(" ".join(parts))
        except Exception:
            pass
    return AddressTuple(
        street=street,
        city=_clean(city),
        state=_clean(state),
        zip=re.sub(r"\D", "", zip_)[:5],
    )


def normalize_address_str(s: Optional[str]) -> Optional[AddressTuple]:
    """Parse a single-line 'street, city, ST zip' address (the sponsor input
    format) into an AddressTuple by splitting on commas, then delegating to
    normalize_address for cleaning/zip-truncation."""
    if not s:
        return None
    parts = [p.strip() for p in s.split(",")]
    street = parts[0] if parts else s
    city = parts[1] if len(parts) > 1 else ""
    state, zip_ = "", ""
    if len(parts) > 2:
        m = re.search(r"([A-Za-z]{2})\s*(\d{5})", parts[-1])
        if m:
            state, zip_ = m.group(1), m.group(2)
        else:
            tail = parts[-1].split()
            if tail:
                state = tail[0]
                if len(tail) > 1:
                    zip_ = tail[1]
    return normalize_address(street, city, state, zip_)


def agreement(observed: Optional[str], *, new: str, old: str, field: str) -> float:
    if observed is None:
        return 0.0
    if field == "phone":
        o = normalize_phone(observed)
        # An unparseable phone (o is None) never "agrees" — guard the None==None trap.
        return 1.0 if (o is not None and o == normalize_phone(new)) else 0.0
    o, n, ol = _clean(observed), _clean(new), _clean(old)
    if o == n:
        return 1.0
    if o == ol:
        return 0.0
    return fuzz.token_set_ratio(o, n) / 100.0
