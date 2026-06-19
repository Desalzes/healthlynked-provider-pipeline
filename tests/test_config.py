from provider_pipeline.config import Config


def test_source_weights_and_safe_auto_property():
    cfg = Config()
    assert cfg.source_weights["npi"] == 0.45
    assert cfg.source_weights["website"] == 0.35
    assert cfg.source_weights["board"] == 0.20
    assert cfg.source_weights["snippet"] == 0.10
    # The safe-auto-update moat: the two strongest sources alone fall below the
    # auto bar, so an auto-update always needs a third corroborating source.
    assert cfg.source_weights["npi"] + cfg.source_weights["website"] < cfg.auto_threshold
    # Weights are deliberately NOT normalized to 1.0 (raw sum > 1; score clamps).
    assert sum(cfg.source_weights.values()) > 1.0


def test_thresholds_and_fields():
    cfg = Config()
    assert cfg.auto_threshold == 0.85
    assert cfg.review_threshold == 0.55
    assert cfg.stale_days == 180
    assert cfg.fields == ("address", "phone")
    assert cfg.half_lives == {"npi": 90, "website": 30, "board": 120, "snippet": 14}


def test_llm_model_env_override(monkeypatch):
    monkeypatch.setenv("PIPELINE_LLM_MODEL", "ollama/qwen3:14b")
    assert Config().llm_model == "ollama/qwen3:14b"


def test_llm_model_default(monkeypatch):
    monkeypatch.delenv("PIPELINE_LLM_MODEL", raising=False)
    assert Config().llm_model == "deepseek/deepseek-chat"
