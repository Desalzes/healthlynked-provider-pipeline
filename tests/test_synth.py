from provider_pipeline.synth import generate


def test_generate_is_deterministic():
    a = generate(seed=7)
    b = generate(seed=7)
    assert [r.provider_id for r in a] == [r.provider_id for r in b]


def test_generate_includes_showcase_records():
    recs = generate(seed=7)
    ids = {r.provider_id for r in recs}
    assert {"SHOW-MOVE", "SHOW-AUTO", "SHOW-REVIEW", "SHOW-CONFLICT"} <= ids


def test_generate_count_and_shape():
    recs = generate(seed=7, n=50)
    assert len(recs) == 50 + 4   # 50 random + 4 showcase
    r = recs[0]
    assert r.npi.isdigit() and len(r.npi) == 10
    assert r.address and r.provider_name and r.practice_name
    assert "," in r.address   # single-line "street, city, ST zip"
