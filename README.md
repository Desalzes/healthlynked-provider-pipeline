# HealthLynked Provider Pipeline (prototype)

Deterministic-first, multi-source pipeline that keeps a healthcare provider
directory current (address + phone) with an explainable confidence score and
per-decision cost telemetry. Kaggle submission — Track C (hybrid). Full design:
`WRITEUP.md`.

## Quickstart

```bash
cd comps/provider-pipeline
python -m venv .venv
# activate the venv:
#   POSIX (macOS/Linux):  source .venv/bin/activate
#   Windows (PowerShell): .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"

python scripts/make_synthetic_data.py        # writes data/synthetic_providers.json (54 records)
python scripts/make_bulk_fixtures.py         # writes the per-record source fixtures
python -m provider_pipeline.cli --fake-contacts --show-examples
python scripts/make_cost_chart.py            # -> out/cost_telemetry.png, out/sensitivity.csv
python scripts/make_review_queue.py          # -> out/review_queue.html (human-review dashboard)
# $0 data-quality screen (NPI check-digit validation + duplicate detection) on the planted set:
python -m provider_pipeline.cli --data data/dataquality_demo.json --data-quality
# (scripts/make_data_quality_report.py writes the same out/data_quality.json with cluster members)
python -m pytest -q                          # full test suite

# optional: measure the LLM extractor on realistic practice pages (needs Ollama)
PIPELINE_LLM_MODEL=ollama_chat/qwen2.5:3b python scripts/measure_realistic_extraction.py
```

(The CLI must run before `make_cost_chart.py` / `make_review_queue.py` — those read the audit
DB the CLI populates, and exit with a clear message if it is empty.)

`--fake-contacts` runs fully offline (regex extractor, zero LLM calls). Drop it
and add `--live` to use the live CMS NPI API plus DeepSeek/Ollama extraction via
litellm (set `PIPELINE_LLM_MODEL=ollama/<model>` for the no-cost local path).
Practice website/snippet text and State Medical Board observations are fixture-backed
in this prototype; the injected source seams are where production fetchers plug in.
The audit log is `out/audit.db`; the cost chart is `out/cost_telemetry.png`.

## How it works

Four sources, deterministic-first. CMS **NPI Registry** is implemented as a free live/cacheable
lookup; the **State Medical Board** source is a fixture-backed prototype for a free authoritative
lookup; two sources are gated LLM extractors (practice website, then a web-search snippet
fallback). Most records resolve with zero LLM spend (~82% of field-decisions in the offline
demo); the LLM runs only on candidate changes; an auto-update always needs a third corroborating
source (so two sources alone are held for review); conflicts escalate to human review. Every
decision writes a fully-traceable audit row, including the number of paid LLM stages it invoked.
See `WRITEUP.md`.

## Design ↔ code map

| Design element (WRITEUP) | Code |
|---|---|
| Data-quality pre-pass: NPI validation + dedup (§2) | `provider_pipeline/dataquality.py`, `scripts/make_data_quality_report.py` |
| Realistic-page extraction measurement (§3) | `data/fixtures/realistic/`, `scripts/measure_realistic_extraction.py` |
| Stale selection (§2.1) | `provider_pipeline/pipeline.py::select_stale` |
| NPI Registry lookup (§2.2) | `provider_pipeline/sources/npi.py` |
| State Medical Board (§2.4) | `provider_pipeline/sources/board.py` |
| Website / snippet extraction (§2.4/2.6) | `provider_pipeline/sources/{website,snippet}.py`, `llm.py` |
| Normalization (§4) | `provider_pipeline/normalize.py` |
| Cross-source routing (§2.5) | `provider_pipeline/compare.py::cross_source` |
| Confidence + safe-auto rule (§4) | `provider_pipeline/confidence.py`, `config.py` |
| Audit log (§5) | `provider_pipeline/audit.py` |
| Cost model (§3) | `provider_pipeline/cost.py`, `scripts/make_cost_chart.py` |
| Review dashboard (§6) | `provider_pipeline/review_queue.py`, `scripts/make_review_queue.py` |

MIT licensed.
