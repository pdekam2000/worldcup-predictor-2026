"""Phase 25 — promotion shadow replay and calibration evaluation (offline)."""

from __future__ import annotations

import json
import os
import statistics
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import runpy

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "PHASE_25_CALIBRATION_SHADOW_REPLAY_REPORT.md"
REPLAY_JSONL = ROOT / "data" / "shadow" / "phase25_promotion_replay.jsonl"
METRICS_JSON = ROOT / "data" / "shadow" / "phase25_promotion_metrics.json"

DEFAULT_FLAGS = {
    "EXPECTED_LINEUP_PROMOTION_MODE": "shadow",
    "TOURNAMENT_CONTEXT_PROMOTION_MODE": "shadow",
    "XG_PROMOTION_MODE": "shadow",
    "SPORTMONKS_PREDICTION_PROMOTION_MODE": "shadow",
}


@dataclass
class ReplayCase:
    fixture_id: int
    match_name: str
    actual_1x2: str
    actual_over_under: str
    source: str
    has_promotion_signals: bool
    baseline: Any
    report: Any
    specialist: Any


@dataclass
class ReplayRow:
    fixture_id: int
    match_name: str
    source: str
    stack: str
    mode: str
    actual_1x2: str
    predicted_1x2: str
    baseline_1x2: str
    correct: bool
    confidence: float
    baseline_confidence: float
    no_bet_flag: bool
    no_bet_review_trace: bool
    winner_flipped: bool
    combined_conf_delta: float
    lineup_delta: float
    context_delta: float
    xg_delta: float
    sportmonks_conf_delta: float
    disagreement_signal: str
    promotion_active_count: int
    gate_failures: list[str] = field(default_factory=list)


@dataclass
class StackMetrics:
    stack: str
    mode: str
    n: int = 0
    one_x_two_accuracy: float = 0.0
    avg_confidence: float = 0.0
    avg_confidence_correct: float = 0.0
    avg_confidence_wrong: float = 0.0
    brier_score: float | None = None
    overconfidence_rate: float = 0.0
    no_bet_review_rate: float = 0.0
    disagreement_rate: float = 0.0
    winner_flip_rate: float = 0.0
    avg_combined_conf_delta: float = 0.0
    avg_lineup_delta: float = 0.0
    avg_context_delta: float = 0.0
    avg_xg_delta: float = 0.0
    avg_sportmonks_conf_delta: float = 0.0
    promotion_coverage_rate: float = 0.0


def _reset_env(**overrides: str) -> None:
    for key, value in DEFAULT_FLAGS.items():
        os.environ[key] = value
    for key, value in overrides.items():
        os.environ[key] = value
    from worldcup_predictor.config.settings import get_settings

    get_settings.cache_clear()


def _verify_defaults_unchanged() -> bool:
    from worldcup_predictor.config.settings import get_settings

    get_settings.cache_clear()
    s = get_settings()
    return (
        s.expected_lineup_promotion_mode == "shadow"
        and s.tournament_context_promotion_mode == "shadow"
        and s.xg_promotion_mode == "shadow"
        and s.sportmonks_prediction_promotion_mode == "shadow"
    )


PROMOTION_STACKS: dict[str, dict[str, str]] = {
    "baseline": {
        "EXPECTED_LINEUP_PROMOTION_MODE": "off",
        "TOURNAMENT_CONTEXT_PROMOTION_MODE": "off",
        "XG_PROMOTION_MODE": "off",
        "SPORTMONKS_PREDICTION_PROMOTION_MODE": "off",
    },
    "shadow_default": dict(DEFAULT_FLAGS),
    "gated_simulation": {
        "EXPECTED_LINEUP_PROMOTION_MODE": "gated",
        "TOURNAMENT_CONTEXT_PROMOTION_MODE": "gated",
        "XG_PROMOTION_MODE": "gated",
        "SPORTMONKS_PREDICTION_PROMOTION_MODE": "gated",
    },
    "24a_only": {
        "EXPECTED_LINEUP_PROMOTION_MODE": "gated",
        "TOURNAMENT_CONTEXT_PROMOTION_MODE": "off",
        "XG_PROMOTION_MODE": "off",
        "SPORTMONKS_PREDICTION_PROMOTION_MODE": "off",
    },
    "24b_only": {
        "EXPECTED_LINEUP_PROMOTION_MODE": "off",
        "TOURNAMENT_CONTEXT_PROMOTION_MODE": "gated",
        "XG_PROMOTION_MODE": "off",
        "SPORTMONKS_PREDICTION_PROMOTION_MODE": "off",
    },
    "24c_xg_only": {
        "EXPECTED_LINEUP_PROMOTION_MODE": "off",
        "TOURNAMENT_CONTEXT_PROMOTION_MODE": "off",
        "XG_PROMOTION_MODE": "gated",
        "SPORTMONKS_PREDICTION_PROMOTION_MODE": "off",
    },
    "24c_sm_only": {
        "EXPECTED_LINEUP_PROMOTION_MODE": "off",
        "TOURNAMENT_CONTEXT_PROMOTION_MODE": "off",
        "XG_PROMOTION_MODE": "off",
        "SPORTMONKS_PREDICTION_PROMOTION_MODE": "gated",
    },
    "24a_24b": {
        "EXPECTED_LINEUP_PROMOTION_MODE": "gated",
        "TOURNAMENT_CONTEXT_PROMOTION_MODE": "gated",
        "XG_PROMOTION_MODE": "off",
        "SPORTMONKS_PREDICTION_PROMOTION_MODE": "off",
    },
    "24a_24b_24c": {
        "EXPECTED_LINEUP_PROMOTION_MODE": "gated",
        "TOURNAMENT_CONTEXT_PROMOTION_MODE": "gated",
        "XG_PROMOTION_MODE": "gated",
        "SPORTMONKS_PREDICTION_PROMOTION_MODE": "gated",
    },
}


def _make_baseline_from_history(record: Any) -> Any:
    from worldcup_predictor.domain.prediction import (
        ConfidenceLevel,
        FirstGoalPrediction,
        HalftimePrediction,
        MarketPrediction,
        MatchPrediction,
        PredictionConfidenceBreakdown,
    )

    conf = float(record.confidence_score)
    level = ConfidenceLevel.MEDIUM
    if conf >= 70:
        level = ConfidenceLevel.HIGH
    elif conf < 45:
        level = ConfidenceLevel.LOW
    prob_map = {"home_win": 0.45, "away_win": 0.40, "draw": 0.33}
    return MatchPrediction(
        fixture_id=int(record.fixture_id),
        competition_key="world_cup_2026",
        match_name=f"{record.home_team} vs {record.away_team}",
        one_x_two=MarketPrediction(
            market="1x2",
            selection=record.predicted_1x2,
            probability=prob_map.get(record.predicted_1x2, 0.40),
        ),
        over_under=MarketPrediction(
            market="over_under_2_5",
            selection=record.predicted_over_under_2_5,
            probability=0.52,
        ),
        halftime=HalftimePrediction(estimated_total_goals=float(record.predicted_halftime_goals)),
        first_goal=FirstGoalPrediction(team=record.predicted_first_goal_team),
        confidence_score=conf,
        confidence_level=level,
        confidence_breakdown=PredictionConfidenceBreakdown(
            form_score=60.0,
            h2h_score=50.0,
            injuries_score=55.0,
            lineups_score=50.0,
            odds_score=50.0,
            data_quality_score=float(record.data_quality_score),
            total=conf,
        ),
        risk_level=str(record.risk_level),
        no_bet_flag=bool(record.no_bet_flag),
    )


def _make_report_from_result(result: dict[str, Any]) -> Any:
    from worldcup_predictor.domain.fixture import Fixture
    from worldcup_predictor.domain.intelligence import (
        DataQualityReport,
        InjuryReport,
        MatchIntelligenceReport,
        TeamIntelligence,
    )

    kickoff_raw = result.get("kickoff_utc") or "2026-06-15T19:00:00"
    kickoff = datetime.fromisoformat(str(kickoff_raw).replace("Z", "")[:19])
    fixture = Fixture(
        id=int(result["fixture_id"]),
        competition_key="world_cup_2026",
        home_team=str(result["home_team"]),
        away_team=str(result["away_team"]),
        home_team_id=1,
        away_team_id=2,
        kickoff_utc=kickoff,
        venue=str(result.get("venue") or "WC Stadium"),
        stage="Group Stage",
        league_id=1,
        season=2026,
        status="FT",
    )
    return MatchIntelligenceReport(
        fixture_id=int(result["fixture_id"]),
        fixture=fixture,
        home_team=TeamIntelligence(team_name=str(result["home_team"]), team_id=1),
        away_team=TeamIntelligence(team_name=str(result["away_team"]), team_id=2),
        is_placeholder=False,
        data_quality=DataQualityReport(
            score=0.70,
            available_fields=["home_form", "away_form", "odds"],
            missing_fields=["lineups"],
            errors=[],
        ),
        missing_data=["lineups"],
    )


def _synthetic_promotion_signals(fixture_id: int, variant: str) -> Any:
    from worldcup_predictor.agents.specialists.helpers import make_signal
    from worldcup_predictor.domain.specialist import MatchSpecialistReport

    signals: dict[str, Any] = {}
    if variant in ("full", "24a", "combo"):
        signals["lineup_intelligence_agent"] = make_signal(
            "lineup_intelligence_agent",
            "lineup_intelligence_v2",
            "partial",
            {
                "home": {"lineup_strength": 48.0, "official_lineup": False, "risk_flags": []},
                "away": {"lineup_strength": 44.0, "official_lineup": False, "risk_flags": []},
                "prediction_impact": {"home_adjustment": 0, "away_adjustment": 0, "over25_adjustment": 0},
            },
        )
        signals["expected_lineup_agent"] = make_signal(
            "expected_lineup_agent",
            "expected_lineup_intelligence",
            "available",
            {
                "lineup_confidence": 58.0,
                "expected_xi_quality": 72.0,
                "lineup_supports_internal": True,
                "late_news_risk": "medium",
                "data_sources": ["lineups_api_football"],
                "comparison_available": False,
                "confirmed_available": False,
            },
        )
    if variant in ("full", "24b", "combo"):
        signals["motivation_psychology_agent"] = make_signal(
            "motivation_psychology_agent",
            "motivation_psychology",
            "available",
            {
                "motivation_score_home": 72.0,
                "motivation_score_away": 58.0,
                "home_qualification_status": "must_win",
                "away_qualification_status": "goal_difference_critical",
            },
        )
        signals["tournament_intelligence_agent"] = make_signal(
            "tournament_intelligence_agent",
            "tournament_intelligence",
            "available",
            {"pressure_score": 58.0, "prediction_impact": {"home_adjustment": 4.0, "away_adjustment": -2.0}, "risk_flags": []},
        )
        signals["tournament_context_agent"] = make_signal(
            "tournament_context_agent",
            "tournament_context",
            "available",
            {
                "motivation_score_home": 74.0,
                "motivation_score_away": 56.0,
                "qualification_status_home": "must_win",
                "qualification_status_away": "goal_difference_critical",
                "must_win_flag": True,
                "rotation_risk": "High",
                "draw_acceptability": False,
                "expected_aggression": "high",
                "expected_conservatism": "balanced",
                "tournament_importance": "high",
                "group_context_strength": 54.0,
                "context_supports_internal": True,
                "disagreement_score": 0.12,
                "match_context": "Group Stage — Matchday 3",
                "data_sources": ["api_football_standings", "schedule_context"],
            },
        )
    if variant in ("full", "24c", "combo"):
        signals["tactics_agent"] = make_signal(
            "tactics_agent",
            "tactics",
            "available",
            {
                "xg_attack_strength_home": 58.0,
                "xg_attack_strength_away": 52.0,
                "over_under_tendency": "over_lean",
                "expected_goal_pressure": 2.9,
            },
        )
        signals["xg_chance_quality_intelligence_agent"] = make_signal(
            "xg_chance_quality_intelligence_agent",
            "xg_chance_quality_v2",
            "available",
            {"goals_pressure_score": 62.0, "prediction_impact": {"over25_adjustment": 4.0}, "risk_flags": []},
        )
        signals["xg_intelligence_agent"] = make_signal(
            "xg_intelligence_agent",
            "sportmonks_xg_intelligence",
            "available",
            {
                "home_xg": 1.65,
                "away_xg": 1.05,
                "xg_total": 2.7,
                "xg_difference": 0.6,
                "xg_confidence": 85.0,
                "plan_support": "full",
                "comparison_available": True,
                "disagreement_score": 0.18,
                "xg_supports_internal": True,
                "data_sources": ["xGFixture"],
            },
        )
        signals["sportmonks_prediction_agent"] = make_signal(
            "sportmonks_prediction_agent",
            "sportmonks_prediction_benchmark",
            "available",
            {
                "sportmonks_confidence": 62.0,
                "disagreement_vs_internal": 0.32,
                "consensus_with_internal": 52.0,
                "conflict_level": "medium",
                "recommendation": "caution",
                "sportmonks_odds_available": True,
                "sportmonks_prediction_available": True,
                "internal_lean": "home_win",
                "sportmonks_lean": "home_win",
            },
        )
    return MatchSpecialistReport(fixture_id=fixture_id, signals=signals)


def load_replay_cases() -> list[ReplayCase]:
    from worldcup_predictor.accuracy.history_store import PredictionHistoryStore
    from worldcup_predictor.results.match_results_store import MatchResultsStore

    cases: list[ReplayCase] = []
    results = MatchResultsStore().by_fixture_id()
    latest = PredictionHistoryStore().latest_by_fixture()

    for fid, result in sorted(results.items()):
        rec = latest.get(int(fid))
        if rec is None:
            continue
        baseline = _make_baseline_from_history(rec)
        report = _make_report_from_result(result.to_dict())
        cases.append(
            ReplayCase(
                fixture_id=int(fid),
                match_name=f"{result.home_team} vs {result.away_team}",
                actual_1x2=str(result.winner),
                actual_over_under=str(result.over_under_2_5_result),
                source="wc2026_results_history",
                has_promotion_signals=False,
                baseline=baseline,
                report=report,
                specialist=None,
            )
        )

    from worldcup_predictor.backtesting.historical_loader import HistoricalLoader, build_form_history, build_intelligence_report

    csv_path = ROOT / "data" / "historical" / "worldcup_sample.csv"
    if csv_path.exists():
        loader = HistoricalLoader(csv_path)
        rows = loader.load(create_sample_if_missing=False)
        form_hist = build_form_history(rows)
        for row in rows[:12]:
            hf, af = form_hist.get(row.fixture_id, ([], []))
            report = build_intelligence_report(row, home_form=hf, away_form=af)
            from worldcup_predictor.domain.prediction import (
                ConfidenceLevel,
                FirstGoalPrediction,
                HalftimePrediction,
                MarketPrediction,
                MatchPrediction,
                PredictionConfidenceBreakdown,
            )

            baseline = MatchPrediction(
                fixture_id=row.fixture_id,
                competition_key="world_cup_2026",
                match_name=f"{row.home_team} vs {row.away_team}",
                one_x_two=MarketPrediction(market="1x2", selection="home_win", probability=0.42),
                over_under=MarketPrediction(market="over_under_2_5", selection="over_2_5", probability=0.55),
                halftime=HalftimePrediction(estimated_total_goals=1.3),
                first_goal=FirstGoalPrediction(team=row.home_team),
                confidence_score=58.0,
                confidence_level=ConfidenceLevel.MEDIUM,
                confidence_breakdown=PredictionConfidenceBreakdown(
                    form_score=55.0,
                    h2h_score=50.0,
                    injuries_score=50.0,
                    lineups_score=45.0,
                    odds_score=55.0,
                    data_quality_score=65.0,
                    total=58.0,
                ),
                risk_level="medium",
            )
            cases.append(
                ReplayCase(
                    fixture_id=row.fixture_id,
                    match_name=f"{row.home_team} vs {row.away_team}",
                    actual_1x2=row.actual_1x2,
                    actual_over_under=row.actual_over_under,
                    source="demo_wc2022_csv",
                    has_promotion_signals=False,
                    baseline=baseline,
                    report=report,
                    specialist=None,
                )
            )

    synth_specs = [
        (1489388, "Mexico vs South Korea", "home_win", "24a"),
        (1489399, "Brazil vs Morocco", "draw", "24b"),
        (1489400, "France vs Japan", "home_win", "24c"),
        (1489401, "Argentina vs Croatia", "home_win", "combo"),
    ]
    kickoff = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=2)
    for fid, name, actual, variant in synth_specs:
        home, away = name.split(" vs ", 1)
        from worldcup_predictor.domain.fixture import Fixture
        from worldcup_predictor.domain.intelligence import MatchIntelligenceReport, TeamIntelligence
        from worldcup_predictor.domain.prediction import (
            ConfidenceLevel,
            FirstGoalPrediction,
            HalftimePrediction,
            MarketPrediction,
            MatchPrediction,
            PredictionConfidenceBreakdown,
        )

        fixture = Fixture(
            id=fid,
            competition_key="world_cup_2026",
            home_team=home,
            away_team=away,
            home_team_id=10,
            away_team_id=11,
            kickoff_utc=kickoff,
            venue="Test Stadium",
            stage="Group Stage",
            league_id=1,
            season=2026,
            status="NS",
        )
        report = MatchIntelligenceReport(
            fixture_id=fid,
            fixture=fixture,
            home_team=TeamIntelligence(team_name=home, team_id=10),
            away_team=TeamIntelligence(team_name=away, team_id=11),
            is_placeholder=False,
        )
        baseline = MatchPrediction(
            fixture_id=fid,
            competition_key="world_cup_2026",
            match_name=name,
            one_x_two=MarketPrediction(market="1x2", selection="home_win", probability=0.48),
            over_under=MarketPrediction(market="over_under_2_5", selection="over_2_5", probability=0.55),
            halftime=HalftimePrediction(estimated_total_goals=1.4),
            first_goal=FirstGoalPrediction(team=home),
            confidence_score=64.0,
            confidence_level=ConfidenceLevel.MEDIUM,
            confidence_breakdown=PredictionConfidenceBreakdown(
                form_score=62.0,
                h2h_score=55.0,
                injuries_score=58.0,
                lineups_score=50.0,
                odds_score=52.0,
                data_quality_score=74.0,
                total=64.0,
            ),
            risk_level="medium",
        )
        cases.append(
            ReplayCase(
                fixture_id=fid,
                match_name=name,
                actual_1x2=actual,
                actual_over_under="over_2_5",
                source=f"synthetic_promotion_{variant}",
                has_promotion_signals=True,
                baseline=baseline,
                report=report,
                specialist=_synthetic_promotion_signals(fid, variant if variant != "combo" else "full"),
            )
        )

    seen: set[int] = set()
    deduped: list[ReplayCase] = []
    for case in cases:
        key = (case.fixture_id, case.source)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(case)
    return deduped


def _run_wde(case: ReplayCase, env: dict[str, str], stack_name: str) -> ReplayRow:
    import copy

    from worldcup_predictor.decision.weighted_decision_engine import DecisionInput, WeightedDecisionEngine

    _reset_env(**env)
    baseline = copy.deepcopy(case.baseline)
    wde = WeightedDecisionEngine()
    output = wde.decide(
        DecisionInput(baseline=baseline, report=case.report, specialist_report=case.specialist)
    )
    merged = wde.apply_decision(baseline, output)
    trace = output.audit.trace if output.audit and output.audit.trace else None

    if stack_name == "baseline":
        mode = "baseline"
    elif stack_name == "shadow_default":
        mode = "shadow"
    else:
        mode = "gated_simulation"

    gate_failures: list[str] = []
    promo_count = 0
    if wde._last_lineup_promotion:
        if wde._last_lineup_promotion.lineup_promotion_active:
            promo_count += 1
        elif env.get("EXPECTED_LINEUP_PROMOTION_MODE") != "off":
            gate_failures.append("24a")
    if wde._last_context_promotion:
        if wde._last_context_promotion.context_promotion_active:
            promo_count += 1
        elif env.get("TOURNAMENT_CONTEXT_PROMOTION_MODE") != "off":
            gate_failures.append("24b")
    if wde._last_xg_promotion:
        if wde._last_xg_promotion.xg_promotion_active:
            promo_count += 1
        elif env.get("XG_PROMOTION_MODE") != "off":
            gate_failures.append("24c_xg")
    if wde._last_sportmonks_promotion:
        if wde._last_sportmonks_promotion.sportmonks_promotion_active:
            promo_count += 1
        elif env.get("SPORTMONKS_PREDICTION_PROMOTION_MODE") != "off":
            gate_failures.append("24c_sm")

    predicted = str(merged.one_x_two.selection)
    return ReplayRow(
        fixture_id=case.fixture_id,
        match_name=case.match_name,
        source=case.source,
        stack=stack_name,
        mode=mode,
        actual_1x2=case.actual_1x2,
        predicted_1x2=predicted,
        baseline_1x2=str(case.baseline.one_x_two.selection),
        correct=predicted == case.actual_1x2,
        confidence=float(output.confidence_score),
        baseline_confidence=float(case.baseline.confidence_score),
        no_bet_flag=bool(output.no_bet_flag),
        no_bet_review_trace=bool(trace.sportmonks_no_bet_review_trace if trace else False),
        winner_flipped=False,
        combined_conf_delta=float(trace.combined_promotion_confidence_delta if trace else 0.0),
        lineup_delta=float(trace.lineup_delta_score if trace else 0.0),
        context_delta=float(trace.context_delta_score if trace else 0.0),
        xg_delta=float(trace.xg_delta_score if trace else 0.0),
        sportmonks_conf_delta=float(trace.sportmonks_confidence_delta if trace else 0.0),
        disagreement_signal=str(trace.sportmonks_disagreement_signal if trace else ""),
        promotion_active_count=promo_count,
        gate_failures=gate_failures,
    )


def run_replay(cases: list[ReplayCase]) -> list[ReplayRow]:
    rows: list[ReplayRow] = []
    baseline_preds: dict[int, str] = {}

    for case in cases:
        baseline_row = _run_wde(case, PROMOTION_STACKS["baseline"], "baseline")
        baseline_preds[case.fixture_id] = baseline_row.predicted_1x2
        rows.append(baseline_row)

    for stack_name, env in PROMOTION_STACKS.items():
        if stack_name == "baseline":
            continue
        for case in cases:
            row = _run_wde(case, env, stack_name)
            row.winner_flipped = row.predicted_1x2 != baseline_preds.get(case.fixture_id, row.baseline_1x2)
            rows.append(row)

    _reset_env()
    return rows


def _brier(rows: list[ReplayRow], cases: dict[int, ReplayCase]) -> float | None:
    scores: list[float] = []
    for row in rows:
        case = cases.get(row.fixture_id)
        if case is None:
            continue
        prob = case.baseline.one_x_two.probability
        if prob is None:
            continue
        actual = 1.0 if row.actual_1x2 == row.predicted_1x2 else 0.0
        scores.append((float(prob) - actual) ** 2)
    return round(sum(scores) / len(scores), 4) if scores else None


def aggregate_metrics(rows: list[ReplayRow], cases: list[ReplayCase]) -> list[StackMetrics]:
    case_map = {c.fixture_id: c for c in cases}
    grouped: dict[tuple[str, str], list[ReplayRow]] = defaultdict(list)
    for row in rows:
        grouped[(row.stack, row.mode)].append(row)

    metrics: list[StackMetrics] = []
    for (stack, mode), group in sorted(grouped.items()):
        correct = [r for r in group if r.correct]
        wrong = [r for r in group if not r.correct]
        high_conf_wrong = [r for r in group if r.confidence >= 60 and not r.correct]
        disagree = [r for r in group if r.disagreement_signal]
        review = [r for r in group if r.no_bet_review_trace]
        flips = [r for r in group if r.winner_flipped]
        promo_active = [r for r in group if r.promotion_active_count > 0]

        m = StackMetrics(
            stack=stack,
            mode=mode,
            n=len(group),
            one_x_two_accuracy=round(len(correct) / len(group), 4) if group else 0.0,
            avg_confidence=round(statistics.mean(r.confidence for r in group), 2) if group else 0.0,
            avg_confidence_correct=round(statistics.mean(r.confidence for r in correct), 2) if correct else 0.0,
            avg_confidence_wrong=round(statistics.mean(r.confidence for r in wrong), 2) if wrong else 0.0,
            brier_score=_brier(group, case_map),
            overconfidence_rate=round(len(high_conf_wrong) / len(group), 4) if group else 0.0,
            no_bet_review_rate=round(len(review) / len(group), 4) if group else 0.0,
            disagreement_rate=round(len(disagree) / len(group), 4) if group else 0.0,
            winner_flip_rate=round(len(flips) / len(group), 4) if group else 0.0,
            avg_combined_conf_delta=round(statistics.mean(r.combined_conf_delta for r in group), 3) if group else 0.0,
            avg_lineup_delta=round(statistics.mean(r.lineup_delta for r in group), 3) if group else 0.0,
            avg_context_delta=round(statistics.mean(r.context_delta for r in group), 3) if group else 0.0,
            avg_xg_delta=round(statistics.mean(r.xg_delta for r in group), 3) if group else 0.0,
            avg_sportmonks_conf_delta=round(statistics.mean(r.sportmonks_conf_delta for r in group), 3) if group else 0.0,
            promotion_coverage_rate=round(len(promo_active) / len(group), 4) if group else 0.0,
        )
        metrics.append(m)
    return metrics


def safety_analysis(rows: list[ReplayRow], cases: list[ReplayCase]) -> dict[str, Any]:
    gated = [r for r in rows if r.stack == "gated_simulation"]
    baseline = [r for r in rows if r.stack == "baseline"]
    synth = {c.fixture_id for c in cases if c.has_promotion_signals}

    conf_inflation = 0
    for g, b in zip(sorted(gated, key=lambda x: (x.fixture_id, x.source)), sorted(baseline, key=lambda x: (x.fixture_id, x.source))):
        if g.fixture_id == b.fixture_id and g.source == b.source and g.confidence > b.confidence + 2:
            conf_inflation += 1

    high_conflict = [r for r in gated if r.disagreement_signal.startswith("high")]
    bad_promo = [r for r in gated if r.gate_failures and r.fixture_id not in synth]
    coverage_gaps = len([c for c in cases if not c.has_promotion_signals])

    return {
        "confidence_inflation_cases": conf_inflation,
        "winner_flip_count": sum(1 for r in gated if r.winner_flipped),
        "high_conflict_cases": len(high_conflict),
        "gate_failure_without_signals": len(bad_promo),
        "coverage_gap_cases": coverage_gaps,
        "synthetic_signal_cases": len(synth),
    }


def recommend_flags(metrics: list[StackMetrics], safety: dict[str, Any]) -> dict[str, str]:
    rec = {
        "EXPECTED_LINEUP_PROMOTION_MODE": "shadow",
        "TOURNAMENT_CONTEXT_PROMOTION_MODE": "shadow",
        "XG_PROMOTION_MODE": "shadow",
        "SPORTMONKS_PREDICTION_PROMOTION_MODE": "shadow",
    }
    baseline_acc = next((m.one_x_two_accuracy for m in metrics if m.stack == "baseline"), 0.0)
    stacks = {
        "24a_only": next((m for m in metrics if m.stack == "24a_only"), None),
        "24b_only": next((m for m in metrics if m.stack == "24b_only"), None),
        "24c_xg_only": next((m for m in metrics if m.stack == "24c_xg_only"), None),
        "24c_sm_only": next((m for m in metrics if m.stack == "24c_sm_only"), None),
        "24a_24b_24c": next((m for m in metrics if m.stack == "24a_24b_24c"), None),
    }

    def _candidate(m: StackMetrics | None) -> str:
        if m is None or m.n == 0:
            return "shadow"
        uplift = m.one_x_two_accuracy - baseline_acc
        if uplift >= 0.05 and m.winner_flip_rate <= 0.05 and m.overconfidence_rate <= baseline_acc:
            return "gated_candidate"
        if uplift >= 0.02 and m.winner_flip_rate <= 0.08:
            return "shadow"
        if m.winner_flip_rate > 0.12 or m.overconfidence_rate > 0.35:
            return "off"
        return "shadow"

    rec["EXPECTED_LINEUP_PROMOTION_MODE"] = _candidate(stacks["24a_only"])
    rec["TOURNAMENT_CONTEXT_PROMOTION_MODE"] = _candidate(stacks["24b_only"])
    rec["XG_PROMOTION_MODE"] = _candidate(stacks["24c_xg_only"])
    sm = stacks["24c_sm_only"]
    if sm and sm.avg_sportmonks_conf_delta < -2 and safety["high_conflict_cases"] > 0:
        rec["SPORTMONKS_PREDICTION_PROMOTION_MODE"] = "shadow"
    else:
        rec["SPORTMONKS_PREDICTION_PROMOTION_MODE"] = _candidate(sm)

    if safety["winner_flip_count"] > 3:
        for key in rec:
            if rec[key] == "gated_candidate":
                rec[key] = "shadow"
    return rec


def write_report(
    cases: list[ReplayCase],
    rows: list[ReplayRow],
    metrics: list[StackMetrics],
    safety: dict[str, Any],
    recommendations: dict[str, str],
) -> None:
    sources: dict[str, int] = defaultdict(int)
    for c in cases:
        sources[c.source] += 1

    lines = [
        "# Phase 25 — Calibration + Shadow Replay Report",
        "",
        "**Status:** Complete (local evaluation — no deployment, no gated auto-enable)",
        "",
        "## Dataset",
        "",
        f"- **Total replay cases:** {len(cases)}",
        f"- **Total replay rows (cases × stacks):** {len(rows)}",
        "",
        "| Source | Count |",
        "|--------|-------|",
    ]
    for src, count in sorted(sources.items()):
        lines.append(f"| {src} | {count} |")

    lines.extend(
        [
            "",
            "## Promotion Modes Evaluated",
            "",
            "1. **baseline** — all promotion flags `off`",
            "2. **shadow_default** — all flags `shadow` (runtime default)",
            "3. **gated_simulation** — isolated `gated` apply (does not change defaults)",
            "",
            "## Metric Comparison",
            "",
            "| Stack | Mode | N | 1X2 Acc | Avg Conf | Brier | Overconf | Review | Disagree | Flip | Promo Cov |",
            "|-------|------|---|---------|----------|-------|----------|--------|----------|------|-----------|",
        ]
    )
    for m in metrics:
        brier = f"{m.brier_score:.3f}" if m.brier_score is not None else "n/a"
        lines.append(
            f"| {m.stack} | {m.mode} | {m.n} | {m.one_x_two_accuracy:.1%} | {m.avg_confidence:.1f} | "
            f"{brier} | {m.overconfidence_rate:.1%} | {m.no_bet_review_rate:.1%} | "
            f"{m.disagreement_rate:.1%} | {m.winner_flip_rate:.1%} | {m.promotion_coverage_rate:.1%} |"
        )

    lines.extend(["", "## Promotion Stack Comparison (gated simulation)", ""])
    for m in [x for x in metrics if x.stack not in ("baseline", "shadow_default")]:
        lines.append(
            f"- **{m.stack}**: acc {m.one_x_two_accuracy:.1%}, flip {m.winner_flip_rate:.1%}, "
            f"avg Δconf {m.avg_combined_conf_delta:+.2f}, lineup Δ {m.avg_lineup_delta:+.2f}, "
            f"context Δ {m.avg_context_delta:+.2f}, xG Δ {m.avg_xg_delta:+.2f}, SM Δ {m.avg_sportmonks_conf_delta:+.2f}"
        )

    lines.extend(["", "## Risk Analysis", ""])
    for key, val in safety.items():
        lines.append(f"- **{key}:** {val}")

    lines.extend(["", "## Recommended Flag Settings (manual approval required)", ""])
    lines.append("| Flag | Recommendation |")
    lines.append("|------|----------------|")
    for flag, rec in recommendations.items():
        lines.append(f"| `{flag}` | **{rec}** (default remains `shadow` until approved) |")

    lines.extend(
        [
            "",
            "## Next Step Recommendation",
            "",
            "1. Continue **shadow** defaults for all four promotion flags.",
            "2. Expand replay with full specialist orchestrator snapshots when WC 2026 group-stage results accumulate.",
            "3. Enable **gated** per promotion only after manual review of this report and live shadow JSONL.",
            "4. Phase 25 weight calibration deferred — WDE weights unchanged.",
            "",
            f"Replay JSONL: `{REPLAY_JSONL.relative_to(ROOT)}`",
            f"Metrics JSON: `{METRICS_JSON.relative_to(ROOT)}`",
            "",
            "**Phase 25 complete. Deployment not started.**",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def persist_outputs(rows: list[ReplayRow], metrics: list[StackMetrics]) -> None:
    REPLAY_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with REPLAY_JSONL.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")
    METRICS_JSON.write_text(
        json.dumps([asdict(m) for m in metrics], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    cases = load_replay_cases()
    if not cases:
        print("No replay cases loaded", file=sys.stderr)
        return 1

    rows = run_replay(cases)
    metrics = aggregate_metrics(rows, cases)
    safety = safety_analysis(rows, cases)
    recommendations = recommend_flags(metrics, safety)
    persist_outputs(rows, metrics)
    write_report(cases, rows, metrics, safety, recommendations)

    defaults_ok = _verify_defaults_unchanged()
    print(f"Phase 25 shadow replay: {len(cases)} cases, {len(rows)} rows")
    print(f"Default flags preserved: {defaults_ok}")
    print(f"Report: {REPORT_PATH}")
    for m in metrics:
        if m.stack in ("baseline", "shadow_default", "gated_simulation"):
            print(f"  {m.stack}: acc={m.one_x_two_accuracy:.1%} n={m.n}")
    return 0 if defaults_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
