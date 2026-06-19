from pathlib import Path
from provider_pipeline.synth import generate
from provider_pipeline.synth_fixtures import build_fixtures

FIX = Path(__file__).resolve().parents[1] / "data" / "fixtures"


def main() -> None:
    recs = generate(seed=7, n=50)
    routes = build_fixtures(recs, fixtures_dir=FIX)
    from collections import Counter
    print("route plan:", dict(Counter(routes.values())))


if __name__ == "__main__":
    main()
