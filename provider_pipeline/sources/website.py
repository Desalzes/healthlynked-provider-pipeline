from __future__ import annotations
import re
from pathlib import Path
from typing import Optional
from ..llm import extract_contact, CompletionFn
from ..schemas import ContactTuple

_TAG = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_ANGLE = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")

_INSTRUCTION = (
    "You are reading the text of a medical practice's public web page. "
    "Extract the practice's current contact details for the provider."
)


def html_to_text(html: str) -> str:
    no_blocks = _TAG.sub(" ", html)
    text = _ANGLE.sub(" ", no_blocks)
    return _WS.sub(" ", text).strip()


def extract_from_practice_site(html: str, *, model: str, cache_dir: Path,
                               completion_fn: Optional[CompletionFn] = None) -> tuple[ContactTuple, int]:
    return extract_contact(html_to_text(html), instruction=_INSTRUCTION,
                           model=model, cache_dir=cache_dir, completion_fn=completion_fn)


def load_fixture(slug: str, *, fixtures_dir: Path) -> Optional[str]:
    f = Path(fixtures_dir) / f"{slug}.html"
    return f.read_text(encoding="utf-8") if f.exists() else None
