# Keeping a Provider Directory Current — a Deterministic-First, Cost-Aware Pipeline

**HealthLynked Provider & Practice Directory Update Pipeline — Track C (working prototype + production design)**

> **The one idea, up front.** Keeping a provider directory current is a **routing**
> problem, not a token problem. On this prototype's data, human review costs **~$250
> per 1,000 records** while LLM inference costs **~$0.036** — labor is ~7,000× the
> inference bill. So the design spends its effort resolving the **maximum share of
> records with zero human and zero LLM cost**, calls an LLM only where cheaper
> signals are exhausted, and routes a human only to genuinely ambiguous cases — every
> decision traceable. A field of "LLM-everywhere" pipelines optimizes the rounding
> error; this one optimizes the bill.

This submission is a runnable prototype (Python, **73 passing tests**) plus the production
design behind it. Everything below is reproducible from the repository: `pip install -e ".[dev]"`,
then `python -m provider_pipeline.cli --fake-contacts --show-examples`. Numbers reported as
**observed/measured** come from that command (and `scripts/make_cost_chart.py`) on 54
synthetic records; numbers reported as **modeled** are labeled as such and state their
assumptions.

---

## 1. Problem framing

A provider directory is a depreciating asset. The moment a record is verified it begins to
drift: providers move practices, practices merge or rebrand, phone numbers and suite numbers
change, providers join or leave groups, specialties and credentials are reported differently
across sources, and — most dangerously — **two reputable sources disagree**. Industry studies
of physician directories routinely find 30–50% of entries contain at least one inaccuracy
within a year. Each stale entry has a real downstream cost: a patient routed to a closed
office or a dead phone line, a referral that bounces, a compliance exposure.

Manual upkeep does not scale: a human verifying every field of every record is both the
slowest and the **most expensive** part of the system (Section 3 shows it dominates cost by
more than three orders of magnitude over inference). The goal, restated as an engineering
problem, is therefore not "use AI to check records" but: **resolve the maximum share of
records with zero human and zero LLM cost, spend LLM tokens only where cheaper signals are
exhausted, and route a human only to the cases that are genuinely ambiguous — while keeping
every decision traceable.**

The MVP tracks the fields HealthLynked's brief names: provider name, NPI, specialty, practice
name, **address**, **phone**, website, and active/inactive status. The prototype implements
the two highest-churn free-text fields end-to-end (**address** and **phone**) plus a
deterministic **active-status** flip, and the design generalizes the same machinery to the
remaining fields (Section 8).

---

## 2. Architecture — deterministic-first, with two free authoritative sources

The pipeline mirrors HealthLynked's desired architecture and makes the "Decision" node
concrete. Cost rises at each stage, so every stage is a **gate** that resolves as many records
as possible before the next, more expensive stage runs. Two of the four sources — the **CMS
NPI Registry** and the **State Medical Board** — are free, deterministic public lookups; the
two paid LLM stages (practice-website and web-search extraction) run only when the free
signals are exhausted.

```
  HealthLynked directory record
            │
  ┌─────────▼──────────┐
  │ 1. Stale selection │  pick records past the re-verification horizon         $0
  └─────────┬──────────┘
  ┌─────────▼──────────┐
  │ 2. NPI Registry    │  CMS NPI lookup — free, authoritative                  $0
  │    lookup (CMS)    │  also a deterministic is_active flip
  └─────────┬──────────┘
  ┌─────────▼──────────┐
  │ 3. Field compare   │  normalize + compare record vs NPI                     $0
  └─────────┬──────────┘
            │  NPI agrees with record ──────────────► no_change  (most records)
            │  candidate change OR NPI silent
  ┌─────────▼──────────┐
  │ 2b/4. State Board  │  State Medical Board lookup — free, authoritative       $0
  │   + Website (LLM)  │  Website extractor (gated LLM) on candidate changes     $  (gated)
  └─────────┬──────────┘
  ┌─────────▼──────────┐
  │ 5. Cross-source    │  NPI vs website vs existing → agree / conflict         $0
  └─────────┬──────────┘
            │  below auto threshold and not a conflict
  ┌─────────▼──────────┐
  │ 6. Snippet extract │  LLM reads search snippets — FALLBACK third source     $  (gated)
  │    (gated LLM)     │  only when the board was silent and a 3rd is needed
  └─────────┬──────────┘
  ┌─────────▼──────────┐
  │ 7. Confidence +    │  weighted score → auto_update / human_review / no_change
  │    routing         │  conflicts are forced to human_review
  └─────────┬──────────┘
  ┌─────────▼──────────┐
  │ 8. Audit emit      │  one SQLite row per decision: sources, weights,        $0
  │                    │  freshness, score, decision, gated calls, wall-time
  └────────────────────┘
```

Rationale, stage by stage:

1. **Stale selection** — `select_stale()` admits only records whose `last_verified_date` is
   past the re-verification horizon (180 days by default); fresh records cost nothing. A
   periodic run touches the stale tail, not the whole directory.
2. **NPI Registry lookup** — the CMS NPI Registry is free, authoritative for licensed
   providers, and rate-limit friendly, so it runs first. The active/inactive flip is read
   directly from it — a deterministic, $0 update with no LLM.
3. **Field compare** — record and NPI values are normalized (phone → digits, address →
   `street|city|state|zip` key) and compared. **If NPI agrees with the record, the decision is
   `no_change` and the pipeline stops — no board, no LLM, no human.** This is where most
   records exit.
4. **State Medical Board + Website extraction** — for a candidate change, the pipeline adds the
   **State Medical Board** (a free, authoritative licensing source) and runs the
   **practice-website extractor** (the first paid LLM stage). The board makes auto-update reachable
   through *authoritative* corroboration rather than a weak web snippet (Section 4).
5. **Cross-source agreement** — NPI, website, and the existing value are compared: all-agree
   (`no_change`), NPI+website agree and differ from existing (`strong_update`), website merely
   confirms the old value (`false_alarm`, no change), or mutual disagreement (`conflict`).
6. **Snippet extraction (gated LLM, fallback)** — runs **only** when the score is still below
   the auto bar and the case is not a conflict — i.e. the authoritative board was silent and a
   third confirmation is needed. Most auto-updates never reach this stage.
7. **Confidence + routing** — the weighted score (Section 4) routes to `auto_update`,
   `human_review`, or `no_change`. Conflicts are forced to `human_review` regardless of score.
8. **Audit emit** — every decision writes a fully-traceable row (Section 5), including the
   number of paid LLM stages it invoked (`gated_calls`) so the cost model is *measured*.

The pipeline is a pure function over injected dependencies (`Deps`: NPI fetch, board lookup,
website extract, snippet extract). The same code runs against fixtures (offline, deterministic),
a regex extractor (`--fake-contacts`, offline, $0), or live DeepSeek/Ollama via litellm — only
the injected functions change.

---

## 3. Tiered routing and per-record cost (the centerpiece)

### 3.1 The tier model

| Tier | What resolves it | Cost driver | Design target |
|---|---|---|---|
| **Deterministic** | NPI agrees, or a clean NPI/board-confirmed change, or an is_active flip | $0 (no LLM, no human) | majority of a real directory |
| **LLM-assisted** | candidate changes needing website/snippet extraction | gated tokens | the minority that actually drifted |
| **Human review** | conflicts and under-corroborated changes | analyst minutes | only the genuinely ambiguous |

### 3.2 Observed split (reproducible, offline)

`python -m provider_pipeline.cli --fake-contacts` over the 54-record synthetic set
(108 field-decisions, 2 tracked fields/record):

```
loaded=54 stale_selected=54 decisions=108 auto=11 review=9 no_change=88
llm_calls=0 total_tokens=0 mean_wall_ms=...
```

| Decision | Count | Share |
|---|---|---|
| `no_change` | 88 | 81.5% |
| `auto_update` | 11 | 10.2% |
| `human_review` | 9 | 8.3% |

`llm_calls=0` because the offline demo uses a regex extractor for reproducibility (no network,
no spend). The **structural** split — ~82% resolved with no review, ~18% changed — is the
number that drives cost, and it is real.

**Honest note on the synthetic set.** This set was generated with deliberate drift injected
into roughly a third of records so that all four routing paths are exercised; a production
directory has *more* unchanged records, not fewer, so the deterministic share would be
**higher**, not lower. We report the measured ~82% and explicitly flag it as a floor.

### 3.3 Cost per 1,000 records

Two cost components. Inference is **measured from the actual count of gated LLM-stage calls**
the pipeline makes (`gated_calls`, recorded on every decision), not a hand-picked fraction —
so the offline demo, which spends $0, still yields a defensible inference estimate at a stated
price.

**Inference (LLM).** Over the 54-record demo the pipeline invoked **24 gated extraction
calls** (website + snippet; each paid source is extracted at most once per record) — measured,
in `out/audit.db`. Assumptions: DeepSeek-class inference at $0.0002/1k tokens, ~400 tokens/call.
- *This pipeline (gated, measured)* — `24 calls / 54 records = 0.44 calls/record → ~444
  calls per 1k records × 400 tokens ≈ 178k tokens → ≈ $0.036 per 1k records`.
- *LLM-everywhere baseline* — one extraction call per field for every record:
  `1000 × 2 × 400 = 800k tokens → $0.16 per 1k records`.
- **≈ 4.5× cheaper** (`0.16 / 0.036 ≈ 4.5×`), and the gap widens on a real directory where the
  drift rate (hence gated calls) is lower. A live `--live` run records real token counts and
  replaces the per-call estimate with measured tokens (see README); the prompt-hash cache makes
  re-runs free.

**Human review (labor).** This is the dominant term. At the observed 8.3% review rate, 1,000
records (2,000 field-decisions) yield ~167 reviews → `167 × 3 min = 8.3 h × $30 = ~$250 per
1k records`. `scripts/make_cost_chart.py` prints this on a **per-1,000-decisions** basis —
`review_usd = $125.00` at 83.3 reviews/1k decisions — which is the *same* figure: each record
carries two tracked field-decisions, so `$125.00 × 2 = $250 per 1k records`. The table below
states both bases so the printed number and the headline reconcile exactly.

| Cost line | Per 1,000 records | Note |
|---|---|---|
| Gated inference | ~$0.036 | measured from 24 gated calls; $0 spent in the offline demo |
| LLM-everywhere inference (baseline) | $0.16 | what we avoid (~4.5×) |
| Human review | ~$250 | `= $125.00` per 1k **decisions** (tool output) × 2 decisions/record |
| **Total** | **~$250** | **~99.98% is human labor** |

**The insight that should drive the design — and it is not the obvious one.** Inference is a
rounding error next to human labor. Shaving LLM tokens saves cents; removing a record from the
review queue saves dollars. So the highest-leverage cost control is **the deterministic
no-review path that resolves ~82% of decisions before any human or LLM is involved**, followed
by the **auto-approve gate** that keeps confirmed changes out of the review queue. A naive
"send every detected change to a human" pipeline would review ~18% of decisions (~$540/1k
records); auto-approving high-confidence changes roughly halves that. A "review everything"
baseline would cost ~$3,000/1k records — ~12× more. Cost efficiency here is a **routing**
problem, not a **token** problem, and the pipeline is built around that fact.

### 3.4 Threshold sensitivity

`scripts/make_cost_chart.py` re-runs routing at a sweep of auto-update thresholds
(`out/sensitivity.csv`). Conflict-forced reviews are held constant — a genuine source conflict
is irreducible and cannot be thresholded away:

| auto_threshold | auto_update | human_review | no_change |
|---|---|---|---|
| 0.75 | 16 | 4 | 88 |
| 0.80 | 16 | 4 | 88 |
| **0.85 (default)** | **11** | **9** | **88** |
| 0.90 | 11 | 9 | 88 |

Reading the table: lowering the bar to 0.80 promotes the five under-corroborated
(NPI+website-only, score 0.80) changes from review to auto — trading review labor for the risk
of auto-applying a two-source change. The **four conflict-driven reviews persist at every
threshold**, as they should. The default 0.85 reproduces the live demo split exactly
(11 / 9 / 88), the consistency check that the cost model and the running pipeline agree.

### 3.5 Throughput

The deterministic path is cheap in compute as well as money: the offline run processes the
54-record set in ~27 ms — **~0.5 ms/record, ~2,000 records/core-second** — so the $0 stages
(stale-select, NPI/board lookups, normalization, scoring, audit) are not the bottleneck at any
realistic directory size. The gated LLM stages are network-bound and **embarrassingly
parallel** (Section 7); the real scaling constraint is the human review queue, not compute.

---

## 4. Confidence formula and safe auto-update rules

Each proposed change scores as a **raw weighted sum** over the sources that observed it,
clamped to [0, 1]:

```
score = min(1.0,  Σ_source  weight(source) × agreement(source, new_value) × freshness(source))
```

- **weight** — source reliability: NPI Registry **0.45**, Practice Website **0.35**, State
  Medical Board **0.20**, web-search snippet **0.10**. (Deliberately *not* normalized to 1.0 —
  see the safe-auto property below; a four-source agreement clamps to 1.0.)
- **agreement** — for **phone**, binary: 1.0 if the source's digits equal the proposed new
  value, 0 otherwise (an unparseable value never "agrees"). For **address**, a normalized fuzzy
  ratio: 1.0 on an exact normalized-key match, 0 if it matches the *old* value, else a
  `token_set_ratio` in between (so "same street, different suite" contributes partially); a junk
  address scores near zero.
- **freshness** — exponential decay `0.5 ^ (age_days / half_life)`, clamped to [0,1], with
  half-lives NPI 90 d / website 30 d / board 120 d / snippet 14 d. In the prototype every
  source is observed at fetch time, so freshness = 1.0; the decay term governs **re-scoring of
  cached observations** in periodic operation (an NPI value seen 90 days ago contributes half
  as much as one seen today).

Routing thresholds: **auto_update ≥ 0.85**, **human_review ≥ 0.55**, else **no_change**.

**The safe-auto-update property (deliberate).** The score is *not* normalized to 1.0. With
fresh data, NPI + Practice Website agreeing caps at `0.45 + 0.35 = 0.80`, which is **below** the
0.85 auto bar. **An auto-update therefore always requires a third corroborating source** — and
because the State Medical Board (0.20) is authoritative, `NPI + Website + Board = 1.00` clears
the bar through *trustworthy* sources, not through the weak web snippet. The snippet (0.10) is a
**fallback** for when the board has no record: it can tip a two-source agreement over the bar
(`0.45 + 0.35 + 0.10 = 0.90`). That fallback path is exercised by the unit tests
(`test_confidence.py`); in this particular synthetic run the board covers all the auto
candidates, so no auto-update depends on the snippet. Any two-source agreement is held for human
confirmation; conflicts (mutually disagreeing sources) bypass scoring entirely and are forced to
`human_review`.

**On the sponsor's example — a deliberate, calibrated choice.** The competition's `HL_001`
example auto-updates a **two-source** phone change (Practice Website + NPI Registry) at
confidence 0.88. This pipeline scores that exact pair at **0.80 and holds it for review** by
default. That is a deliberate stance, not an oversight: for a directory, **a wrong auto-update
is more costly than an extra review** (a patient sent to a dead number vs. an analyst spending
three minutes), so the default bar prefers a third confirmation. The choice is a **single
configuration knob**: at `auto_threshold = 0.80` the pipeline reproduces the sponsor's
two-source auto-update exactly (see the §3.4 sensitivity table — the five under-corroborated
changes move to auto at 0.80). And for the sponsor's **address** change, which names three
sources including the *State Medical Board*, the pipeline reproduces the expected `auto_update`
end-to-end at the default bar (see `SHOW-MOVE` in Section 6). To be precise about that worked
example: in `SHOW-MOVE` a board observation is available for the *phone* too, so the phone change
clears the default bar as a **three-source** update — it is *not* the held case. The held case
is specifically the **two-source** phone with no third source (the sponsor's literal HL_001
phone sub-change lists only Website + NPI), which `SHOW-REVIEW` demonstrates at 0.80 →
`human_review`. In short: we match the sponsor's example under the sponsor's risk appetite, we
demonstrate the three-source auto-update they expect, and we **recommend** the safer default for
the two-source case — the kind of calibrated judgment a directory operator actually wants.

This is directly visible in the worked examples (Section 6): SHOW-MOVE and SHOW-AUTO score 1.00
(three authoritative sources) → auto; SHOW-REVIEW scores 0.80 (NPI+website agree, no third
source) → review; SHOW-CONFLICT scores 0.45 (sources disagree) → review.

---

## 5. Audit log — schema and a real row

Every decision — including `no_change` — writes one row to a SQLite audit table, so any entry
in the directory can be traced back to the sources and the confidence logic that produced it.

Columns: `id, provider_id, field, old_value, new_value, per_source (JSON), per_source_weights
(JSON), per_source_freshness (JSON), final_score, decision, llm_tokens, gated_calls,
wall_time_ms, timestamp`.

A real emitted row for the SHOW-AUTO phone change, as stored in `out/audit.db` (every field is
reproduced from an actual `SELECT`; the `id` auto-increment PK and the wall-clock `timestamp`
are naturally run-specific — all other fields are deterministic):

```json
{
  "provider_id": "SHOW-AUTO",
  "field": "phone",
  "old_value": "2395550000",
  "new_value": "2395559999",
  "per_source":           {"npi": "2395559999", "website": "2395559999", "board": "2395559999"},
  "per_source_weights":   {"npi": 0.45, "website": 0.35, "board": 0.20},
  "per_source_freshness": {"npi": 1.0,  "website": 1.0,  "board": 1.0},
  "final_score": 1.0,
  "decision": "auto_update",
  "llm_tokens": 0,
  "gated_calls": 1,
  "wall_time_ms": 0,
  "timestamp": "2026-06-19T13:44:33.298621+00:00"
}
```

The row answers *what changed* (old→new), *why* (final_score 1.0 from three corroborating
sources — NPI, website, **State Medical Board** — each weighted and freshness-adjusted),
*which sources supported it* (per_source), and *what it cost* (`llm_tokens` 0 offline;
`gated_calls` 1 = a single paid stage, since the authoritative board made the snippet
unnecessary). `AuditLog.summary()` aggregates these into the routing counts and cost telemetry
used in Section 3; the same table is the backing store for the human-review dashboard
(`scripts/make_review_queue.py`, Section 6).

---

## 6. Prototype demo — four worked examples

The sponsor-facing output matches the brief's example schema exactly
(`data/example_record.json`). Output is human-readable: normalized keys never leak into the
recommendation — phones render `239-555-9999`, addresses `250 Health Park Dr, Fort Myers, FL
33908`. From `--show-examples`:

**SHOW-MOVE — reproduces the sponsor's HL_001 (a provider who moved): address + phone, three
sources incl. State Medical Board → auto_update (1.00)**
```json
{
  "provider_id": "SHOW-MOVE", "npi": "4444444444", "change_detected": true,
  "changes": [
    {"field": "address", "old_value": "100 Main St, Naples, FL 34102",
     "new_value": "250 Health Park Dr, Fort Myers, FL 33908", "confidence_score": 1.0,
     "supporting_sources": ["NPI Registry", "Practice Website", "State Medical Board"]},
    {"field": "phone", "old_value": "239-555-1234", "new_value": "239-555-9000",
     "confidence_score": 1.0,
     "supporting_sources": ["NPI Registry", "Practice Website", "State Medical Board"]}
  ],
  "overall_confidence": 1.0, "recommended_action": "auto_update",
  "reason": "Updated address and phone confirmed by multiple reliable sources."
}
```
This is the competition's own `HL_001` record (same fields, same new values, the State Medical
Board among the sources), and the record-level recommendation matches the sponsor's
(`auto_update`). The **address** change is a faithful three-source → three-source reproduction
of the sponsor's example. For the **phone**, a board observation is also available here, so it
clears the default bar as a three-source change; the sponsor's *two-source* phone case (Website
+ NPI only) is the one we deliberately hold for review at the default bar — see `SHOW-REVIEW`
below and §4. So the demo shows both: the three-source auto the sponsor expects, and the
two-source case our safer default holds.

**SHOW-AUTO — three authoritative sources agree → auto_update (1.00)**
```json
{
  "provider_id": "SHOW-AUTO", "npi": "1111111111", "change_detected": true,
  "changes": [{
    "field": "phone", "old_value": "239-555-0000", "new_value": "239-555-9999",
    "confidence_score": 1.0,
    "supporting_sources": ["NPI Registry", "Practice Website", "State Medical Board"]
  }],
  "overall_confidence": 1.0, "recommended_action": "auto_update",
  "reason": "Updated phone confirmed by multiple reliable sources."
}
```

**SHOW-REVIEW — two sources agree but under-corroborated → human_review (0.80)**
```json
{
  "provider_id": "SHOW-REVIEW", "npi": "2222222222", "change_detected": true,
  "changes": [{
    "field": "phone", "old_value": "512-555-0000", "new_value": "512-555-9999",
    "confidence_score": 0.8,
    "supporting_sources": ["NPI Registry", "Practice Website"]
  }],
  "overall_confidence": 0.8, "recommended_action": "human_review",
  "reason": "Sources agree on phone but corroboration is below the auto-update threshold; manual confirmation recommended."
}
```

**SHOW-CONFLICT — sources disagree → human_review (0.45)**
```json
{
  "provider_id": "SHOW-CONFLICT", "npi": "3333333333", "change_detected": true,
  "changes": [{
    "field": "phone", "old_value": "720-555-0000", "new_value": "720-555-9999",
    "confidence_score": 0.45, "supporting_sources": ["NPI Registry"]
  }],
  "overall_confidence": 0.45, "recommended_action": "human_review",
  "reason": "Sources disagree on phone; manual verification recommended."
}
```

Note the `reason` strings distinguish the two review cases honestly: SHOW-REVIEW's sources
*agree* (both NPI and Website name the same new number) and the recommendation says so — it is
held only for lack of a third confirmation, not because anything conflicts. SHOW-CONFLICT is a
true disagreement. A pipeline that called both "sources disagree" would contradict its own
`supporting_sources` list.

**Human-review dashboard.** `python scripts/make_review_queue.py` renders the held
(`human_review`) decisions from the audit log into a static `out/review_queue.html` — provider,
field, current→proposed value, score, *why held* (under-corroborated vs. source conflict), and
the per-source value/weight/freshness behind the score — the reviewer-facing surface the audit
table backs (Section 8).

---

## 7. Scaling to 1k / 100k / 1M records

The cost structure (Section 3) sets the scaling priorities: protect the deterministic path and
keep the review queue small; tokens take care of themselves.

- **NPI snapshot caching.** The CMS NPI Registry is downloadable in bulk. At 100k+ records,
  replace per-record API calls with a local monthly NPI snapshot — Stage 2 becomes a local
  join, $0 and rate-limit-free. The pipeline already isolates NPI fetch behind one injected
  function, so this is a dependency swap, not a rewrite. The same applies to per-state board
  rosters (Stage 2b).
- **Idempotent, cache-backed LLM.** Extraction is keyed by a prompt hash; re-runs over
  unchanged inputs are free and reproducible. Periodic runs only pay for records whose source
  content actually changed.
- **Embarrassingly parallel.** Records are independent. Stage 4/6 LLM calls fan out across
  workers; the audit log is append-only. The deterministic path already runs at ~2,000
  records/core-second (Section 3.5), so throughput scales horizontally with workers.
- **The review queue is the bottleneck to watch, not compute.** At 1M records and an 8.3%
  per-decision review rate that is **~170k reviews** (1M records = 2M field-decisions × 8.3%) —
  the thing to engineer down. Batching reviews by change type, pre-filling the analyst's view
  from the audit row (the dashboard in §6), and learning per-source weights from resolved
  reviews (Section 8) attack the one cost that actually scales with the directory.
- **Incremental operation.** "Stale selection" (Stage 1) means a periodic run touches only
  records past their re-verification horizon, not the whole directory — continuous upkeep, not
  a periodic full rescan.

The gated-LLM curve is the favorable one: inference cost scales with the **drift rate** (how
many records changed), not with directory size. A stable directory is cheap to keep stable.

---

## 8. Implementation roadmap

The prototype is a proof of the routing-and-cost machinery on address + phone, with four
sources (two free/authoritative, two gated). Production phasing, in cost-leverage order:

1. **Productionize the deterministic core** — bulk NPI + state-board snapshot joins; the
   is_active flip and the NPI-agreement `no_change` path are already $0 and ship as-is.
2. **Harden normalization** — swap the prototype's `usaddress`/regex normalizer for `libpostal`
   for international-grade address parsing; add phone-extension handling and specialty/taxonomy
   normalization against the NPPES taxonomy crosswalk; add an NPI check-digit (Luhn, prefix
   80840) validator as a $0 structural pre-filter.
3. **Real source acquisition under a safe policy** — replace fixtures with polite, robots-aware
   practice-site fetching (the included `scripts/fetch_fixtures.py` already respects robots.txt
   and rate-limits) and live per-state medical-board lookups behind the existing injected
   source seam.
4. **Human-review dashboard** — the audit table is the backing store and
   `scripts/make_review_queue.py` already renders the held queue; productionize it into a thin
   web app that writes the analyst's verdict back. Resolved verdicts become training labels.
5. **Learned weights and duplicate detection** — calibrate source weights and freshness
   half-lives from resolved-review outcomes (turn the 0.45/0.35/0.20/0.10 priors into measured
   posteriors); add record-linkage duplicate detection (provider × practice × location) as a
   pre-pass.
6. **Full-field rollout** — the scoring/routing/audit machinery is field-agnostic; extend from
   address+phone to practice name, specialty, and affiliations by adding extractors and weights.

This sequencing is itself a cost argument: every phase either widens the $0 deterministic path
or shrinks the review queue — the two terms that dominate the bill.

---

## Appendix — how this maps to the evaluation criteria

| Criterion | Where |
|---|---|
| **Accuracy** | Safe-auto-update property (§4): auto requires a third corroborating source; conflicts forced to review; the sponsor's own HL_001 reproduced end-to-end (`SHOW-MOVE`, §6). |
| **Scalability** | NPI/board snapshots, idempotent cache, parallelism, measured ~2,000 rec/core-sec deterministic throughput, drift-bound inference (§3.5, §7). |
| **Cost efficiency** | Tiered routing, gated LLM, **measured** per-1k cost with an LLM-everywhere baseline (~4.5×) and the labor-dominates insight (§3). |
| **Practicality** | ~1,260 lines (package, `wc -l`), stdlib SQLite, one injected-dependency seam; runs offline with one command. |
| **Explainability** | Per-decision `reason` (under-corroborated vs. conflict) + the full audit row (§5, §6). |
| **Data quality** | Phone/address normalization to comparable keys, demonstrated on a real address change (`SHOW-MOVE`); junk values normalize to "no match", not false agreement (§2 stage 3, §4). |
| **Source reliability** | Four weighted sources, two free/authoritative; auto-update reached through NPI+Website+**State Medical Board**, not the weak snippet; three-way conflict handling (§4, §2 stage 5). |
| **Human-review design** | Only conflicts + under-corroborated changes escalate (~8.3% observed) **plus a working review-queue dashboard** (§6). |
| **Audit trail** | One SQLite row per decision, every update traceable to sources + weights + freshness + score + gated-call cost (§5). |

**Bonus items addressed:** working prototype (73 tests), agent workflow diagram (§2),
cost-per-1k estimate (§3), confidence scoring formula (§4), **human-review dashboard**
(`make_review_queue.py`, §6), address normalization strategy (§2/§8, demonstrated in §6), NPI
Registry lookup + is_active (§2), practice-location matching (normalized address key),
provider-movement detection (the `SHOW-MOVE` address change), inactive-provider detection
(is_active flip), change history and audit log (§5), safe auto-update rules (§4), implementation
roadmap (§8). Duplicate detection and an NPI check-digit validator are described as near-term
roadmap items (§8), not claimed as built.

---

*Prototype: `provider_pipeline/` — run `python -m provider_pipeline.cli --fake-contacts
--show-examples` and `python -m pytest -q` (73 tests). Cost chart and sensitivity table:
`python scripts/make_cost_chart.py`; review queue: `python scripts/make_review_queue.py`. Full
design ↔ code traceability in `README.md`.*
