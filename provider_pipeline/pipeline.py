from __future__ import annotations
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Optional
from .config import Config
from .schemas import (
    ProviderRecord, CanonicalRecord, ContactTuple, SourceObservation,
    FieldChange, ChangeRecommendation, AuditRow, SOURCE_DISPLAY,
)
from .compare import field_existing, field_canonical, cross_source
from .confidence import freshness, score, route
from .normalize import normalize_phone, normalize_address


@dataclass
class FieldDecision:
    field: str
    old_value: Optional[str]
    new_value: Optional[str]
    confidence: float
    decision: str
    per_source: dict


@dataclass
class RecordResult:
    provider_id: str
    npi: str
    changes: list
    generated_at: datetime


@dataclass
class Deps:
    cfg: Config
    fetch_canonical: Callable[[str], Optional[CanonicalRecord]]
    extract_website: Callable[[ProviderRecord], tuple]
    extract_snippet: Callable[[ProviderRecord], tuple]
    cache_dir: Path
    # State Medical Board lookup: fixture-backed prototype of a free, deterministic
    # authoritative source (no LLM).
    # Returns (ContactTuple, 0). Defaults to "silent" so older callers/tests that
    # don't wire a board still work (the board simply contributes nothing).
    extract_board: Callable[[ProviderRecord], tuple] = lambda record: (ContactTuple(), 0)


def select_stale(records: list[ProviderRecord], cfg: Config,
                 today: Optional[date] = None) -> list[ProviderRecord]:
    """Stage 1 — only records past the re-verification horizon enter the pipeline;
    fresh records cost nothing. A periodic run touches the stale tail, not the whole
    directory (incremental upkeep, not a full rescan)."""
    today = today or datetime.now(timezone.utc).date()
    return [r for r in records
            if (today - r.last_verified_date).days >= cfg.stale_days]


def _contact_field(contact: ContactTuple, field: str) -> Optional[str]:
    if field == "phone":
        return normalize_phone(contact.phone)
    if contact.address_line is None:
        return None
    return normalize_address(contact.address_line, contact.city or "",
                             contact.state or "", contact.zip or "").key()


def _eq(a: Optional[str], b: Optional[str], field: str) -> bool:
    if a is None or b is None:
        return False
    if field == "phone":
        na = normalize_phone(a)
        return na is not None and na == normalize_phone(b)
    return a.strip().lower() == b.strip().lower()


def _age_days(observed_at: Optional[datetime], now: datetime) -> float:
    if observed_at is None:
        return 0.0
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    return max(0.0, (now - observed_at).total_seconds() / 86400.0)


def _emit_no_change(record, field, existing, npi_val, now, tokens=0, gated_calls=0,
                    npi_freshness: float = 1.0):
    fc = FieldDecision(field=field, old_value=existing, new_value=None,
                       confidence=0.0, decision="no_change", per_source={"npi": npi_val})
    row = AuditRow(provider_id=record.provider_id, field=field, old_value=existing,
                   new_value=None, per_source={"npi": npi_val},
                   per_source_weights={"npi": 0.45}, per_source_freshness={"npi": npi_freshness},
                   final_score=0.0, decision="no_change", llm_tokens=tokens,
                   gated_calls=gated_calls, wall_time_ms=0, timestamp=now)
    return fc, row


def run_record(record: ProviderRecord, deps: Deps):
    cfg = deps.cfg
    canonical = deps.fetch_canonical(record.npi)
    changes = []
    rows = []
    total_tokens = 0
    started = time.perf_counter()
    now = datetime.now(timezone.utc)
    npi_age = _age_days(canonical.fetched_at, now) if canonical else 0.0
    npi_freshness = freshness(npi_age, cfg.half_lives["npi"]) if canonical else 1.0

    # Extract each paid LLM source at most ONCE per record — the website page and
    # the search snippets are the same for every field, so a second field reuses the
    # first call (idempotent, like the prompt-hash cache). This keeps gated_calls a
    # count of UNIQUE paid calls; the first field to need a source pays for it.
    _memo: dict = {}

    def _gated(kind, fn):
        nonlocal total_tokens
        if kind in _memo:
            return _memo[kind][0], 0, False   # contact, incremental_tokens, newly_called
        contact, tok = fn(record)
        _memo[kind] = (contact, tok)
        total_tokens += tok
        return contact, tok, True

    # Deterministic is_active flip (stage 2/3, $0)
    if canonical is not None and canonical.is_active != record.is_active:
        changes.append(FieldDecision(
            field="is_active", old_value=str(record.is_active),
            new_value=str(canonical.is_active), confidence=1.0, decision="auto_update",
            per_source={"npi": str(canonical.is_active)}))
        rows.append(AuditRow(
            provider_id=record.provider_id, field="is_active",
            old_value=str(record.is_active), new_value=str(canonical.is_active),
            per_source={"npi": str(canonical.is_active)},
            per_source_weights={"npi": 1.0}, per_source_freshness={"npi": npi_freshness},
            final_score=1.0, decision="auto_update", llm_tokens=0,
            wall_time_ms=0, timestamp=now))

    for field in cfg.fields:
        existing = field_existing(record, field)
        npi_val = field_canonical(canonical, field) if canonical else None

        # Stage 3: NPI agrees with record -> no_change, $0
        if npi_val is not None and _eq(npi_val, existing, field):
            fc, row = _emit_no_change(
                record, field, existing, npi_val, now, npi_freshness=npi_freshness
            )
            changes.append(fc); rows.append(row); continue

        # Stage 4 (website LLM, gated): candidate change OR NPI silent. Memoized per
        # record, so only the first candidate field is charged a gated call.
        website_contact, tok_w, web_new = _gated("website", deps.extract_website)
        gated = 1 if web_new else 0
        website_val = _contact_field(website_contact, field)
        new_value = npi_val if npi_val is not None else website_val
        if new_value is None:
            fc, row = _emit_no_change(record, field, existing, None, now,
                                      tokens=tok_w, gated_calls=gated)
            changes.append(fc); rows.append(row); continue

        # Stage 5: cross-source routing
        case = cross_source(npi_val, website_val, existing, field)
        # Stage 2b: State Medical Board — fixture-backed prototype of a free,
        # deterministic authoritative source, observed alongside NPI and website
        # for every candidate change ($0, no LLM).
        board_contact, _tok_b = deps.extract_board(record)
        board_val = _contact_field(board_contact, field)
        obs = [
            SourceObservation(source="npi", field=field, value=npi_val,
                              freshness=npi_freshness, observed_at=now),
            SourceObservation(source="website", field=field, value=website_val,
                              freshness=freshness(0, cfg.half_lives["website"]), observed_at=now),
            SourceObservation(source="board", field=field, value=board_val,
                              freshness=freshness(0, cfg.half_lives["board"]), observed_at=now),
        ]
        s = score(obs, new=new_value, old=existing, field=field, cfg=cfg)
        tokens = tok_w
        per_source = {"npi": npi_val, "website": website_val, "board": board_val}
        board_agrees_existing = _eq(board_val, existing, field)
        board_disagrees_with_new = board_val is not None and not _eq(board_val, new_value, field)

        if case == "false_alarm" and (board_val is None or board_agrees_existing):
            fc, row = _emit_no_change(record, field, existing, npi_val, now,
                                      tokens=tok_w, gated_calls=gated)
            fc.per_source = per_source
            row.per_source = per_source
            row.per_source_weights = {o.source: cfg.source_weights[o.source] for o in obs}
            row.per_source_freshness = {o.source: o.freshness for o in obs}
            changes.append(fc); rows.append(row); continue

        # Stage 6 (snippet LLM, gated): only if still below auto and not conflict —
        # i.e. the authoritative board was silent and a third confirmation is needed.
        if case != "conflict" and board_val is None and s < cfg.auto_threshold:
            snippet_contact, tok_s, snip_new = _gated("snippet", deps.extract_snippet)
            tokens += tok_s; gated += 1 if snip_new else 0
            snippet_val = _contact_field(snippet_contact, field)
            obs.append(SourceObservation(source="snippet", field=field, value=snippet_val,
                                         freshness=freshness(0, cfg.half_lives["snippet"]), observed_at=now))
            per_source["snippet"] = snippet_val
            s = score(obs, new=new_value, old=existing, field=field, cfg=cfg)

        decision = "human_review" if case == "conflict" or board_disagrees_with_new else route(s, cfg)
        weights = {o.source: cfg.source_weights[o.source] for o in obs}
        fresh = {o.source: o.freshness for o in obs}
        changes.append(FieldDecision(field=field, old_value=existing, new_value=new_value,
                                     confidence=s, decision=decision, per_source=per_source))
        rows.append(AuditRow(
            provider_id=record.provider_id, field=field, old_value=existing,
            new_value=new_value, per_source=per_source, per_source_weights=weights,
            per_source_freshness=fresh, final_score=s, decision=decision,
            llm_tokens=tokens, gated_calls=gated, wall_time_ms=0, timestamp=now))

    wall_ms = int((time.perf_counter() - started) * 1000)
    for r in rows:
        if r.field != "is_active":
            r.wall_time_ms = wall_ms
    result = RecordResult(provider_id=record.provider_id, npi=record.npi,
                          changes=changes, generated_at=now)
    telem = {"llm_tokens": total_tokens, "wall_time_ms": wall_ms}
    return result, rows, telem


def _join_fields(changes) -> str:
    names = [c.field for c in changes]
    if len(names) <= 1:
        return names[0] if names else ""
    return ", ".join(names[:-1]) + " and " + names[-1]


def _reason(action: str, changes, has_source_conflict: bool = False) -> str:
    if action == "no_change":
        return "All checked fields match the NPI Registry; no update needed."
    fields = _join_fields(changes)
    if action == "auto_update":
        return f"Updated {fields} confirmed by multiple reliable sources."
    # human_review splits two ways: sources that agree but fall short of the
    # auto-update corroboration bar, vs. sources that genuinely disagree.
    if not has_source_conflict and changes and all(len(c.supporting_sources) >= 2 for c in changes):
        return (f"Sources agree on {fields} but corroboration is below the "
                f"auto-update threshold; manual confirmation recommended.")
    return f"Sources disagree on {fields}; manual verification recommended."


def _has_source_conflict(change: FieldDecision) -> bool:
    if change.new_value is None:
        return False
    return any(val is not None and not _eq(val, change.new_value, change.field)
               for val in change.per_source.values())


def _raw_field(record, field):
    if field == "phone":
        return record.phone
    if field == "address":
        return record.address
    if field == "is_active":
        return str(record.is_active)
    return ""


def _display(value, field):
    if value is None:
        return None
    if field == "phone":
        d = re.sub(r"\D", "", value)
        return f"{d[:3]}-{d[3:6]}-{d[6:10]}" if len(d) >= 10 else value
    if field == "address":
        parts = value.split("|")
        if len(parts) == 4:
            street, city, state, zp = parts
            return f"{street.title()}, {city.title()}, {state.upper()} {zp}"
        return value
    return value


def to_recommendation(result: RecordResult, record: ProviderRecord) -> ChangeRecommendation:
    sponsor_changes = []
    has_source_conflict = False
    for c in result.changes:
        if c.decision == "no_change":
            continue
        has_source_conflict = has_source_conflict or _has_source_conflict(c)
        supporting = [SOURCE_DISPLAY.get(src, src)
                      for src, val in c.per_source.items()
                      if _eq(val, c.new_value, c.field)]
        sponsor_changes.append(FieldChange(
            field=c.field,
            old_value=_raw_field(record, c.field),
            new_value=_display(c.new_value, c.field),
            confidence_score=round(c.confidence, 2),
            supporting_sources=supporting))
    change_detected = len(sponsor_changes) > 0
    decisions = [c.decision for c in result.changes if c.decision != "no_change"]
    if any(d == "human_review" for d in decisions):
        action = "human_review"
    elif any(d == "auto_update" for d in decisions):
        action = "auto_update"
    else:
        action = "no_change"
    if sponsor_changes:
        overall = round(sum(fc.confidence_score for fc in sponsor_changes) / len(sponsor_changes), 2)
    else:
        overall = 1.0
    return ChangeRecommendation(
        provider_id=result.provider_id, npi=result.npi,
        change_detected=change_detected, changes=sponsor_changes,
        overall_confidence=overall, recommended_action=action,
        reason=_reason(action, sponsor_changes, has_source_conflict))
