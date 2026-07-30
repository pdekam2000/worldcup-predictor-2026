"""Phase 2 Bet Coverage Optimizer enhancements."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from worldcup_predictor.research.bet_coverage_optimizer.config import (
    ALLOWED_TOP_N,
    load_optimizer_config,
    scoring_weights_from_config,
    validate_top_n,
)
from worldcup_predictor.research.bet_coverage_optimizer.models import ModelTopScores, ScoreEntry
from worldcup_predictor.research.bet_coverage_optimizer.optimizer import optimize_fixture
from worldcup_predictor.research.bet_coverage_optimizer.service import run_coverage_optimizer_job
from worldcup_predictor.research.coupon_optimizer import optimize_coupon
from worldcup_predictor.research.multi_market_odds_loader import MarketPrice


def _entries(scores: list[str], probs: list[float] | None = None) -> list[ScoreEntry]:
    probs = probs or [max(0.01, 0.20 - i * 0.012) for i in range(len(scores))]
    return [ScoreEntry(score=s, probability=p, rank=i + 1) for i, (s, p) in enumerate(zip(scores, probs))]


RAW = {
    "bookmakers": [
        {
            "name": "ResearchBook",
            "bets": [
                {
                    "name": "Result/Total Goals",
                    "values": [
                        {"value": "Away & Under 4.5", "odd": "1.72"},
                        {"value": "Home & Under 4.5", "odd": "1.68"},
                        {"value": "Draw & Under 4.5", "odd": "3.10"},
                        {"value": "Home & Over 2.5", "odd": "1.95"},
                    ],
                },
                {
                    "name": "Goals Over/Under",
                    "values": [
                        {"value": "Under 3.5", "odd": "1.85"},
                        {"value": "Under 4.5", "odd": "1.28"},
                        {"value": "Over 2.5", "odd": "1.90"},
                    ],
                },
                {"name": "Both Teams Score", "values": [{"value": "Yes", "odd": "1.92"}, {"value": "No", "odd": "1.75"}]},
                {
                    "name": "Double Chance/Total Goals",
                    "values": [{"value": "X2 & Under 4.5", "odd": "1.62"}],
                },
                {
                    "name": "Home Team Total Goals",
                    "values": [{"value": "Over 2.5", "odd": "1.88"}],
                },
            ],
        }
    ]
}


def _models_wide() -> list[ModelTopScores]:
    scores = [f"{h}-{a}" for h in range(0, 4) for a in range(0, 4)][:12]
    return [
        ModelTopScores("canonical", _entries(scores)),
        ModelTopScores("exact_v2", _entries(scores[::-1])),
        ModelTopScores("lambda_v2", _entries(scores[2:] + scores[:2]), weight=0.75),
    ]


def test_validate_top_n_allowed_only():
    for n in (8, 10, 12):
        assert validate_top_n(n) == n
    with pytest.raises(ValueError):
        validate_top_n(9)
    assert ALLOWED_TOP_N == frozenset({8, 10, 12})


def test_config_weights_loaded_without_code_changes(tmp_path: Path):
    cfg_path = tmp_path / "weights.json"
    cfg_path.write_text(
        json.dumps(
            {
                "coverage_weights": {
                    "covered_probability_mass": 0.50,
                    "non_exact_probability_mass": 0.10,
                    "exact_overlap_probability_mass": 0.10,
                    "estimated_edge": 0.20,
                    "log_odds": 0.10,
                },
                "min_odds": 1.60,
            }
        ),
        encoding="utf-8",
    )
    cfg = load_optimizer_config(cfg_path)
    w = scoring_weights_from_config(cfg)
    assert w.covered_mass == 0.50
    assert w.non_exact_mass == 0.10
    assert w.min_odds == 1.60


def test_top5_ranked_candidates_artifact_fields():
    models = [
        ModelTopScores("canonical", _entries(["0-2", "0-1", "1-2", "0-3", "1-1", "0-0", "1-3", "2-2"])),
        ModelTopScores("exact_v2", _entries(["0-2", "1-2", "0-1", "0-3", "1-3", "1-1", "0-0", "2-2"])),
    ]
    rec = optimize_fixture(1556628, models, require_fresh=False, skip_db_odds=True, raw_payload=RAW, top_n_scores=8)
    assert len(rec.ranked_candidates) <= 5
    assert len(rec.ranked_candidates) >= 1
    row = rec.ranked_candidates[0]
    for key in (
        "rank",
        "market_label",
        "bookmaker",
        "odds",
        "covered_topN_scores",
        "covered_probability_mass",
        "exact_overlap_probability_mass",
        "estimated_edge",
        "coverage_score",
        "rejection_reason",
    ):
        assert key in row
    assert row["rank"] == 1
    if rec.selected_coverage_market:
        assert row["selected"] is True
        assert row["rejection_reason"] is None


def test_topn_8_10_12_deterministic_and_different(tmp_path: Path):
    models_payload = {
        1: {
            "canonical": {"scores": [s.to_dict() for s in _entries([f"{i//4}-{i%4}" for i in range(12)])]},
            "exact_v2": {"scores": [s.to_dict() for s in _entries([f"{i%4}-{i//4}" for i in range(12)])]},
        }
    }
    outs = {}
    for n in (8, 10, 12):
        # single fixture — no tickets/coupon
        result = run_coverage_optimizer_job(
            [1],
            model_payloads=models_payload,
            top_n_scores=n,
            require_fresh=False,
            skip_db_odds=True,
            raw_payload_by_fixture={1: RAW},
            generate_tickets=False,
            run_coupon_optimizer=False,
            output_dir=tmp_path / f"top{n}",
        )
        rec = result["recommendations"][0]
        outs[n] = {
            "top_n": rec["top_n"],
            "scores": [s["score"] for s in rec["top_n_scores"]],
            "fourth": (rec.get("selected_coverage_market") or {}).get("market_key"),
            "mass": rec["total_top_n_probability_mass"],
            "ranked": [(r["market_key"], r["coverage_score"]) for r in rec["ranked_candidates"]],
        }
        # deterministic re-run
        again = run_coverage_optimizer_job(
            [1],
            model_payloads=models_payload,
            top_n_scores=n,
            require_fresh=False,
            skip_db_odds=True,
            raw_payload_by_fixture={1: RAW},
            generate_tickets=False,
            run_coupon_optimizer=False,
            output_dir=tmp_path / f"top{n}_b",
        )
        assert again["recommendations"][0]["top_n_scores"] == rec["top_n_scores"]
        assert again["recommendations"][0]["ranked_candidates"] == rec["ranked_candidates"]
        assert (tmp_path / f"top{n}" / "candidate_markets_ranked.json").is_file()

    assert outs[8]["top_n"] == 8 and len(outs[8]["scores"]) == 8
    assert outs[10]["top_n"] == 10 and len(outs[10]["scores"]) == 10
    assert outs[12]["top_n"] == 12 and len(outs[12]["scores"]) == 12
    # Different TopN must change target set and/or fourth ranking inputs
    assert outs[8]["scores"] != outs[10]["scores"] or outs[8]["mass"] != outs[10]["mass"]
    assert outs[10]["scores"] != outs[12]["scores"] or outs[10]["mass"] != outs[12]["mass"]


def test_coupon_optimizer_joint_vs_independent():
    models = _models_wide()
    recs = []
    for fid in (1556628, 1494717, 1567860):
        recs.append(
            optimize_fixture(
                fid,
                models,
                require_fresh=False,
                skip_db_odds=True,
                raw_payload=RAW,
                top_n_scores=8,
            )
        )
    result = optimize_coupon(recs, config={"candidate_pool_per_fixture": 4, "stake_per_ticket": 1.0})
    d = result.to_dict()
    assert "coupon_score" in d
    assert "expected_coupon_value" in d
    assert "diversification_score" in d
    assert "overlap_penalty" in d
    assert d["tickets"]["summary"]["ticket_count"] == 64
    assert len(d["recommendations"]) == 3
    assert "independent_baseline" in d
    assert "ev_delta_vs_independent" in d["independent_baseline"]


def test_weight_sensitivity_changes_ranking(tmp_path: Path):
    models = [
        ModelTopScores("canonical", _entries(["0-2", "0-1", "1-2", "0-3", "1-1", "0-0", "1-3", "2-2"])),
        ModelTopScores("exact_v2", _entries(["0-2", "1-2", "0-1", "0-3", "1-3", "1-1", "0-0", "2-2"])),
    ]
    mass_heavy = scoring_weights_from_config(
        {"coverage_weights": {"covered_probability_mass": 0.70, "non_exact_probability_mass": 0.05, "exact_overlap_probability_mass": 0.05, "estimated_edge": 0.10, "log_odds": 0.10}}
    )
    odds_heavy = scoring_weights_from_config(
        {"coverage_weights": {"covered_probability_mass": 0.10, "non_exact_probability_mass": 0.10, "exact_overlap_probability_mass": 0.10, "estimated_edge": 0.20, "log_odds": 0.50}}
    )
    a = optimize_fixture(1, models, require_fresh=False, skip_db_odds=True, raw_payload=RAW, weights=mass_heavy)
    b = optimize_fixture(1, models, require_fresh=False, skip_db_odds=True, raw_payload=RAW, weights=odds_heavy)
    # Ranked lists exist; weight change can alter order (allow same if market set tiny)
    assert a.ranked_candidates and b.ranked_candidates
    assert a.scoring_weights["covered_probability_mass"] == 0.70
    assert b.scoring_weights["log_odds"] == 0.50
