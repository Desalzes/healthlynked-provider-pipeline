<!--
Condensed Kaggle Writeup body (Track C, hybrid). Target: <= 1,500 words so it is
safe under either a 1,500- or 3,000-word cap (confirm the exact limit on the comp
page). The full 5k-word design lives in WRITEUP.md, linked from the notebook/repo.
Paste the content below (from the H1 down) into the Kaggle Writeup body.
-->

# Keeping a Provider Directory Current — a Deterministic-First, Cost-Aware Pipeline

**HealthLynked Track C (hybrid): a runnable prototype + the production design behind it.**
Python, **98 passing tests**; every number below reproduces from one command. Full design and
design↔code map: `WRITEUP.md` / `README.md` in the attached notebook/repo.

**The one idea.** Keeping a directory current is a **routing problem, not a token problem.** On
this prototype's data, human review costs **~$250 per 1,000 records** while LLM inference costs
**~$0.036** — labor is **~7,000×** the inference bill. So the design resolves the *maximum share
of records with zero human and zero LLM cost*, spends an LLM only where cheaper signals are
exhausted, and routes a human only to genuinely ambiguous cases — every decision auditable. A
field of "LLM-everywhere" pipelines optimizes the rounding error; this one optimizes the bill.

## Problem
A provider directory is a depreciating asset: providers move, practices merge or rebrand,
numbers change, and reputable sources disagree. CMS Medicare Advantage reviews have found
location-level inaccuracy clustering near ~45%. Each stale entry has a real cost — a patient sent
to a dead phone line, a bounced referral, a compliance exposure. Manual upkeep is the slowest and
**most expensive** part of the system, so the engineering goal is to **resolve most records
deterministically, gate the LLM, and escalate only the genuinely ambiguous.**

## Architecture — a deterministic-first gate cascade
Cost rises at each stage, so every stage is a **gate** that resolves what it can before the next:

```
record → stale-select → NPI Registry (free) → field compare
   NPI agrees ───────────────► no_change   (most records, $0)
   candidate change → State Medical Board (free) + Practice Website (gated LLM)
      → cross-source: agree / conflict → [web-snippet LLM fallback if needed]
      → confidence + route → audit row   (auto_update / human_review / no_change)
```

The pipeline is a **pure function over injected dependencies**, so fixtures (offline, $0), an
offline regex extractor, or live CMS NPI + a real LLM are a dependency swap, not a rewrite.

## Tiered routing & cost — the centerpiece
`python -m provider_pipeline.cli --fake-contacts` over 54 records (108 field-decisions):

| Decision | Share |
|---|---|
| `no_change` (deterministic) | **81.5%** |
| `auto_update` | 10.2% |
| `human_review` | 8.3% |

**Cost per 1,000 records.** Gated inference **~$0.036** — modeled from **24 *measured* gated
calls** (recorded in the audit DB), not a hand-picked fraction — vs **$0.16** for an
LLM-everywhere baseline (**~4.5× cheaper**). But both are a rounding error next to **~$250** of
human review (≈99.98% of the bill). The highest-leverage cost control is therefore the **~82%
no-review path**, then the auto-approve gate that keeps confirmed changes out of the queue.

*Honesty note:* the synthetic set injects drift into ~⅓ of records so all four routing paths are
exercised; treat the split as a reproducible **stress scenario**, not a guarantee — production
reports the same metrics from its own audit table.

## Confidence & safe auto-update
Each proposed change scores as a clamped weighted sum over the sources that observed it — weights
**NPI 0.45 / Website 0.35 / Board 0.20 / Snippet 0.10**, each multiplied by a source freshness
decay; thresholds **auto ≥ 0.85, review ≥ 0.55**. The weights are **deliberately not normalized**:
NPI + Website cap at **0.80 < 0.85**, so **an auto-update always requires an authoritative third
source** — never the weak snippet alone. Conflicts bypass scoring and are forced to review.

**On the sponsor's HL_001 example.** We run the **literal** record at both thresholds
(`scripts/sponsor_example_demo.py`): at the **0.85 default** the 2-source phone (Website + NPI) is
held for review → record `human_review` at overall **0.90**; at **`auto_threshold=0.80`** the same
record matches the brief's expected **`auto_update`**, also at **0.90**. Holding a 2-source change
by default is deliberate — a wrong auto-update (a patient sent to a dead number) costs more than an
extra review — and matching the sponsor's risk appetite is a single config knob.

## Sources & reliability
Four weighted sources. The CMS **NPI Registry** is free, live/cacheable, and **proven against the
real API** (`scripts/live_npi_demo.py`), behind a **$0 NPI check-digit pre-filter** (`validate_npi`,
the CMS Luhn algorithm) that rejects malformed NPIs before any call. The **State Medical Board** is
authoritative for **license status** and a best-effort corroborator for contact fields, so the
"authoritative third source" slot is whichever free authoritative source actually carries the
field. Two gated LLM extractors (practice website, then a web-snippet fallback) run only on
candidate changes, each at most once per record.

## Duplicates, movement, inactive
- **Duplicate detection** (`scripts/duplicate_report.py`, $0 batch pre-pass): an identical **NPI**
  across records is the same provider → `auto_merge`; records that merely share **name + ZIP +
  practice but have distinct NPIs** are different clinicians → **held for review, never
  auto-merged**. On the 54-record set this surfaces 6 same-name clusters with **0 false
  auto-merges** — the safety property that matters most for a directory.
- **Movement:** `SHOW-MOVE` demonstrates an address + phone change confirmed by three sources.
- **Inactive/retired:** a deterministic `is_active` flip read straight from the NPI Registry ($0).

## Explainability, audit & data quality
Every decision — including `no_change` — writes one **SQLite audit row** (per-source values,
weights, freshness, final score, decision, and gated-call cost), so any entry traces back to its
evidence and confidence logic. The per-decision `reason` distinguishes *under-corroborated* from
*source conflict*. Phone and address **normalize to comparable keys**; junk values normalize to
"no match," not false agreement. A static **human-review dashboard**
(`scripts/make_review_queue.py`) renders the held queue with the per-source evidence behind each
score.

## Scaling to 1k / 100k / 1M
NPI/board **snapshots** turn lookups into local joins ($0, rate-limit-free); extraction is
**prompt-hash cached**; records are **embarrassingly parallel**; and inference scales with the
**drift rate**, not directory size — a stable directory is cheap to keep stable. The **review
queue** is the only term that scales with the directory, so it is the thing to engineer down
(batching by change type, pre-filled review views, learned per-source weights).

## Roadmap & the first 90 days
The award is a 3-month engagement, so the roadmap maps to a schedule ordered by cost leverage:
**wks 1–2** productionize the deterministic core on real data and measure the *real* no-review and
drift rates; **wks 3–6** live sources (robots-aware site fetch, per-state boards) behind the
existing seam + `libpostal` normalization; **wks 7–10** learn source weights from resolved
reviews, add survivorship + practice-level dedup, roll out specialty/affiliation fields; **wks
11–12** SLA + cost dashboards and handoff. Success metric = **dollars per 1,000 records** from the
live audit table, not a leaderboard number. Survivorship rules and practice-level dedup are
near-term roadmap, not claimed as built.

## Reproduce everything
```
pip install -e ".[dev]"
python -m provider_pipeline.cli --fake-contacts --show-examples   # the routing split + examples
python scripts/sponsor_example_demo.py    # literal HL_001 at 0.85 and 0.80
python scripts/live_npi_demo.py           # live CMS NPI lookup + $0 check-digit pre-filter
python scripts/duplicate_report.py        # $0 duplicate-detection pre-pass
python scripts/make_cost_chart.py         # cost telemetry + threshold sensitivity
python scripts/make_review_queue.py       # human-review dashboard
python -m pytest -q                       # 98 tests
```
