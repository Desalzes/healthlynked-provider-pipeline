"""Integration: the $0 data-quality screen runs through the actual product CLI
entry point (not just the standalone script), over the planted demo set."""
import json
from pathlib import Path
from provider_pipeline.cli import main

DEMO = Path(__file__).resolve().parents[1] / "data" / "dataquality_demo.json"


def test_cli_data_quality_screen_reports_and_writes(tmp_path, capsys):
    rc = main(["--data", str(DEMO), "--data-quality", "--db", str(tmp_path / "audit.db")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "invalid_npi=1" in out
    assert "duplicate_clusters=2" in out

    report = json.loads((tmp_path / "data_quality.json").read_text(encoding="utf-8"))
    assert report["invalid_npi"] == ["HL-BAD-1"]
    assert report["duplicate_clusters"] == [["HL-DUP-A", "HL-DUP-B"], ["HL-DUP-C", "HL-DUP-D"]]


def test_cli_data_quality_is_screen_only_no_pipeline_run(tmp_path):
    # Screen mode must short-circuit before the staged pipeline — no audit DB written.
    rc = main(["--data", str(DEMO), "--data-quality", "--db", str(tmp_path / "audit.db")])
    assert rc == 0
    assert not (tmp_path / "audit.db").exists()
