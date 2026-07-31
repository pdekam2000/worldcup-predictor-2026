"""Phase 4 — forensic audit + historical replay + forward shadow tests."""

from __future__ import annotations

import json
from pathlib import Path

from worldcup_predictor.research.bet_coverage_optimizer.phase4.coverage_explanation import (
    explain_fixture_coverage,
)
from worldcup_predictor.research.bet_coverage_optimizer.phase4.forward_shadow import (
    evaluate_prediction_day,
    store_prediction_day,
    summarize_forward_shadow,
)
from worldcup_predictor.research.bet_coverage_optimizer.phase4.historical_replay import (
    build_deterministic_historical_fixtures,
    run_historical_replay,
)
from worldcup_predictor.research.bet_coverage_optimizer.phase4.pipeline import run_phase4
from worldcup_predictor.research.bet_coverage_optimizer.phase4.real_market_validation import (
    validate_real_markets,
)
from worldcup_predictor.research.bet_coverage_optimizer.phase4.ticket_audit import build_ticket_audit
from worldcup_predictor.research.bet_coverage_optimizer.insurance.uncovered_mass import compute_uncovered_mass
from worldcup_predictor.research.bet_coverage_optimizer.models import (
    CoverageMarketEvaluation,
    CoverageRecommendation,
    ScoreEntry,
)


ODDS_JSON = (
    Path(__file__).resolve().parents[3]
    / "worldcup_predictor"
    / "research"
    / "bet_coverage_optimizer"
    / "fixtures"
    / "interwetten_three_fixture_markets.json"
)


def _sample_rec(fid: int = 1556628) -> CoverageRecommendation:
    exacts = [
        ScoreEntry(score="0-1", probability=0.19, rank=1),
        ScoreEntry(score="0-2", probability=0.16, rank=2),
        ScoreEntry(score="1-2", probability=0.10, rank=3),
    ]
    # attach weighted_probability for audit
    for e in exacts:
        e.weighted_probability = e.probability  # type: ignore[attr-defined]
    top = [
        ScoreEntry(score="0-1", probability=0.19, rank=1),
        ScoreEntry(score="0-2", probability=0.16, rank=2),
        ScoreEntry(score="1-2", probability=0.10, rank=3),
        ScoreEntry(score="0-0", probability=0.11, rank=4),
        ScoreEntry(score="0-3", probability=0.09, rank=5),
        ScoreEntry(score="1-1", probability=0.09, rank=6),
        ScoreEntry(score="1-3", probability=0.07, rank=7),
        ScoreEntry(score="2-2", probability=0.04, rank=8),
    ]
    cov = CoverageMarketEvaluation(
        fixture_id=fid,
        bookmaker="Interwetten",
        provider="manual_screenshot_transcription",
        market_key="btts|side=yes",
        market_label="BTTS Yes",
        market_type="btts",
        market_parameters={"side": "yes"},
        odds=2.10,
        odds_timestamp="2026-07-30T20:00:00Z",
        odds_age_seconds=1.0,
        odds_freshness_status="FRESH_ODDS",
        target_scores=[s.score for s in top],
        covered_scores=["1-2", "1-1", "1-3", "2-2"],
        covered_probability_mass=0.3,
        exact_overlap_scores=["1-2"],
        non_exact_covered_scores=["1-1", "1-3", "2-2"],
        exact_overlap_probability_mass=0.1,
        non_exact_coverage_probability_mass=0.2,
        estimated_model_probability=0.3,
        implied_probability=1 / 2.10,
        estimated_edge=0.01,
        coverage_score=0.5,
        eligible=True,
    )
    from worldcup_predictor.research.bet_coverage_optimizer.models import ExactSelection

    exact_sels = [
        ExactSelection(
            score=s.score,
            consensus_count=2,
            weighted_probability=float(s.probability),
            canonical_rank=s.rank,
            exact_v2_rank=s.rank,
            selection_id=f"exact:{s.score}",
            label=f"Exact {s.score}",
            odds=None,
            odds_freshness_status=None,
        )
        for s in exacts
    ]
    return CoverageRecommendation(
        fixture_id=fid,
        model_snapshot_hash="test",
        selected_exact_scores=exact_sels,
        selected_coverage_market=cov,
        top_n_scores_list=top,
        total_top_n_probability_mass=sum(s.probability for s in top),
        covered_top_n_scores=["0-1", "0-2", "1-2", "1-1", "1-3", "2-2"],
        uncovered_top_n_scores=["0-0", "0-3"],
        generated_at="2026-07-31T00:00:00+00:00",
        top_n=8,
        ranked_candidates=[],
        scoring_weights={},
        research_only=True,
        owner_only=True,
        status="OK",
        blockers=[],
    )


def test_historical_replay_reduces_complete_failure():
    fixtures = build_deterministic_historical_fixtures(120)
    result = run_historical_replay(fixtures, min_fixtures=100)
    assert result["enough_historical_data"] is True
    assert result["no_future_leakage"] is True
    cf = result["complete_coupon_failure"]
    assert cf["insurance_reduces_complete_failure"] is True
    assert cf["main_plus_insurance_all_ticket_loss_frequency"] < cf["main_only_all_ticket_loss_frequency"]
    assert result["strategies"]["exact3_main_insurance"]["coverage_rate"] >= result["strategies"]["exact3_main"]["coverage_rate"]


def test_coverage_explanation_lists_scorelines():
    rec = _sample_rec()
    unc = compute_uncovered_mass(rec)
    expl = explain_fixture_coverage(rec, uncovered=unc, insurance=None, fixture_name="Test")
    assert "0-1" in expl["scoreline_narrative"]["Primary"]
    assert isinstance(expl["residual_uncovered_scores"], list)
    assert "coverage_increase" in expl


def test_ticket_audit_fields():
    rec = _sample_rec()
    main = {
        "summary": {"stake_per_ticket": 1.0},
        "tickets": [
            {
                "ticket_number": 1,
                "combined_odds": None,
                "selections": [
                    {
                        "fixture_id": rec.fixture_id,
                        "selection_id": "exact:0-1",
                        "label": "Exact 0-1",
                        "kind": "exact_score",
                        "score": "0-1",
                        "odds": None,
                    },
                    {
                        "fixture_id": rec.fixture_id,
                        "selection_id": "exact:0-2",
                        "label": "Exact 0-2",
                        "kind": "exact_score",
                        "score": "0-2",
                        "odds": None,
                    },
                    {
                        "fixture_id": rec.fixture_id,
                        "selection_id": "coverage:btts",
                        "label": "BTTS Yes",
                        "kind": "coverage",
                        "odds": 2.1,
                    },
                ],
            }
        ],
    }
    # Need 3 fixtures for real tickets; pad with same rec ids artificially for field presence
    recs = [
        _sample_rec(1556628),
        _sample_rec(1494717),
        _sample_rec(1567860),
    ]
    main["tickets"][0]["selections"] = [
        {
            "fixture_id": 1556628,
            "selection_id": "exact:0-1",
            "label": "Exact 0-1",
            "kind": "exact_score",
            "score": "0-1",
            "odds": None,
        },
        {
            "fixture_id": 1494717,
            "selection_id": "exact:2-0",
            "label": "Exact 2-0",
            "kind": "exact_score",
            "score": "2-0",
            "odds": None,
        },
        {
            "fixture_id": 1567860,
            "selection_id": "coverage:x",
            "label": "DC",
            "kind": "coverage",
            "odds": 1.62,
        },
    ]
    # Fix exact scores on other recs so model probs resolve
    from worldcup_predictor.research.bet_coverage_optimizer.models import ExactSelection

    recs[1].selected_exact_scores = [
        ExactSelection("2-0", 2, 0.2, 1, 1, "exact:2-0", "Exact 2-0"),
        ExactSelection("3-0", 2, 0.15, 2, 2, "exact:3-0", "Exact 3-0"),
        ExactSelection("1-0", 1, 0.1, 3, 3, "exact:1-0", "Exact 1-0"),
    ]
    audit = build_ticket_audit(
        main_payload=main,
        insurance_tickets=[],
        recommendations=recs,
        fixture_names={1556628: "A", 1494717: "B", 1567860: "C"},
        budget={"stake_per_main_ticket_eur": 5.0},
    )
    row = audit["tickets"][0]
    for key in (
        "ticket_id",
        "selections",
        "fixture_ids",
        "fixture_names",
        "bookmaker_odds",
        "combined_odds",
        "model_probability",
        "probability_mass_utility",
        "reason_for_inclusion",
        "coupon_score",
        "insurance_usage",
        "ranking",
    ):
        assert key in row


def test_real_market_validation_flags_researchbook():
    rec = _sample_rec()
    rec.selected_coverage_market.provider = "ResearchBook"
    rec.selected_coverage_market.bookmaker = "ResearchBook"
    out = validate_real_markets([rec], ranked_by={rec.fixture_id: []}, real_odds_report={"fixtures": {}})
    assert out["summary"]["n_synthetic"] >= 1
    assert out["summary"]["priced_coverage_and_insurance_all_real"] is False


def test_forward_shadow_db(tmp_path: Path):
    db = tmp_path / "forward_shadow.db"
    day = store_prediction_day(
        db,
        prediction_date="2026-07-31",
        main_tickets=[{"ticket_id": "MAIN-001", "x": 1}],
        insurance_tickets=[{"ticket_id": "INS-001", "x": 2}],
        coverage_report={"ok": True},
        budget={"total_budget_eur": 400},
    )
    evaluate_prediction_day(
        db,
        day_id=day,
        main_only_result={"roi": -0.1},
        main_plus_insurance_result={"roi": -0.05},
        insurance_hit_rate=0.2,
        coverage_gain=0.05,
        daily_roi=-0.05,
    )
    summary = summarize_forward_shadow(db)
    assert summary["forward_shadow_ready"] is True
    assert summary["n_prediction_days"] == 1
    assert summary["n_evaluations"] == 1
    assert summary["ticket_counts_by_layer"]["main"] == 1


def test_phase4_pipeline_end_to_end(tmp_path: Path):
    assert ODDS_JSON.is_file()
    result = run_phase4(
        top_n=8,
        real_odds_json=ODDS_JSON,
        total_budget=400.0,
        main_budget_ratio=0.8,
        max_insurance_tickets=15,
        stake_mode="score_weighted",
        output_dir=tmp_path / "phase4",
        historical_n=120,
    )
    assert result["status"] == "BET_COVERAGE_OPTIMIZER_PHASE4_FORWARD_SHADOW_READY"
    out = Path(result["output_dir"])
    for name in (
        "ticket_audit.json",
        "ticket_audit.csv",
        "insurance_validation.json",
        "real_market_validation.json",
        "historical_replay.json",
        "historical_replay.md",
        "forward_shadow.db",
        "forward_shadow_summary.json",
        "owner_phase4_report.html",
        "owner_phase4_report.md",
        "final_recommendations.json",
        "validation_report.json",
    ):
        assert (out / name).exists(), name
    sc = result["validation"]["success_criteria"]
    assert sc["insurance_reduces_complete_failure"] is True
    assert sc["no_synthetic_priced_markets"] is True
    assert sc["priced_markets_real"] is True
    assert sc["no_production_deploy"] is True
    audit = json.loads((out / "ticket_audit.json").read_text(encoding="utf-8"))
    assert audit["n_main_tickets"] == 64
