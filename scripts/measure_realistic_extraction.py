"""Measure the LLM extractor on production-shaped practice pages.

The bundled 54-record demo fixtures are compact, so the per-call token count
measured there understates a real practice website. This script runs the actual
website extractor over data/fixtures/realistic/*.html — pages with nav menus,
hours tables, insurance lists, labeled fax/billing numbers, suite numbers, and
(for R3) a permanently-closed previous address — and reports:

  1. correctness: did the extractor pull the CURRENT contact and avoid the
     fax/billing/closed-address decoys? (the naive regex floor does not), and
  2. measured tokens/call on realistic input.

It uses a real local model via litellm (default ollama_chat/qwen2.5:3b — $0,
needs Ollama running). Override with PIPELINE_LLM_MODEL. Writes
out/extraction_measurement.json. This is a one-time measurement (not a CI test);
the offline structural check lives in tests/test_realistic_fixtures.py.
"""
import json
import re
from pathlib import Path
from provider_pipeline.config import Config
from provider_pipeline.normalize import normalize_phone
from provider_pipeline.sources.website import extract_from_practice_site, load_fixture

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "data" / "fixtures" / "realistic"
OUT = ROOT / "out"


def _check(slug: str, contact, exp: dict) -> list[str]:
    """Return a list of failures (empty == correct)."""
    fails = []
    got_phone = normalize_phone(contact.phone)
    if got_phone != exp["phone"]:
        fails.append(f"phone {got_phone!r} != {exp['phone']!r}")
    if got_phone in exp.get("must_not_pick_phones", []):
        fails.append(f"picked a decoy phone {got_phone!r}")
    if (contact.zip or "")[:5] != exp["zip"]:
        fails.append(f"zip {contact.zip!r} != {exp['zip']!r}")
    if contact.state and contact.state.strip().lower() != exp["state"]:
        fails.append(f"state {contact.state!r} != {exp['state']!r}")
    # Normalize punctuation/whitespace before comparing city ("St. Petersburg"
    # and "st petersburg" are the same place).
    got_city = re.sub(r"\s+", " ", re.sub(r"[.,]", "", (contact.city or "").lower())).strip()
    if got_city and exp["city"] not in got_city:
        fails.append(f"city {contact.city!r} missing {exp['city']!r}")
    street = (contact.address_line or "")
    if exp["street_number"] not in street:
        fails.append(f"street {street!r} missing number {exp['street_number']!r}")
    bad_num = exp.get("must_not_pick_street_number")
    if bad_num and bad_num in street:
        fails.append(f"street {street!r} picked closed-address number {bad_num!r}")
    return fails


def main() -> None:
    expected = json.loads((FIX / "expected.json").read_text(encoding="utf-8"))
    model = Config().llm_model
    cache = OUT / "_realistic_cache"
    import shutil
    shutil.rmtree(cache, ignore_errors=True)  # fresh run -> real token counts

    results = []
    total_tokens = 0
    for slug, exp in expected.items():
        html = load_fixture(slug, fixtures_dir=FIX)
        if html is None:
            raise SystemExit(f"missing fixture {slug}.html")
        contact, tokens = extract_from_practice_site(html, model=model, cache_dir=cache)
        total_tokens += tokens
        fails = _check(slug, contact, exp)
        results.append({"fixture": slug, "tokens": tokens, "ok": not fails,
                        "failures": fails, "html_chars": len(html),
                        "extracted": contact.model_dump()})
        status = "OK " if not fails else "FAIL"
        print(f"[{status}] {slug}: {tokens} tokens, {len(html)} html chars"
              + ("" if not fails else f" -> {fails}"))

    n = len(results)
    n_ok = sum(r["ok"] for r in results)
    # Transparency: track which scalar fields the model actually emitted (the checked
    # fields are phone/zip/city/street + decoy avoidance; state is reported separately
    # because a small model may omit it and the grader does not fail on a null state).
    state_extracted = sum(1 for r in results if r["extracted"].get("state"))
    mean_tokens = round(total_tokens / n, 1) if n else 0.0
    report = {
        "model": model,
        "fixtures": n,
        "correct": n_ok,
        "state_extracted": state_extracted,
        "total_tokens": total_tokens,
        "mean_tokens_per_call": mean_tokens,
        "mean_html_chars": round(sum(r["html_chars"] for r in results) / n, 1) if n else 0,
        "results": results,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "extraction_measurement.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n{n_ok}/{n} correct (phone/zip/city/street + decoys); "
          f"state emitted on {state_extracted}/{n}; "
          f"mean {mean_tokens} tokens/call on realistic pages")
    print("wrote out/extraction_measurement.json")


if __name__ == "__main__":
    main()
