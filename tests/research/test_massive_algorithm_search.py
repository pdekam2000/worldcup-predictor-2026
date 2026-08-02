"""Tests for massive algorithm search foundation."""

from __future__ import annotations

import json
from pathlib import Path

from worldcup_predictor.research.massive_algorithm_search import corpus as c
from worldcup_predictor.research.massive_algorithm_search import search_engine as s
from worldcup_predictor.research.massive_algorithm_search.foundation import run_foundation
from worldcup_predictor.research.massive_algorithm_search.inventory import run_inventory


def test_inventory_has_primary_db():
    inv = run_inventory()
    assert inv["primary_db"].endswith("football_intelligence.db")
    assert inv["reconciliation"].get("fixture_results_finished") is not None


def test_config_dedup_and_determinism():
    a = list(s.iter_search_space(500))
    b = list(s.iter_search_space(500))
    ha = [s.cfg_hash(x.to_dict()) for x in a]
    hb = [s.cfg_hash(x.to_dict()) for x in b]
    assert ha == hb
    assert len(ha) == len(set(ha))


def test_checkpoint_resume(tmp_path):
    rows = [
        c.MassiveRow(
            fixture_id=i,
            kickoff_utc=f"2026-07-{(i % 28) + 1:02d}T12:00:00+00:00",
            predicted_at=f"2026-07-{(i % 28) + 1:02d}T08:00:00+00:00",
            odds_snapshot_at=None,
            cohort=c.COHORT_IMMUTABLE,
            source="t",
            league="L",
            match="a",
            wde_decision="home",
            home_p=0.55,
            draw_p=0.25,
            away_p=0.20,
            confidence=60,
            no_bet=False,
            ecse_direction="home",
            top5_mass=0.55,
            top10_mass=0.8,
            entropy=1.5,
            lambda_home=1.2,
            lambda_away=0.9,
            odds_home=1.8,
            odds_draw=3.5,
            odds_away=4.5,
            actual_1x2="home" if i % 2 == 0 else "away",
            final_score="1-0",
            has_wde=True,
            has_ecse=True,
        )
        for i in range(1, 80)
    ]
    for r in rows:
        c._enrich_market(r)
    train, val = rows[:50], rows[50:]
    eng = s.SearchEngine(tmp_path / "s", target_n=300)
    cp1 = eng.run(train, val, max_new=100, checkpoint_every=50)
    assert cp1["tested"] == 100
    cp2 = eng.run(train, val, max_new=None, checkpoint_every=50)
    assert cp2["tested"] >= 300 or cp2["tested"] > cp1["tested"]
    assert (tmp_path / "s" / "experiment_checkpoint.json").exists()


def test_roi_and_metrics():
    r = c.MassiveRow(
        fixture_id=1,
        kickoff_utc="2026-07-01T12:00:00+00:00",
        predicted_at="2026-07-01T08:00:00+00:00",
        odds_snapshot_at=None,
        cohort=c.COHORT_IMMUTABLE,
        source="t",
        league="L",
        match="a",
        wde_decision="home",
        home_p=0.6,
        draw_p=0.2,
        away_p=0.2,
        confidence=70,
        no_bet=False,
        ecse_direction="home",
        top5_mass=0.6,
        top10_mass=0.9,
        entropy=1.4,
        lambda_home=1.4,
        lambda_away=0.8,
        odds_home=2.0,
        odds_draw=3.4,
        odds_away=4.0,
        actual_1x2="home",
        final_score="2-0",
        has_wde=True,
        has_ecse=True,
    )
    c._enrich_market(r)
    m = s.evaluate_bets([("home", r)], 1)
    assert m["accuracy"] == 1.0
    assert m["roi"] == 1.0


def test_chronological_split_holdout_sealed():
    rows = [
        c.MassiveRow(
            fixture_id=i,
            kickoff_utc=f"2026-08-{(i%28)+1:02d}T12:00:00+00:00",
            predicted_at=f"2026-08-{(i%28)+1:02d}T08:00:00+00:00",
            odds_snapshot_at=None,
            cohort=c.COHORT_IMMUTABLE,
            source="t",
            league="L",
            match="a",
            wde_decision="home",
            home_p=0.5,
            draw_p=0.3,
            away_p=0.2,
            confidence=60,
            no_bet=False,
            ecse_direction="home",
            top5_mass=0.5,
            top10_mass=0.8,
            entropy=1.5,
            lambda_home=1.1,
            lambda_away=1.0,
            odds_home=1.9,
            odds_draw=3.5,
            odds_away=4.0,
            actual_1x2="home",
            final_score="1-0",
            has_wde=True,
            has_ecse=True,
        )
        for i in range(1, 21)
    ]
    sp = c.chrono_split(rows)
    assert len(sp["train"]) == 12
    assert len(sp["holdout_sealed"]) == 4


def test_foundation_smoke(tmp_path):
    v = run_foundation(out_dir=tmp_path / "m", target_n=500)
    assert v["status"] in {
        "MASSIVE_SEARCH_FOUNDATION_AND_100K_COMPLETE",
        "MASSIVE_SEARCH_DATA_CORPUS_BLOCKED",
        "MASSIVE_SEARCH_VALIDATION_FAILED",
    }
    assert v["not_deployed"] is True
    assert v["canonical_unchanged"] is True
    assert v["wde_unchanged"] is True
    assert v["ecse_unchanged"] is True
    assert v["no_auto_promotion"] is True
    assert v["no_result_leakage"] is True
    assert v["target_75_claimed"] is False
    assert v["sealed_holdout_status"] == "SEALED_UNOPENED"
    assert (tmp_path / "m" / "database_inventory.json").exists()
    assert (tmp_path / "m" / "experiment_checkpoint.json").exists()
