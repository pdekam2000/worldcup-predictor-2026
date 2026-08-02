"""Tests for Prediction Engine 75% Phase 3 specialists + meta."""

from __future__ import annotations

import json

from worldcup_predictor.research.prediction_engine_75 import phase2 as p2
from worldcup_predictor.research.prediction_engine_75 import phase3 as m


def _row(**kwargs) -> p2.RowV2:
    base = dict(
        fixture_id=1,
        kickoff_utc="2026-07-01T12:00:00+00:00",
        predicted_at="2026-07-01T08:00:00+00:00",
        frozen_at="2026-07-01T08:00:00+00:00",
        freeze_id="f",
        freeze_hash=None,
        cohort=p2.COHORT_PREMATCH,
        source="test",
        league="L1",
        match="A vs B",
        wde_decision="home",
        ft_marginal="home",
        home_p=0.55,
        draw_p=0.25,
        away_p=0.20,
        confidence=60,
        no_bet=False,
        odds_home=1.70,
        odds_draw=3.60,
        odds_away=5.00,
        implied_home=0.52,
        implied_draw=0.25,
        implied_away=0.23,
        book_margin=0.05,
        favorite_strength=0.59,
        balanced_market=False,
        lambda_home=1.3,
        lambda_away=0.9,
        top5_mass=0.55,
        entropy=1.5,
        ecse_direction="home",
        actual_1x2="home",
        final_score="1-0",
    )
    base.update(kwargs)
    r = p2.RowV2(**base)
    p2.enrich_odds_metrics(r)
    return r


def test_regime_tags_favorite_failure_and_draw():
    r = _row(wde_decision="home", actual_1x2="away", odds_home=1.4, odds_draw=4.5, odds_away=7.0)
    p2.enrich_odds_metrics(r)
    tags = m.tag_regimes(r)
    assert "Favorite_Failure" in tags
    assert "Underdog_Breakout" in tags
    r2 = _row(wde_decision="home", actual_1x2="draw")
    assert "Draw_Underranked" in m.tag_regimes(r2)


def test_routing_balanced_to_draw_and_high_entropy_abstain():
    fitted = {n: m.FittedSpecialist(n, None, 0, [], {}, "DATA_LIMITED") for n in m.SPECIALISTS}
    # Nearly even 1X2 odds → balanced_market True after enrich
    r = _row(odds_home=2.45, odds_draw=3.20, odds_away=2.85, entropy=1.2, lambda_home=1.5, lambda_away=1.4)
    p2.enrich_odds_metrics(r)
    assert r.balanced_market is True
    md = m.meta_decide(r, fitted)
    assert md.chosen_specialist == "Draw_Specialist"
    # force high entropy abstain
    r2 = _row(entropy=1.9)
    md2 = m.meta_decide(r2, fitted)
    assert md2.chosen_specialist == "ABSTAIN"
    assert md2.abstain_probability >= 0.8


def test_routing_heavy_favorite():
    fitted = {n: m.FittedSpecialist(n, None, 0, [], {}, "DATA_LIMITED") for n in m.SPECIALISTS}
    r = _row(odds_home=1.30, odds_draw=5.0, odds_away=9.0, entropy=1.2, balanced_market=False)
    p2.enrich_odds_metrics(r)
    md = m.meta_decide(r, fitted)
    assert md.chosen_specialist == "Heavy_Favorite_Specialist"


def test_specialist_determinism_and_calibration_fields():
    train = []
    for i in range(1, 40):
        train.append(
            _row(
                fixture_id=i,
                kickoff_utc=f"2026-07-{(i % 28) + 1:02d}T12:00:00+00:00",
                actual_1x2="home" if i % 3 else "away",
                odds_home=1.6 + (i % 5) * 0.05,
            )
        )
    sp = m.fit_specialist("Favorite_Specialist", train)
    assert sp.name == "Favorite_Specialist"
    pr = m.predict_specialist(sp, train[0])
    assert pr.abstain_probability is not None
    assert pr.confidence is not None or not pr.eligible


def test_candidate_lock_disables_tuning():
    wf = {
        "models": {
            "meta_model": {"mean_accuracy": 0.55, "median_accuracy": 0.54, "worst_accuracy": 0.4, "mean_n": 12, "folds_with_metric": 5},
            "canonical_wde": {"mean_accuracy": 0.50, "median_accuracy": 0.5, "worst_accuracy": 0.3, "mean_n": 15, "folds_with_metric": 5},
        }
    }
    lock = m.lock_candidates(wf, {})
    assert lock["phase1_holdout_opened"] is False
    assert lock["promotion"] is False
    assert all(c["tuning_allowed_after_lock"] is False for c in lock["locked_candidates"])


def test_no_leakage_late_goal_not_invented():
    regimes = m.discover_error_regimes([_row(wde_decision="home", actual_1x2="away", final_score="2-1")])
    assert regimes["regimes"]["Late_Goal_Pattern"]["n"] == 0
    assert regimes["regimes"]["Late_Goal_Pattern"]["status"].startswith("UNAVAILABLE")


def test_phase3_smoke(tmp_path):
    v = m.run_phase3(out_dir=tmp_path / "p3")
    assert v["status"] in {m.STATUS_COMPLETE, m.STATUS_LIMITED, m.STATUS_FAILED}
    assert v["not_deployed"] is True
    assert v["canonical_unchanged"] is True
    assert v["wde_unchanged"] is True
    assert v["ecse_unchanged"] is True
    assert v["no_auto_promotion"] is True
    assert v["sealed_holdout_status"] == "SEALED_UNOPENED"
    assert v["target_75_claimed"] is False
    assert (tmp_path / "p3" / "specialist_models.json").exists()
    assert (tmp_path / "p3" / "meta_model.json").exists()
    assert (tmp_path / "p3" / "candidate_leaderboard.csv").exists()
    lock = json.loads((tmp_path / "p3" / "sealed_holdout_status.json").read_text(encoding="utf-8"))
    assert lock["phase1_holdout"]["opened"] is False
