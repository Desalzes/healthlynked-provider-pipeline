# HealthLynked Provider Pipeline (prototype)

Deterministic-first, multi-source pipeline that keeps a healthcare provider
directory current (address + phone) with an explainable confidence score and
per-decision cost telemetry. Kaggle submission — Track C (hybrid). Full design:
`WRITEUP.md`.

## Quickstart

```bash
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
python -m pytest -q                          # 73 tests
```

(The CLI must run before `make_cost_chart.py` / `make_review_queue.py` — those read the audit
DB the CLI populates, and exit with a clear message if it is empty.)

`--fake-contacts` runs fully offline (regex extractor, zero LLM calls). Drop it
and add `--live` to use DeepSeek/Ollama via litellm (set
`PIPELINE_LLM_MODEL=ollama/<model>` for the no-cost local path). The audit log is
`out/audit.db`; the cost chart is `out/cost_telemetry.png`.

## How it works

Four sources, deterministic-first. Two are free, authoritative public lookups (CMS **NPI
Registry** and **State Medical Board**); two are gated LLM extractors (practice website, then a
web-search snippet fallback). Most records resolve with zero LLM spend (~82% of field-decisions
in the offline demo); the LLM runs only on candidate changes; an auto-update always needs a
third corroborating source (so two sources alone are held for review); conflicts escalate to
human review. Every decision writes a fully-traceable audit row, including the number of paid
LLM stages it invoked. See `WRITEUP.md`.

## Design ↔ code map

| Design element (WRITEUP) | Code |
|---|---|
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
