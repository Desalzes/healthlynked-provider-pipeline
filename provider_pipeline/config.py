import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Config:
    stale_days: int = 180
    fields: tuple[str, ...] = ("address", "phone")
    # Source reliability weights (raw, deliberately NOT normalized to 1.0 — see
    # WRITEUP §4 safe-auto-update rule). NPI Registry + Practice Website cap at
    # 0.80 < auto_threshold, so an auto-update always needs a third corroborating
    # source; the authoritative State Medical Board (0.20) is the primary third
    # source, with the web-search snippet (0.10) as a fallback when the board is
    # silent. A four-source agreement clamps at 1.0 (see confidence.score).
    source_weights: dict[str, float] = field(
        default_factory=lambda: {"npi": 0.45, "website": 0.35, "board": 0.20, "snippet": 0.10}
    )
    half_lives: dict[str, int] = field(
        default_factory=lambda: {"npi": 90, "website": 30, "board": 120, "snippet": 14}
    )
    auto_threshold: float = 0.85
    review_threshold: float = 0.55

    @property
    def llm_model(self) -> str:
        return os.environ.get("PIPELINE_LLM_MODEL", "deepseek/deepseek-chat")
