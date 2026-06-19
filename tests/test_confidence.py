from datetime import datetime, timezone
from provider_pipeline.config import Config
from provider_pipeline.schemas import SourceObservation
from provider_pipeline.confidence import freshness, score, route

CFG = Config()


def test_freshness_decays_by_half_life():
    assert freshness(0, 90) == 1.0
    assert abs(freshness(90, 90) - 0.5) < 1e-9
    assert freshness(10_000, 30) >= 0.0


def _obs(source, value, fresh):
    return SourceObservation(source=source, field="phone", value=value,
                             freshness=fresh, observed_at=datetime.now(timezone.utc))


def test_score_two_sources_capped_below_auto():
    # NPI (0.45) + Practice Website (0.35) = 0.80 < 0.85 — the safe-auto moat:
    # the two strongest sources alone never auto-update.
    obs = [_obs("npi", "2395559999", 1.0), _obs("website", "2395559999", 1.0)]
    s = score(obs, new="2395559999", old="2395550000", field="phone", cfg=CFG)
    assert abs(s - 0.80) < 1e-9
    assert route(s, CFG) == "human_review"


def test_three_authoritative_sources_reach_auto():
    # NPI + Website + State Medical Board = 1.00 — auto via authoritative sources,
    # not the weak web snippet.
    obs = [_obs("npi", "2395559999", 1.0), _obs("website", "2395559999", 1.0),
           _obs("board", "2395559999", 1.0)]
    s = score(obs, new="2395559999", old="2395550000", field="phone", cfg=CFG)
    assert abs(s - 1.0) < 1e-9
    assert route(s, CFG) == "auto_update"


def test_snippet_is_a_valid_fallback_third_source():
    # When the board is silent, the web snippet (0.10) can still tip a 2-source
    # agreement over the bar: 0.45 + 0.35 + 0.10 = 0.90 >= 0.85.
    obs = [_obs("npi", "2395559999", 1.0), _obs("website", "2395559999", 1.0),
           _obs("snippet", "2395559999", 1.0)]
    s = score(obs, new="2395559999", old="2395550000", field="phone", cfg=CFG)
    assert abs(s - 0.90) < 1e-9
    assert route(s, CFG) == "auto_update"


def test_four_source_agreement_clamps_to_one():
    obs = [_obs("npi", "2395559999", 1.0), _obs("website", "2395559999", 1.0),
           _obs("board", "2395559999", 1.0), _obs("snippet", "2395559999", 1.0)]
    s = score(obs, new="2395559999", old="2395550000", field="phone", cfg=CFG)
    assert s == 1.0


def test_route_below_review_is_no_change():
    assert route(0.40, CFG) == "no_change"
    assert route(0.60, CFG) == "human_review"
    assert route(0.90, CFG) == "auto_update"
