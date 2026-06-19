from __future__ import annotations
from .config import Config
from .schemas import SourceObservation, Decision
from .normalize import agreement


def freshness(age_days: float, half_life_days: float) -> float:
    if age_days <= 0:
        return 1.0
    return max(0.0, min(1.0, 0.5 ** (age_days / half_life_days)))


def score(observations: list[SourceObservation], *, new: str, old: str,
          field: str, cfg: Config) -> float:
    total = 0.0
    for o in observations:
        w = cfg.source_weights.get(o.source, 0.0)
        a = agreement(o.value, new=new, old=old, field=field)
        total += w * a * max(0.0, min(1.0, o.freshness))
    # Weights sum to >1.0 (four sources), so a full agreement is clamped to 1.0;
    # confidence is reported on a [0, 1] scale.
    return round(min(1.0, total), 6)


def route(s: float, cfg: Config) -> Decision:
    if s >= cfg.auto_threshold:
        return "auto_update"
    if s >= cfg.review_threshold:
        return "human_review"
    return "no_change"
