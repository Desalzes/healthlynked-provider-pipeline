from datetime import datetime, timezone
from provider_pipeline.schemas import AuditRow
from provider_pipeline.audit import AuditLog


def _row(decision="auto_update", tokens=30, gated_calls=2):
    return AuditRow(
        provider_id="P1", field="phone", old_value="2395550000", new_value="2395559999",
        per_source={"npi": "2395559999", "website": "2395559999", "board": "2395559999"},
        per_source_weights={"npi": 0.45, "website": 0.35, "board": 0.20},
        per_source_freshness={"npi": 1.0, "website": 0.9, "board": 0.8},
        final_score=1.0, decision=decision, llm_tokens=tokens, gated_calls=gated_calls,
        wall_time_ms=12, timestamp=datetime.now(timezone.utc),
    )


def test_write_and_read_back(tmp_path):
    log = AuditLog(tmp_path / "audit.db")
    log.write(_row())
    rows = log.all()
    assert len(rows) == 1
    assert rows[0]["decision"] == "auto_update"
    assert rows[0]["per_source"]["npi"] == "2395559999"
    assert rows[0]["gated_calls"] == 2
    log.close()


def test_summary_aggregates_gated_calls(tmp_path):
    log = AuditLog(tmp_path / "audit.db")
    log.write(_row("auto_update", 30, gated_calls=1))
    log.write(_row("human_review", 50, gated_calls=2))
    log.write(_row("no_change", 0, gated_calls=0))
    assert log.summary()["gated_calls_total"] == 3
    log.close()


def test_summary_aggregates_cost(tmp_path):
    log = AuditLog(tmp_path / "audit.db")
    log.write(_row("auto_update", 30))
    log.write(_row("no_change", 0))
    log.write(_row("human_review", 50))
    s = log.summary()
    assert s["counts"]["auto_update"] == 1
    assert s["counts"]["no_change"] == 1
    assert s["total_llm_tokens"] == 80
    assert s["decisions_total"] == 3
    log.close()


def test_fresh_resets_existing_rows(tmp_path):
    db = tmp_path / "audit.db"
    first = AuditLog(db)
    first.write(_row())
    first.write(_row())
    first.close()
    # Reopening with fresh=True must drop the prior run's rows, not append.
    second = AuditLog(db, fresh=True)
    second.write(_row())
    assert second.summary()["decisions_total"] == 1
    second.close()
    # Default (append) reopen still sees the single fresh row plus a new one.
    third = AuditLog(db)
    third.write(_row())
    assert third.summary()["decisions_total"] == 2
    third.close()
