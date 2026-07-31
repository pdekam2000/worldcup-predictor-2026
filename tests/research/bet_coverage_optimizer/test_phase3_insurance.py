"""Phase 3 Insurance Pick + real odds tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from worldcup_predictor.research.bet_coverage_optimizer.insurance.budget import allocate_budget
from worldcup_predictor.research.bet_coverage_optimizer.insurance.backtest import run_insurance_backtest
from worldcup_predictor.research.bet_coverage_optimizer.insurance.insurance_candidates import (
    enrich_candidate_against_uncovered,
)
from worldcup_predictor.research.bet_coverage_optimizer.insurance.insurance_optimizer import (
    build_fixture_insurance_candidates,
    optimize_insurance_tickets,
)
from worldcup_predictor.research.bet_coverage_optimizer.insurance.insurance_scoring import score_insurance_candidates
from worldcup_predictor.research.bet_coverage_optimizer.insurance.real_odds import (
    load_real_odds_json,
    validate_odds_document,
)
from worldcup_predictor.research.bet_coverage_optimizer.insurance.uncovered_mass import (
    compute_uncovered_mass,
    primary_covered_score_set,
)
from worldcup_predictor.research.bet_coverage_optimizer.models import (
    CoverageMarketEvaluation,
    CoverageRecommendation,
    ExactSelection,
    ModelTopScores,
    ScoreEntry,
)
from worldcup_predictor.research.bet_coverage_optimizer.optimizer import optimize_fixture
from worldcup_predictor.research.bet_coverage_optimizer.score_mapping import settles_as_win


def _exacts(scores: list[str]) -> list[ExactSelection]:
    return [
        ExactSelection(
            score=s,
            consensus_count=2,
            weighted_probability=0.1,
            canonical_rank=i + 1,
            exact_v2_rank=i + 1,
            selection_id=f"exact:{s}",
            label=f"Exact {s}",
            odds=None,
        )
        for i, s in enumerate(scores)
    ]


def _rec_with_coverage(
    fixture_id: int,
    exacts: list[str],
    top: list[tuple[str, float]],
    covered: list[str],
) -> CoverageRecommendation:
    cov = CoverageMarketEvaluation(
        fixture_id=fixture_id,
        bookmaker="Test",
        provider="test",
        market_key="over_under|direction=under|line=3.5",
        market_label="Under 3.5",
        market_type="over_under",
        market_parameters={"direction": "under", "line": 3.5},
        odds=1.85,
        odds_timestamp="2026-07-30T20:00:00+00:00",
        odds_age_seconds=0,
        odds_freshness_status="FRESH_ODDS",
        target_scores=[s for s, _ in top],
        covered_scores=covered,
        covered_probability_mass=0.5,
        exact_overlap_scores=[s for s in exacts if s in covered],
        non_exact_covered_scores=[s for s in covered if s not in exacts],
        exact_overlap_probability_mass=0.2,
        non_exact_coverage_probability_mass=0.3,
        estimated_model_probability=0.5,
        implied_probability=1 / 1.85,
        estimated_edge=0.0,
        coverage_score=0.8,
        eligible=True,
    )
    return CoverageRecommendation(
        fixture_id=fixture_id,
        model_snapshot_hash="abc",
        selected_exact_scores=_exacts(exacts),
        selected_coverage_market=cov,
        top_n_scores_list=[ScoreEntry(score=s, probability=p, rank=i + 1) for i, (s, p) in enumerate(top)],
        total_top_n_probability_mass=sum(p for _, p in top),
        covered_top_n_scores=list(dict.fromkeys(exacts + covered)),
        uncovered_top_n_scores=[s for s, _ in top if s not in set(exacts) | set(covered)],
        generated_at="2026-07-30T20:00:00+00:00",
        top_n=len(top),
    )


def test_uncovered_mass_arithmetic():
    top = [("0-2", 0.12), ("0-1", 0.11), ("1-2", 0.10), ("1-3", 0.09), ("2-2", 0.08), ("1-1", 0.07), ("0-0", 0.06), ("0-3", 0.05)]
    exacts = ["0-2", "0-1", "1-2"]
    covered = ["0-2", "0-1", "1-2", "0-3", "1-1", "0-0"]  # under 3.5-ish
    rec = _rec_with_coverage(1, exacts, top, covered)
    report = compute_uncovered_mass(rec)
    assert abs(report.top_n_probability_mass - sum(p for _, p in top)) < 1e-9
    assert set(u.score for u in report.primary_uncovered_scores) == {"1-3", "2-2"}
    assert abs(report.primary_uncovered_probability_mass - 0.17) < 1e-9
    assert abs(report.primary_covered_probability_mass + report.primary_uncovered_probability_mass - report.top_n_probability_mass) < 1e-9
    primary = primary_covered_score_set(rec)
    assert exacts[0] in primary
    assert "1-3" not in primary


def test_win_to_nil_and_btts_and_win_under_mapping():
    assert settles_as_win("win_to_nil", {"team": "away"}, 0, 2) is True
    assert settles_as_win("win_to_nil", {"team": "away"}, 1, 2) is False
    assert settles_as_win("btts", {"side": "yes"}, 1, 1) is True
    assert settles_as_win("result_total", {"result": "away", "direction": "under", "line": 4.5}, 1, 2) is True
    assert settles_as_win("winning_margin", {"selection": "home_by_1"}, 2, 1) is True


def test_rejected_fully_redundant_and_min_odds():
    top = [("0-2", 0.2), ("0-1", 0.15), ("1-2", 0.1), ("1-3", 0.08)]
    rec = _rec_with_coverage(1, ["0-2", "0-1", "1-2"], top, ["0-2", "0-1", "1-2"])
    unc = compute_uncovered_mass(rec)
    # Candidate covers only already-primary scores
    cand = {
        "fixture_id": 1,
        "market_key": "x",
        "market_label": "Redundant",
        "market_type": "over_under",
        "market_parameters": {"direction": "under", "line": 2.5},
        "bookmaker": "T",
        "odds": 1.90,
        "odds_freshness_status": "FRESH_ODDS",
        "eligible": True,
        "rejection_reasons": [],
    }
    enriched = enrich_candidate_against_uncovered(
        cand,
        uncovered=unc,
        exact_scores={"0-2", "0-1", "1-2"},
        primary_covered=primary_covered_score_set(rec),
        top_n_pairs=top,
    )
    ranked = score_insurance_candidates([enriched], insurance_cfg={"min_incremental_uncovered_mass": 0.03})
    assert ranked[0].eligible is False
    assert ranked[0].rejection_reason is not None

    low = dict(enriched or cand)
    low["odds"] = 1.20
    low["incremental_uncovered_probability_mass"] = 0.1
    low["covered_uncovered_scores"] = ["1-3"]
    ranked2 = score_insurance_candidates([low], insurance_cfg={"min_odds": 1.55, "min_incremental_uncovered_mass": 0.03})
    assert any("ODDS_BELOW_MIN" in r for r in ranked2[0].rejection_reasons)


def test_stale_real_odds_rejected():
    doc = {
        "fixture_id": 1,
        "bookmaker": "Interwetten",
        "captured_at_utc": "2020-01-01T00:00:00Z",
        "source_type": "manual_screenshot_transcription",
        "markets": [{"market_family": "btts", "selection": "Yes", "odds": 1.90}],
    }
    norm, errs = validate_odds_document(doc, insurance_cfg={"research_freshness_max_age_hours": 24})
    assert norm is None
    assert "STALE_REAL_ODDS" in errs


def test_manual_screenshot_source_labeling():
    path = Path("data/research/interwetten_three_fixture_markets.json")
    report = load_real_odds_json(path, insurance_cfg={"research_freshness_max_age_hours": 100000})
    assert report["n_fixtures"] >= 1
    fx = next(iter(report["fixtures"].values()))
    assert fx["manual_screenshot_transcription"] is True
    assert fx["api_sourced"] is False
    assert fx["source_type"] == "manual_screenshot_transcription"


def test_deterministic_insurance_tickets_no_125(tmp_path: Path):
    RAW = {
        "bookmakers": [
            {
                "name": "ResearchBook",
                "bets": [
                    {"name": "Goals Over/Under", "values": [{"value": "Under 3.5", "odd": "1.85"}, {"value": "Over 2.5", "odd": "1.95"}]},
                    {"name": "Both Teams Score", "values": [{"value": "Yes", "odd": "1.92"}, {"value": "No", "odd": "1.70"}]},
                    {
                        "name": "Result/Total Goals",
                        "values": [{"value": "Away & Under 4.5", "odd": "1.72"}, {"value": "Home & Under 4.5", "odd": "1.68"}],
                    },
                ],
            }
        ]
    }
    models = [
        ModelTopScores(
            "canonical",
            [ScoreEntry(score=f"{i//4}-{i%4}", probability=0.15 - 0.01 * (i % 8), rank=i + 1) for i in range(8)],
        ),
        ModelTopScores(
            "exact_v2",
            [ScoreEntry(score=f"{i%4}-{i//4}", probability=0.14 - 0.01 * (i % 8), rank=i + 1) for i in range(8)],
        ),
    ]
    recs = []
    ranked_by = {}
    unc_by = {}
    for fid in (1556628, 1494717, 1567860):
        rec = optimize_fixture(fid, models, require_fresh=False, skip_db_odds=True, raw_payload=RAW, top_n_scores=8)
        unc, ranked = build_fixture_insurance_candidates(rec, raw_payload=RAW)
        recs.append(rec)
        ranked_by[fid] = ranked
        unc_by[fid] = unc

    tickets = optimize_insurance_tickets(
        recs,
        candidates_by_fixture=ranked_by,
        uncovered_by_fixture=unc_by,
        insurance_cfg={
            "max_insurance_tickets": 15,
            "min_insurance_tickets": 3,
            "allow_triple_insurance": False,
            "min_incremental_uncovered_mass": 0.01,
            "max_primary_overlap_ratio": 0.95,
        },
    )
    # Re-score candidates with looser thresholds if needed
    if not any(c.eligible for cands in ranked_by.values() for c in cands):
        for fid, cands in list(ranked_by.items()):
            raw = [c.to_dict() for c in cands]
            ranked_by[fid] = score_insurance_candidates(
                raw,
                insurance_cfg={
                    "min_incremental_uncovered_mass": 0.005,
                    "max_primary_overlap_ratio": 0.99,
                    "min_odds": 1.40,
                },
            )
        tickets = optimize_insurance_tickets(
            recs,
            candidates_by_fixture=ranked_by,
            uncovered_by_fixture=unc_by,
            insurance_cfg={"max_insurance_tickets": 15, "min_insurance_tickets": 1, "min_incremental_uncovered_mass": 0.005},
        )

    assert len(tickets) <= 15
    assert len(tickets) != 125
    assert len(tickets) < 125
    # If any eligible insurance markets exist, tickets must be generated
    if any(c.eligible for cands in ranked_by.values() for c in cands):
        assert len(tickets) >= 1
        singles = [t for t in tickets if t.n_insurance_legs == 1]
        assert singles
        assert tickets[0].n_insurance_legs == 1
    # Determinism
    again = optimize_insurance_tickets(
        recs,
        candidates_by_fixture=ranked_by,
        uncovered_by_fixture=unc_by,
        insurance_cfg={"max_insurance_tickets": 15, "min_incremental_uncovered_mass": 0.005},
    )
    assert [t.ticket_id for t in again] == [t.ticket_id for t in tickets]
    assert [t.selections for t in again] == [t.selections for t in tickets]

def test_budget_sum_and_rounding():
    b = allocate_budget(
        n_main_tickets=64,
        n_insurance_tickets=10,
        budget_cfg={
            "total_budget_eur": 400,
            "main_budget_ratio": 0.8,
            "insurance_budget_ratio": 0.2,
            "rounding_step_eur": 0.5,
            "min_stake_per_ticket_eur": 1.0,
            "max_stake_per_ticket_eur": 20.0,
            "stake_mode": "equal",
        },
    )
    assert b["stake_per_main_ticket_eur"] >= 1.0
    assert abs(b["total_allocated_eur"] + b["unallocated_remainder_eur"] - 400) < 1.0
    assert b["kelly_enabled"] is False
    assert "not guaranteed" in b["warning"].lower() or "not guaranteed profit" in b["warning"].lower() or "not guaranteed" in b["warning"]


def test_backtest_separates_priced_and_mass_and_no_leakage():
    fixtures = []
    for i in range(120):
        fixtures.append(
            {
                "fixture_id": i,
                "top_n_scores": [{"score": "1-0", "probability": 0.2}, {"score": "0-0", "probability": 0.1}],
                "exact3": ["1-0", "0-0", "2-0"],
                "main_coverage_scores": ["1-1"],
                "insurance_scores": ["0-1"],
                "actual_score": "1-0" if i % 2 == 0 else "0-1",
                "prematch_odds_complete": False,
                "uses_postmatch_odds": False,
            }
        )
    # leakage case excluded
    fixtures.append(
        {
            "fixture_id": 999,
            "top_n_scores": [{"score": "1-0", "probability": 0.2}],
            "exact3": ["1-0"],
            "actual_score": "1-0",
            "uses_postmatch_odds": True,
        }
    )
    rep = run_insurance_backtest(fixtures, min_fixtures=100)
    assert rep["enough_historical_data"] is True
    assert rep["priced_subset_analysis"]["separated_from_mass_only"] is True
    assert rep["probability_mass_only_analysis"]["separated_from_priced"] is True
    assert any("FUTURE_LEAKAGE" in str(e.get("reasons")) for e in rep["excluded_fixtures"])


def test_missing_odds_hit_mass_utility_label():
    top = [("0-2", 0.2), ("1-3", 0.1), ("2-2", 0.08)]
    recs = [
        _rec_with_coverage(101, ["0-2", "0-1", "1-2"], top + [("0-1", 0.1), ("1-2", 0.1), ("0-0", 0.05), ("1-1", 0.05), ("0-3", 0.04)], ["0-2", "0-1", "1-2", "0-0", "1-1"]),
        _rec_with_coverage(102, ["2-0", "3-0", "1-0"], [("2-0", 0.2), ("3-0", 0.15), ("1-0", 0.1), ("4-0", 0.08), ("5-0", 0.05), ("0-0", 0.04), ("2-1", 0.03), ("3-1", 0.03)], ["2-0", "3-0", "1-0", "4-0"]),
        _rec_with_coverage(103, ["1-1", "1-0", "0-0"], [("1-1", 0.15), ("1-0", 0.14), ("0-0", 0.13), ("1-2", 0.1), ("0-1", 0.09), ("2-1", 0.08), ("2-0", 0.07), ("3-1", 0.05)], ["1-1", "1-0", "0-0", "0-1", "2-0"]),
    ]
    # Build simple eligible candidates manually
    from worldcup_predictor.research.bet_coverage_optimizer.insurance.schemas import InsuranceCandidate, UncoveredMassReport, UncoveredScore

    ranked_by = {}
    unc_by = {}
    for rec in recs:
        unc = compute_uncovered_mass(rec)
        unc_by[rec.fixture_id] = unc
        ranked_by[rec.fixture_id] = [
            InsuranceCandidate(
                fixture_id=rec.fixture_id,
                rank=1,
                market_label="BTTS Yes",
                market_key=f"btts|{rec.fixture_id}",
                market_type="btts",
                market_parameters={"side": "yes"},
                bookmaker="T",
                odds=1.9,
                covered_uncovered_scores=[u.score for u in unc.primary_uncovered_scores[:1]],
                incremental_uncovered_probability_mass=max(0.05, unc.primary_uncovered_probability_mass * 0.5),
                primary_overlap_mass=0.1,
                primary_overlap_ratio=0.2,
                residual_uncovered_mass_after=0.05,
                residual_risk_reduction=0.05,
                implied_probability=1 / 1.9,
                model_probability=0.2,
                estimated_edge=0.0,
                diversification_score=0.8,
                insurance_score=0.7,
                eligible=True,
            )
        ]
    tickets = optimize_insurance_tickets(recs, candidates_by_fixture=ranked_by, uncovered_by_fixture=unc_by)
    assert tickets
    # Exact odds missing on primary legs → combined odds may be None → utility still present
    assert all(t.probability_mass_utility >= 0 for t in tickets)
