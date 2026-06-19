from provider_pipeline.synth import generate
from provider_pipeline.synth_fixtures import plan_routes, build_fixtures


def test_plan_routes_has_all_buckets():
    recs = generate(seed=7, n=50)
    routes = plan_routes(recs)
    kinds = set(routes.values())
    assert {"match", "auto", "review", "conflict"} <= kinds


def test_build_fixtures_writes_npi_per_record(tmp_path):
    recs = generate(seed=7, n=50)
    build_fixtures(recs, fixtures_dir=tmp_path)
    routes = plan_routes(recs)
    # every NON-showcase record gets an NPI fixture (showcase fixtures are owned elsewhere)
    for r in recs:
        if r.provider_id.startswith("SHOW"):
            continue
        assert (tmp_path / "npi" / f"{r.npi}.json").exists()
    drift = next(r for r in recs if routes[r.provider_id] in ("auto", "review", "conflict")
                and not r.provider_id.startswith("SHOW"))
    matched = next(r for r in recs if routes[r.provider_id] == "match")
    assert (tmp_path / "websites" / f"{drift.provider_id}.html").exists()
    assert not (tmp_path / "websites" / f"{matched.provider_id}.html").exists()
