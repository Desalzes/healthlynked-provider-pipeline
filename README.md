# HealthLynked Provider Pipeline (prototype)

Deterministic-first, multi-source pipeline that keeps a healthcare provider
directory current (address + phone) with an explainable confidence score and
per-decision cost telemetry. Kaggle submission — Track C (hybrid).

- **`SUBMISSION.md`** — the condensed **Kaggle Writeup body** (a tight ~1,160-word version).
- **`WRITEUP.md`** — the full design (~5k words), the deep dive linked from the Writeup.

## Quickstart

```bash
git clone https://github.com/Desalzes/healthlynked-provider-pipeline
cd healthlynked-provider-pipeline
python -m venv .venv
# activate the venv:
#   POSIX (macOS/Linux):  source .venv/bin/activate
#   Windows (PowerShell): .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"

python scripts/make_synthetic_data.py        # writes data/synthetic_providers.json (54 records)
python scripts/make_bulk_fixtures.py         # writes the per-record source fixtures
python -m provider_pipeline.cli --fake-contacts --show-examples
python scripts/sponsor_example_demo.py       # literal HL_001 at both thresholds (0.85 / 0.80)
python scripts/live_npi_demo.py              # live CMS NPI lookup + $0 check-digit pre-filter
python scripts/duplicate_report.py           # $0 batch duplicate-detection pre-pass
python scripts/make_cost_chart.py            # -> out/cost_telemetry.png, out/sensitivity.csv
python scripts/make_review_queue.py          # -> out/review_queue.html (human-review dashboard)
python -m pytest -q                          # 98 tests
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
| Duplicate detection (§6) | `provider_pipeline/dedupe.py`, `scripts/duplicate_report.py` |
| NPI validation (§2) | `provider_pipeline/validate.py` (CMS check digit), wired in `sources/npi.py::validated_fetch` |
| Sponsor HL_001 / live NPI demos | `scripts/sponsor_example_demo.py`, `scripts/live_npi_demo.py` |

MIT licensed.
