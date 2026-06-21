from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from .schemas import AuditRow

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id TEXT, field TEXT, old_value TEXT, new_value TEXT,
    per_source TEXT, per_source_weights TEXT, per_source_freshness TEXT,
    final_score REAL, decision TEXT, llm_tokens INTEGER,
    gated_calls INTEGER DEFAULT 0,
    wall_time_ms INTEGER, timestamp TEXT
);
"""


class AuditLog:
    def __init__(self, db_path, fresh: bool = False):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        if fresh:
            self.conn.execute("DROP TABLE IF EXISTS audit")
        self.conn.executescript(_SCHEMA)

    def write(self, row: AuditRow) -> None:
        self.conn.execute(
            "INSERT INTO audit (provider_id, field, old_value, new_value, per_source, "
            "per_source_weights, per_source_freshness, final_score, decision, llm_tokens, "
            "gated_calls, wall_time_ms, timestamp) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (row.provider_id, row.field, row.old_value, row.new_value,
             json.dumps(row.per_source), json.dumps(row.per_source_weights),
             json.dumps(row.per_source_freshness), row.final_score, row.decision,
             row.llm_tokens, row.gated_calls, row.wall_time_ms, row.timestamp.isoformat()),
        )
        self.conn.commit()

    def all(self) -> list[dict]:
        out = []
        for r in self.conn.execute("SELECT * FROM audit ORDER BY id"):
            d = dict(r)
            for col in ("per_source", "per_source_weights", "per_source_freshness"):
                d[col] = json.loads(d[col])
            out.append(d)
        return out

    def summary(self) -> dict:
        counts = {"auto_update": 0, "human_review": 0, "no_change": 0}
        total_tokens, total_wall, total_gated, n = 0, 0, 0, 0
        for r in self.conn.execute(
                "SELECT decision, llm_tokens, gated_calls, wall_time_ms FROM audit"):
            counts[r["decision"]] = counts.get(r["decision"], 0) + 1
            total_tokens += r["llm_tokens"]
            total_gated += r["gated_calls"] or 0
            total_wall += r["wall_time_ms"]
            n += 1
        records_total = self.conn.execute(
            "SELECT COUNT(DISTINCT provider_id) AS n FROM audit"
        ).fetchone()["n"]
        return {
            "counts": counts,
            "records_total": records_total,
            "decisions_total": n,
            "total_llm_tokens": total_tokens,
            "mean_llm_tokens": (total_tokens / n) if n else 0.0,
            "mean_wall_ms": (total_wall / n) if n else 0.0,
            # gated_calls_total counts the paid LLM extraction stages actually
            # invoked (website + snippet), regardless of whether the offline
            # regex extractor or a live LLM served them — so the cost model can be
            # measured (call count) rather than modeled even in the $0 demo.
            "gated_calls_total": total_gated,
            "llm_calls": sum(1 for r in self.conn.execute(
                "SELECT llm_tokens FROM audit WHERE llm_tokens > 0")),
        }

    def close(self) -> None:
        self.conn.close()
