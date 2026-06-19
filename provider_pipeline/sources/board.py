from __future__ import annotations
import json
from pathlib import Path
from ..schemas import ContactTuple

# State Medical Board — a free, authoritative, deterministic public source
# (license registries). Unlike the practice website and search snippets, it costs
# no LLM tokens: the lookup returns structured fields directly. In the prototype it
# is fixture-backed (data/fixtures/board/<provider_id>.json); production swaps this
# one function for per-state board lookups (roadmap §8). Returns a "silent"
# ContactTuple when the board has no record for the provider.

_ALLOWED = {"address_line", "city", "state", "zip", "phone"}


def load_board(provider_id: str, *, fixtures_dir: Path) -> ContactTuple:
    f = Path(fixtures_dir) / f"{provider_id}.json"
    if not f.exists():
        return ContactTuple()
    data = json.loads(f.read_text(encoding="utf-8"))
    return ContactTuple(**{k: v for k, v in data.items() if k in _ALLOWED})
