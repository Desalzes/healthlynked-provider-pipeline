from __future__ import annotations
import html
import json
from typing import Optional
from .pipeline import _display

# Renders the human-review queue from audit rows into a self-contained static HTML
# table — the reviewer-facing surface the audit log already backs. Pure function
# (rows -> HTML string) so it is unit-testable; the script wrapper writes the file.

_CSS = """
body{font:14px/1.5 system-ui,sans-serif;margin:2rem;color:#222}
h1{font-size:1.3rem} .sub{color:#666;margin-bottom:1rem}
table{border-collapse:collapse;width:100%} th,td{border:1px solid #ddd;padding:6px 9px;text-align:left;vertical-align:top}
th{background:#264653;color:#fff;font-weight:600} tr:nth-child(even){background:#f7f7f7}
.conflict{color:#9b2226;font-weight:600} .under{color:#bb6b00;font-weight:600}
.src{font-family:ui-monospace,monospace;font-size:12px;white-space:pre}
.score{text-align:right;font-variant-numeric:tabular-nums}
"""


def _reason_class(row: dict) -> tuple[str, str]:
    ps = row.get("per_source", {})
    if (ps.get("npi") is not None and ps.get("website") is not None
            and ps["npi"] != ps["website"]):
        return "conflict", "source conflict"
    return "under", "under-corroborated"


def _sources_cell(row: dict) -> str:
    ps = row.get("per_source", {})
    w = row.get("per_source_weights", {})
    fr = row.get("per_source_freshness", {})
    lines = []
    for src, val in ps.items():
        disp = _display(val, row["field"]) if val is not None else "(silent)"
        lines.append(f"{src:8} w={w.get(src, 0):.2f} f={fr.get(src, 1):.2f}  {disp}")
    return html.escape("\n".join(lines))


def render_review_queue(rows: list[dict]) -> str:
    held = [r for r in rows if r["decision"] == "human_review"]
    body = []
    for r in held:
        cls, label = _reason_class(r)
        old = html.escape(_display(r.get("old_value"), r["field"]) or "")
        new = html.escape(_display(r.get("new_value"), r["field"]) or "")
        body.append(
            f"<tr><td>{html.escape(r['provider_id'])}</td><td>{html.escape(r['field'])}</td>"
            f"<td>{old}</td><td>{new}</td>"
            f"<td class='score'>{r['final_score']:.2f}</td>"
            f"<td class='{cls}'>{label}</td>"
            f"<td class='src'>{_sources_cell(r)}</td></tr>"
        )
    rows_html = "\n".join(body) or "<tr><td colspan='7'>No records need review.</td></tr>"
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>Provider directory — human review queue</title><style>{_CSS}</style></head>"
        "<body><h1>Human review queue</h1>"
        f"<p class='sub'>{len(held)} record-field decisions held for review. "
        "Each shows the per-source value, weight, and freshness behind the score, so a "
        "reviewer can confirm or reject without leaving this view.</p>"
        "<table><thead><tr><th>Provider</th><th>Field</th><th>Current</th><th>Proposed</th>"
        "<th>Score</th><th>Why held</th><th>Sources (value · weight · freshness)</th></tr></thead>"
        f"<tbody>{rows_html}</tbody></table></body></html>"
    )
