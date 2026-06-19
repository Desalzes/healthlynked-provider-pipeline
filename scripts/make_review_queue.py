from pathlib import Path
from provider_pipeline.audit import AuditLog
from provider_pipeline.review_queue import render_review_queue

OUT = Path(__file__).resolve().parents[1] / "out"


def main() -> None:
    log = AuditLog(OUT / "audit.db")
    summary = log.summary()
    rows = log.all()
    log.close()
    if summary["decisions_total"] == 0:
        raise SystemExit(
            "out/audit.db is empty - run `python -m provider_pipeline.cli "
            "--fake-contacts` first, then re-run this script."
        )
    out_file = OUT / "review_queue.html"
    out_file.write_text(render_review_queue(rows), encoding="utf-8")
    held = summary["counts"]["human_review"]
    print(f"wrote {out_file} ({held} decisions in the review queue)")


if __name__ == "__main__":
    main()
