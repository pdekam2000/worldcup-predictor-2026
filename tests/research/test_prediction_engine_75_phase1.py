"""Tests for Prediction Engine 75% Phase 1 foundation."""

from __future__ import annotations

from pathlib import Path

from worldcup_predictor.research.prediction_engine_75 import phase1 as m


def test_label_wording_downgrades_betting_language():
    assert m.LABEL_WORDING_MAP["BETTABLE_CANDIDATE"] == "MODEL_CANDIDATE"
    assert m.LABEL_WORDING_MAP["Approved Bet"] == "Research Candidate"
    assert "Strong Pick" in m.LABEL_WORDING_MAP


def test_chronological_split_and_holdout_seal():
    rows = [
        m.ResearchRow(
            fixture_id=i,
            kickoff_utc=f"2026-07-{i:02d}T12:00:00+00:00",
            frozen_at=f"2026-07-{i:02d}T08:00:00+00:00",
            generated_at=None,
            freeze_id=f"f{i}",
            freeze_hash=None,
            league="test",
            match=f"m{i}",
            wde_decision="home",
            ft_marginal="home",
            home_p=0.6,
            draw_p=0.2,
            away_p=0.2,
            confidence=60,
            top5_mass=0.5,
            top10_mass=0.8,
            entropy=1.5,
            lambda_home=1.2,
            lambda_away=0.8,
            odds_home=1.8,
            odds_draw=3.5,
            odds_away=4.5,
            actual_1x2="home" if i % 2 == 0 else "away",
            final_score="1-0",
        )
        for i in range(1, 21)
    ]
    sp = m.chronological_split(rows)
    assert len(sp["train"]) == 12
    assert len(sp["validation"]) == 4
    assert len(sp["holdout_sealed"]) == 4
    assert [r.fixture_id for r in sp["train"]] == list(range(1, 13))


def test_strategy_determinism_and_dedup():
    space = m.build_search_space()
    hashes = [m.cfg_hash(c.to_dict()) for c in space]
    assert len(hashes) == len(set(hashes))
    space2 = m.build_search_space()
    assert [m.cfg_hash(c.to_dict()) for c in space] == [m.cfg_hash(c.to_dict()) for c in space2]


def test_roi_and_drawdown_and_ci():
    rows = [
        m.ResearchRow(
            fixture_id=1,
            kickoff_utc="2026-07-01T12:00:00+00:00",
            frozen_at="2026-06-30T12:00:00+00:00",
            generated_at=None,
            freeze_id="a",
            freeze_hash=None,
            league="t",
            match="a",
            wde_decision="home",
            ft_marginal="home",
            home_p=0.7,
            draw_p=0.2,
            away_p=0.1,
            confidence=70,
            top5_mass=0.6,
            top10_mass=0.9,
            entropy=1.4,
            lambda_home=1.5,
            lambda_away=0.7,
            odds_home=2.0,
            odds_draw=3.4,
            odds_away=4.0,
            actual_1x2="home",
            final_score="2-0",
        )
    ]
    met = m.metrics([("home", rows[0])])
    assert met["roi"] == 1.0
    assert met["accuracy"] == 1.0
    lo, hi = m.wilson_ci(1, 1)
    assert lo is not None and hi is not None


def test_post_kickoff_excluded_from_usable():
    rows = [
        m.ResearchRow(
            fixture_id=1,
            kickoff_utc="2026-07-01T12:00:00+00:00",
            frozen_at="2026-07-01T13:00:00+00:00",
            generated_at=None,
            freeze_id="a",
            freeze_hash=None,
            league="t",
            match="a",
            wde_decision="home",
            ft_marginal="home",
            home_p=0.5,
            draw_p=0.3,
            away_p=0.2,
            confidence=60,
            top5_mass=0.5,
            top10_mass=0.8,
            entropy=1.5,
            lambda_home=1.0,
            lambda_away=1.0,
            odds_home=None,
            odds_draw=None,
            odds_away=None,
            actual_1x2="home",
            final_score="1-0",
            exclusion_reason="POST_KICKOFF_FREEZE",
        )
    ]
    assert m.usable_rows(rows) == []


def test_search_does_not_open_holdout(tmp_path):
    # tiny synthetic search
    train = [
        m.ResearchRow(
            fixture_id=i,
            kickoff_utc=f"2026-07-{i:02d}T12:00:00+00:00",
            frozen_at=f"2026-07-{i:02d}T08:00:00+00:00",
            generated_at=None,
            freeze_id=f"f{i}",
            freeze_hash=None,
            league="t",
            match=f"m{i}",
            wde_decision="home",
            ft_marginal="home",
            home_p=0.65,
            draw_p=0.2,
            away_p=0.15,
            confidence=62,
            top5_mass=0.6,
            top10_mass=0.85,
            entropy=1.5,
            lambda_home=1.3,
            lambda_away=0.8,
            odds_home=1.9,
            odds_draw=3.5,
            odds_away=4.2,
            actual_1x2="home",
            final_score="1-0",
        )
        for i in range(1, 16)
    ]
    val = [
        m.ResearchRow(
            fixture_id=100 + i,
            kickoff_utc=f"2026-08-{i:02d}T12:00:00+00:00",
            frozen_at=f"2026-08-{i:02d}T08:00:00+00:00",
            generated_at=None,
            freeze_id=f"v{i}",
            freeze_hash=None,
            league="t",
            match=f"v{i}",
            wde_decision="home",
            ft_marginal="home",
            home_p=0.6,
            draw_p=0.25,
            away_p=0.15,
            confidence=61,
            top5_mass=0.55,
            top10_mass=0.8,
            entropy=1.5,
            lambda_home=1.2,
            lambda_away=0.9,
            odds_home=2.0,
            odds_draw=3.3,
            odds_away=3.8,
            actual_1x2="home" if i < 8 else "away",
            final_score="1-0",
        )
        for i in range(1, 11)
    ]
    reg, meta = m.run_strategy_search(train, val, max_experiments=50, min_val_n=3)
    assert meta["n_run"] == 50
    assert all(r["holdout"] == "SEALED_UNOPENED" for r in reg)
    ranked = m.rank_validation_strategies(reg)
    assert ranked
    assert "holdout" not in ranked[0] or ranked[0]["holdout"] == "SEALED_UNOPENED"


def test_phase1_smoke(tmp_path):
    v = m.run_phase1(out_dir=tmp_path / "p75", max_experiments=200)
    assert v["status"] in {m.STATUS_READY, m.STATUS_BLOCKED}
    assert v["not_deployed"] is True
    assert v["canonical_unchanged"] is True
    assert v["wde_unchanged"] is True
    assert v["ecse_unchanged"] is True
    assert v["no_auto_promotion"] is True
    assert v["target_75_claimed"] is False
    assert v["sealed_holdout_status"] == "SEALED_UNOPENED"
    assert (tmp_path / "p75" / "validation_report.json").exists()
    assert (tmp_path / "p75" / "sealed_holdout_lock.json").exists()
    assert (tmp_path / "p75" / "experiment_registry.jsonl").exists()
    lock = __import__("json").loads((tmp_path / "p75" / "sealed_holdout_lock.json").read_text(encoding="utf-8"))
    assert lock["opened_for_strategy_selection"] is False
