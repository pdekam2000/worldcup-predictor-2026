"""Unit tests for forward aligned fixture scan (research-only)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from worldcup_predictor.research.forward_aligned_scan.alignment import (
    alignment_score,
    classify_alignment,
)
from worldcup_predictor.research.forward_aligned_scan.constants import (
    TIER_A,
    TIER_B,
    TIER_REJECTED,
    TIER_S,
)
from worldcup_predictor.research.forward_aligned_scan.directions import derive_directions, ranks_from_ecse
from worldcup_predictor.research.forward_aligned_scan.discovery import parse_days, vienna_date_range
from worldcup_predictor.research.forward_aligned_scan.odds_prep import classify_timing
from worldcup_predictor.research.forward_aligned_scan.predict import _sort_key, select_outputs


TZ = ZoneInfo("Europe/Vienna")


def test_days_range_bounds():
    assert parse_days(3) == 3
    assert parse_days(6) == 6
    with pytest.raises(ValueError):
        parse_days(2)
    with pytest.raises(ValueError):
        parse_days(7)


def test_vienna_midnight_boundaries():
    rng = vienna_date_range(from_date="2026-07-21", days=6)
    assert rng["from_date"] == "2026-07-21"
    assert rng["to_date"] == "2026-07-26"
    assert len(rng["dates"]) == 6
    start = datetime.fromisoformat(rng["range_start_vienna"])
    end = datetime.fromisoformat(rng["range_end_exclusive_vienna"])
    assert start.hour == 0 and start.minute == 0
    assert end.date().isoformat() == "2026-07-27"
    assert (end - start).days == 6


def test_timing_classes():
    assert classify_timing(2.0) == "LATE"
    assert classify_timing(8.0) == "MID"
    assert classify_timing(18.0) == "MATCHDAY"
    assert classify_timing(48.0) == "EARLY"
    assert classify_timing(100.0) == "VERY_EARLY"
    assert classify_timing(-1.0) == "STARTED_OR_PAST"


def _ecse_from_scores(scores: list[str], probs: list[float] | None = None) -> dict:
    ecse = {"scores": scores}
    for i, sc in enumerate(scores[:5], start=1):
        p = None if not probs else probs[i - 1]
        ecse[f"top{i}"] = {"score": sc, "probability": p}
    return ecse


def test_ecse_direction_majority_and_tie():
    # votes: home 3, away 2
    d = derive_directions(
        wde={"decision": "home_win", "ft_marginal": "home_win"},
        ecse=_ecse_from_scores(["1-0", "2-0", "2-1", "0-1", "0-2"], [0.2, 0.15, 0.12, 0.1, 0.09]),
        odds_home=1.5,
        odds_draw=4.0,
        odds_away=6.0,
    )
    assert d["ecse_top1_direction"] == "home_win"
    assert d["ecse_top5_majority"] == "home_win"
    assert d["market_direction"] == "home_win"

    # tie votes 2-2-1 then mass decides; equal mass → tie
    tie = derive_directions(
        wde={"decision": "draw", "ft_marginal": "draw"},
        ecse=_ecse_from_scores(["1-0", "0-1", "2-0", "0-2", "1-1"], [0.1, 0.1, 0.1, 0.1, 0.1]),
        odds_home=2.5,
        odds_draw=3.2,
        odds_away=2.6,
    )
    # votes home=2 away=2 draw=1 → mass all 0.1 among leaders → ECSE_DIRECTION_TIE
    assert tie["ecse_top5_majority_label"] == "ECSE_DIRECTION_TIE"


def test_full_alignment_and_conflict_rejection():
    dirs = {
        "wde_decision": "home_win",
        "ft_marginal": "home_win",
        "ecse_top1_direction": "home_win",
        "ecse_top3_majority": "home_win",
        "ecse_top5_majority": "home_win",
        "market_direction": "home_win",
        "ecse_direction_tie": False,
        "ecse_top5_majority_label": "home_win",
    }
    s = classify_alignment(
        dirs=dirs,
        consensus="HIGH_AGREEMENT",
        no_bet=False,
        top5_mass=0.55,
        odds_ready=True,
    )
    assert s["alignment_tier"] == TIER_S

    conflict = classify_alignment(
        dirs={**dirs, "ecse_top5_majority": "away_win", "ecse_top5_majority_label": "away_win"},
        consensus="HIGH_CONFLICT",
        no_bet=False,
        top5_mass=0.55,
        odds_ready=True,
    )
    assert conflict["alignment_tier"] == TIER_REJECTED
    assert "WDE_ECSE_TOP5_MAJORITY_CONFLICT" in conflict["reject_reasons"]


def test_strong_alignment_no_bet_caution():
    dirs = {
        "wde_decision": "away_win",
        "ft_marginal": "away_win",
        "ecse_top1_direction": "away_win",
        "ecse_top3_majority": "draw",
        "ecse_top5_majority": "away_win",
        "market_direction": "away_win",
        "ecse_direction_tie": False,
        "ecse_top5_majority_label": "away_win",
    }
    # missing mass / no_bet true → not Tier S; should be Tier A with caution if HIGH_AGREEMENT
    a = classify_alignment(
        dirs=dirs,
        consensus="HIGH_AGREEMENT",
        no_bet=True,
        top5_mass=0.40,
        odds_ready=True,
    )
    assert a["alignment_tier"] == TIER_A
    assert a["caution"] is True


def test_directional_watchlist():
    dirs = {
        "wde_decision": "home_win",
        "ft_marginal": "draw",
        "ecse_top1_direction": "draw",
        "ecse_top3_majority": "draw",
        "ecse_top5_majority": "home_win",
        "market_direction": "away_win",
        "ecse_direction_tie": False,
        "ecse_top5_majority_label": "home_win",
    }
    b = classify_alignment(
        dirs=dirs,
        consensus="MIXED",
        no_bet=None,
        top5_mass=0.4,
        odds_ready=True,
    )
    assert b["alignment_tier"] == TIER_B


def test_score_calculation_bounds():
    dirs = {
        "wde_decision": "home_win",
        "ft_marginal": "home_win",
        "ecse_top1_direction": "home_win",
        "ecse_top3_majority": "home_win",
        "ecse_top5_majority": "home_win",
        "market_direction": "home_win",
    }
    sc = alignment_score(
        dirs=dirs,
        consensus="HIGH_AGREEMENT",
        no_bet=False,
        top5_mass=0.72,
        top5_stable=True,
    )
    assert 0 <= sc["alignment_score"] <= 100
    assert sc["alignment_score"] >= 80
    assert sc["research_only"] is True


def test_stable_sort_and_no_quota_fill():
    rows = []
    for i, tier in enumerate([TIER_B, TIER_S, TIER_A, TIER_S, TIER_S, TIER_S, TIER_A]):
        rows.append(
            {
                "fixture_id": 1000 + i,
                "alignment_tier": tier,
                "alignment_score": 50 + i,
                "directions": {"wde_decision": "home_win", "ecse_top5_majority": "home_win"},
                "prediction": {"ecse": {"top5_mass": 0.5 + i * 0.01, "top3_mass": 0.3, "entropy": 1.5}},
                "hours_to_kickoff": 20,
                "odds_prep": {"odds_age_hours": 1},
                "stability": "UNKNOWN_NO_PRIOR_SNAPSHOT",
            }
        )
    # add many rejected — must not fill quotas
    for i in range(20):
        rows.append(
            {
                "fixture_id": 2000 + i,
                "alignment_tier": TIER_REJECTED,
                "alignment_score": 99,
                "reject_reasons": ["WDE_ECSE_TOP5_MAJORITY_CONFLICT"],
                "directions": {},
                "prediction": {"ecse": {}},
            }
        )
    out = select_outputs(rows)
    assert len(out["tier_s"]) <= 3
    assert len(out["tier_a"]) <= 5
    assert len(out["tier_b"]) <= 10
    assert out["no_quota_fill"] is True
    # Tier S first
    assert all(r["alignment_tier"] == TIER_S for r in out["tier_s"])
    # sorting within tier by score desc
    scores = [r["alignment_score"] for r in out["tier_s"]]
    assert scores == sorted(scores, reverse=True)


def test_ranks_from_ecse_format():
    ranks = ranks_from_ecse(_ecse_from_scores(["2-1", "1-1", "1-0", "0-0", "2-0"]))
    assert len(ranks) == 5
    assert ranks[0]["score"] == "2-1"
    assert ranks[0]["direction"] == "home_win"


def test_freeze_script_requires_owner_approval(tmp_path, monkeypatch):
    import scripts.freeze_selected_aligned_fixtures as freeze_mod

    rc = freeze_mod.main(["--scan-id", "does_not_exist"])
    assert rc == 2


def test_top5_string_scores_enrich_from_top10():
    from worldcup_predictor.research.canonical_ephemeral.facade import _top5_from_ecse_prediction

    pred = {
        "top_5_scores": ["3-0", "4-0", "2-0", "5-0", "6-0"],
        "top_10_scorelines": [
            {"scoreline": "3-0", "probability": 0.157},
            {"scoreline": "4-0", "probability": 0.151},
            {"scoreline": "2-0", "probability": 0.123},
            {"scoreline": "5-0", "probability": 0.116},
            {"scoreline": "6-0", "probability": 0.075},
            {"scoreline": "1-0", "probability": 0.064},
        ],
    }
    rows = _top5_from_ecse_prediction(pred)
    assert len(rows) == 5
    assert rows[0]["score"] == "3-0"
    assert rows[0]["probability"] == 0.157
    assert all(r["probability"] is not None for r in rows)


def test_bodo_type_tier_s_with_persisted_mass():
    dirs = {
        "wde_decision": "home_win",
        "ft_marginal": "home_win",
        "ecse_top1_direction": "home_win",
        "ecse_top3_majority": "home_win",
        "ecse_top5_majority": "home_win",
        "market_direction": "home_win",
        "ecse_direction_tie": False,
        "ecse_top5_majority_label": "home_win",
    }
    # Without mass → not Tier S
    no_mass = classify_alignment(
        dirs=dirs, consensus="HIGH_AGREEMENT", no_bet=False, top5_mass=None, odds_ready=True
    )
    assert no_mass["alignment_tier"] == TIER_A
    assert "FAILED_TIER_S_TOP5_MASS_UNAVAILABLE" in (no_mass.get("tier_s_failure_reasons") or [])
    # With mass ≥0.52 → Tier S
    with_mass = classify_alignment(
        dirs=dirs, consensus="HIGH_AGREEMENT", no_bet=False, top5_mass=0.62, odds_ready=True
    )
    assert with_mass["alignment_tier"] == TIER_S


def test_fixture_id_parse_and_log_dirs(tmp_path):
    from worldcup_predictor.research.forward_aligned_scan.runner import (
        _ensure_log_dirs,
        _parse_fixture_ids,
    )

    assert _parse_fixture_ids("1,2, 3") == [1, 2, 3]
    _ensure_log_dirs(tmp_path)
    assert (tmp_path / "artifacts" / "research" / "forward_aligned_fixture_scan" / "logs").is_dir()


def test_compare_promoted_to_tier_s_mass_fix():
    from worldcup_predictor.research.forward_aligned_scan.compare import compare_fixture

    old = {
        "fixture_id": 1494611,
        "home_team": "Bodo/Glimt",
        "away_team": "Ham-Kam",
        "alignment_tier": TIER_A,
        "alignment_score": 85,
        "odds_prep": {"home": 1.12, "draw": 9.0, "away": 17.0, "bookmaker_count": 13},
        "directions": {
            "wde_decision": "home_win",
            "ft_marginal": "home_win",
            "market_direction": "home_win",
            "ecse_top1_direction": "home_win",
            "ecse_top3_majority": "home_win",
            "ecse_top5_majority": "home_win",
            "ranks": [{"rank": i, "score": s, "probability": None} for i, s in enumerate(["3-0", "4-0", "2-0", "5-0", "6-0"], 1)],
        },
        "prediction": {
            "consensus": "HIGH_AGREEMENT",
            "no_bet": False,
            "wde": {"decision": "home_win", "confidence": 76},
            "ecse": {"scores": ["3-0", "4-0", "2-0", "5-0", "6-0"], "top5_mass": None},
        },
    }
    new = {
        **old,
        "alignment_tier": TIER_S,
        "alignment_score": 93,
        "prediction": {
            **old["prediction"],
            "ecse": {
                "scores": ["3-0", "4-0", "2-0", "5-0", "6-0"],
                "top5_mass": 0.62,
                "top3_mass": 0.43,
                "entropy": 1.5,
                "top1_probability": 0.15,
                **{f"top{i}": {"score": s, "probability": 0.1} for i, s in enumerate(["3-0", "4-0", "2-0", "5-0", "6-0"], 1)},
            },
        },
    }
    out = compare_fixture(old, new)
    assert "PROMOTED_TO_TIER_S" in out["movement_labels"]
    assert "PROMOTED_TO_TIER_S_AFTER_PERSISTED_MASS_FIX" in out["movement_labels"]


def test_started_fixture_excluded_label():
    from worldcup_predictor.research.forward_aligned_scan.compare import compare_fixture
    from worldcup_predictor.research.forward_aligned_scan.odds_prep import classify_timing

    assert classify_timing(-0.1) == "STARTED_OR_PAST"
    out = compare_fixture(
        {"fixture_id": 1, "home_team": "A", "away_team": "B", "alignment_tier": TIER_A},
        {
            "fixture_id": 1,
            "home_team": "A",
            "away_team": "B",
            "alignment_tier": TIER_REJECTED,
            "reject_reasons": ["FIXTURE_STARTED_EXCLUDED"],
            "prediction_status": "FIXTURE_STARTED_EXCLUDED",
        },
    )
    assert "FIXTURE_STARTED_EXCLUDED" in out["movement_labels"]
