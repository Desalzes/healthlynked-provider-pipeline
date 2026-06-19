from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from typing import Callable, Optional
from .schemas import ContactTuple

CompletionFn = Callable[..., dict]
_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _default_completion_fn(*, model, messages):  # pragma: no cover - needs litellm + network
    import litellm
    resp = litellm.completion(model=model, messages=messages)
    return resp.model_dump() if hasattr(resp, "model_dump") else resp


def complete(prompt: str, *, model: str, cache_dir: Path,
             completion_fn: Optional[CompletionFn] = None) -> tuple[str, int]:
    completion_fn = completion_fn or _default_completion_fn
    cache_dir = Path(cache_dir)
    key = hashlib.sha256(f"{model}\x00{prompt}".encode("utf-8")).hexdigest()
    cache_file = cache_dir / f"{key}.json"
    if cache_file.exists():
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        return cached["text"], 0
    resp = completion_fn(model=model, messages=[{"role": "user", "content": prompt}])
    text = resp["choices"][0]["message"]["content"]
    tokens = int(resp.get("usage", {}).get("total_tokens", 0))
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps({"text": text, "tokens": tokens}), encoding="utf-8")
    return text, tokens


def _parse_contact(text: str) -> ContactTuple:
    m = _FENCE.search(text)
    raw = m.group(1) if m else text
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        data = json.loads(raw[start:end + 1]) if start >= 0 and end > start else {}
    allowed = {"address_line", "city", "state", "zip", "phone"}
    return ContactTuple(**{k: v for k, v in data.items() if k in allowed})


def extract_contact(text: str, *, instruction: str, model: str, cache_dir: Path,
                    completion_fn: Optional[CompletionFn] = None) -> tuple[ContactTuple, int]:
    prompt = (
        f"{instruction}\n\n"
        "Return ONLY a JSON object with keys address_line, city, state, zip, phone. "
        "Use null for any field not clearly present. Do not invent values.\n\n"
        f"---\n{text}\n---"
    )
    raw, tokens = complete(prompt, model=model, cache_dir=cache_dir, completion_fn=completion_fn)
    return _parse_contact(raw), tokens
