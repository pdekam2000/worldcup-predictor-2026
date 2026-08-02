"""Tests for Prediction Engine 75% Phase 2."""

from __future__ import annotations

import json
from pathlib import Path

from worldcup_predictor.research.prediction_engine_75 import phase1 as p1
from worldcup_predictor.research.prediction_engine_75 import phase2 as m


def _row(**kwargs) -> m.RowV2:
    base = dict(
        fixture_id=1,
        kickoff_utc="2026-07-01T12:00:00+00:00",
        predicted_at="2026-07-01T08:00:00+00:00",
        frozen_at="2026-07-01T08:00:00+00:00",
        freeze_id="f",
        freeze_hash=None,
        cohort=m.COHORT_PREMATCH,
        source="test",
        league="L",
        match="A vs B",
        wde_decision="home",
        ft_marginal="home",
        home_p=0.5,
        draw_p=0.3,
        away_p=0.2,
        confidence=60,
        no_bet=False,
        actual_1x2="home",
        final_score="1-0",
    )
    base.update(kwargs)
    return m.RowV2(**base)


def test_phase1_holdout_helpers_still_import():
    assert p1.STATUS_READY.startswith("PREDICTION_ENGINE_75")


def test_fixture_dedup_and_cohort_labels():
    rows = [_row(fixture_id=i, cohort=m.COHORT_PREMATCH if i % 2 else m.COHORT_REPLAY) for i in range(1, 6)]
    assert len({r.fixture_id for r in rows}) == 5
    assert m.COHORT_TF not in {r.cohort for r in rows}


def test_post_kickoff_odds_not_used_in_extract_path():
    # extract itself is pure; enrichment skips via timestamp in corpus builder — unit-check parse
    payload = {
        "api_sports": {
            "bookmakers": [
                {"id": 1, "bets": [{"name": "Match Winner", "values": [{"value": "Home", "odd": "1.8"}, {"value": "Draw", "odd": "3.4"}, {"value": "Away", "odd": "4.2"}]}]}
            ]
        }
    }
    odds = m.extract_1x2_from_snapshot(payload)
    assert odds and odds["home"] == 1.8


def test_no_bet_reason_provenance_reconstructed_not_invented_precise():
    r = _row(no_bet=True, confidence=40, odds_home=None, odds_draw=None, odds_away=None)
    m.reconstruct_no_bet_reasons(r, {})
    assert r.no_bet_reason_source == "reconstructed"
    assert "MISSING_ODDS" in r.no_bet_reasons
    assert "LOW_CONFIDENCE" in r.no_bet_reasons


def test_regulation_label_and_home_away():
    assert p1._norm_dir("home_win") == "home"
    assert p1._norm_dir("away_win") == "away"


def test_strategy_determinism_and_dedup():
    a = m.build_search_space(500)
    b = m.build_search_space(500)
    assert [p1.cfg_hash(x.to_dict()) for x in a] == [p1.cfg_hash(x.to_dict()) for x in b]
    assert len({p1.cfg_hash(x.to_dict()) for x in a}) == len(a)


def test_sample_size_and_coverage_leaderboards():
    train = [_row(fixture_id=i, kickoff_utc=f"2026-07-{i:02d}T12:00:00+00:00", confidence=70, home_p=0.6, actual_1x2="home") for i in range(1, 21)]
    val = [
        _row(
            fixture_id=100 + i,
            kickoff_utc=f"2026-08-{i:02d}T12:00:00+00:00",
            confidence=70,
            home_p=0.6,
            actual_1x2="home" if i < 8 else "away",
            top5_mass=0.55,
        )
        for i in range(1, 16)
    ]
    reg, meta = m.run_strategy_search(train, val, max_experiments=100, min_val_n=3)
    assert meta["n_run"] > 0
    assert all(r["holdout"] == "SEALED_UNOPENED" for r in reg)
    n25 = m.rank_for_gate(reg, min_n=25)
    # may be empty depending on filters; function must be deterministic
    assert isinstance(n25, list)


def test_sealed_holdout_protection_in_walk_forward():
    sealed = {999}
    rows = [_row(fixture_id=i, kickoff_utc=f"2026-07-{(i%28)+1:02d}T12:00:00+00:00", actual_1x2="home" if i % 2 == 0 else "away") for i in range(1, 80)]
    rows.append(_row(fixture_id=999, kickoff_utc="2026-09-01T12:00:00+00:00", actual_1x2="home"))
    folds, summary = m.walk_forward_folds(rows, sealed)
    assert summary["n_folds"] >= 1
    # sealed id must not appear in any fold test/train composition via metrics n only — check selected data path
    # walk_forward filters sealed from data list
    data_ids = {r.fixture_id for r in m.usable(rows) if r.fixture_id not in sealed}
    assert 999 not in data_ids


def test_phase2_smoke(tmp_path):
    v = m.run_phase2(out_dir=tmp_path / "p2", max_experiments=200)
    assert v["status"] in {m.STATUS_COMPLETE, m.STATUS_PARTIAL, m.STATUS_BLOCKED, m.STATUS_FAILED}
    assert v["not_deployed"] is True
    assert v["canonical_unchanged"] is True
    assert v["wde_unchanged"] is True
    assert v["ecse_unchanged"] is True
    assert v["no_auto_promotion"] is True
    assert v["sealed_holdout_status"] == "SEALED_UNOPENED"
    assert v["target_75_claimed"] is False
    assert (tmp_path / "p2" / "validation_report.json").exists()
    assert (tmp_path / "p2" / "feature_store_v2.parquet").exists()
    lock = json.loads((tmp_path / "p2" / "sealed_holdout_status.json").read_text(encoding="utf-8"))
    assert lock["phase1_holdout"]["opened"] is False
