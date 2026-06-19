from __future__ import annotations
import json
from pathlib import Path
from typing import Optional
from ..llm import extract_contact, CompletionFn
from ..schemas import ContactTuple

_INSTRUCTION = (
    "Below are search-result snippets about a medical provider. "
    "Extract the most likely CURRENT contact details."
)


def extract_from_snippets(snippets: list[str], *, model: str, cache_dir: Path,
                          completion_fn: Optional[CompletionFn] = None) -> tuple[ContactTuple, int]:
    joined = "\n- ".join(snippets)
    return extract_contact(joined, instruction=_INSTRUCTION,
                           model=model, cache_dir=cache_dir, completion_fn=completion_fn)


def load_fixture(slug: str, *, fixtures_dir: Path) -> Optional[list[str]]:
    f = Path(fixtures_dir) / f"{slug}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
