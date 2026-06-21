from provider_pipeline.review_queue import render_review_queue


def _row(decision, **over):
    base = dict(provider_id="P1", field="phone", old_value="2395550000",
                new_value="2395559999", final_score=0.80, decision=decision,
                per_source={"npi": "2395559999", "website": "2395559999"},
                per_source_weights={"npi": 0.45, "website": 0.35},
                per_source_freshness={"npi": 1.0, "website": 1.0})
    base.update(over)
    return base


def test_renders_only_held_rows():
    rows = [_row("human_review"), _row("auto_update"), _row("no_change")]
    html = render_review_queue(rows)
    assert "held for review" in html
    # one held row -> header <tr> + exactly one data <tr>; auto/no_change excluded
    assert html.count("<tr>") == 2


def test_under_corroborated_vs_conflict_labelled():
    under = _row("human_review", per_source={"npi": "2395559999", "website": "2395559999"})
    conflict = _row("human_review", provider_id="P2",
                    per_source={"npi": "2395559999", "website": "2395558888"})
    html = render_review_queue([under, conflict])
    assert "under-corroborated" in html
    assert "source conflict" in html
    # human-readable values, not normalized keys
    assert "239-555-9999" in html
    assert "|" not in html.split("<tbody>")[1]


def test_board_disagreement_is_labelled_source_conflict():
    row = _row(
        "human_review",
        new_value="2395559999",
        per_source={"npi": "2395559999", "website": "2395559999", "board": "2395550000"},
        per_source_weights={"npi": 0.45, "website": 0.35, "board": 0.20},
        per_source_freshness={"npi": 1.0, "website": 1.0, "board": 1.0},
    )

    html = render_review_queue([row])

    assert "source conflict" in html


def test_empty_queue_message():
    html = render_review_queue([_row("auto_update")])
    assert "No records need review" in html
