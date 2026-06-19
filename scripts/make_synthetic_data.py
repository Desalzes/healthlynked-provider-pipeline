import json
from pathlib import Path
from provider_pipeline.synth import generate

OUT = Path(__file__).resolve().parents[1] / "data" / "synthetic_providers.json"


def main() -> None:
    recs = generate(seed=7, n=50)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps([r.model_dump(mode="json") for r in recs], indent=2), encoding="utf-8")
    print(f"wrote {len(recs)} records -> {OUT}")


if __name__ == "__main__":
    main()
