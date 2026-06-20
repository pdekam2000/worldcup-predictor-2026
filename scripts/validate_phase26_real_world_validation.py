"""Phase 26 — real-world validation framework validation (offline)."""

from __future__ import annotations

import json
import runpy
import tempfile
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "PHASE_26_REAL_WORLD_VALIDATION_REPORT.md"


def main() -> int:
    checks: list[tuple[str, bool]] = []

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        val_path = tmp_path / "validation.jsonl"
        stats_path = tmp_path / "stats.json"

        from worldcup_predictor.config.settings import get_settings

        get_settings.cache_clear()

        from worldcup_predictor.agents.specialists.helpers import make_signal
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
        from worldcup_predictor.domain.specialist import MatchSpecialistReport
        from worldcup_predictor.decision.audit_report import FinalDecisionTrace, PredictionAuditReport
        from worldcup_predictor.validation.capture import build_validation_record, maybe_record_real_world_validation
        from worldcup_predictor.validation.service import RealWorldValidationService
        from worldcup_predictor.validation.store import RealWorldValidationStore

        fixture = Fixture(
            id=1489500,
            competition_key="world_cup_2026",
            home_team="France",
            away_team="Japan",
            home_team_id=1,
            away_team_id=2,
            kickoff_utc=__import__("datetime").datetime(2026, 6, 20, 19, 0, 0),
            venue="Test",
            stage="Group Stage",
            league_id=1,
            season=2026,
            status="NS",
        )
        report = MatchIntelligenceReport(
            fixture_id=1489500,
            fixture=fixture,
            home_team=TeamIntelligence(team_name="France", team_id=1),
            away_team=TeamIntelligence(team_name="Japan", team_id=2),
            is_placeholder=False,
        )
        prediction = MatchPrediction(
            fixture_id=1489500,
            competition_key="world_cup_2026",
            match_name="France vs Japan",
            one_x_two=MarketPrediction(market="1x2", selection="home_win", probability=0.52),
            over_under=MarketPrediction(market="over_under_2_5", selection="over_2_5", probability=0.55),
            halftime=HalftimePrediction(estimated_total_goals=1.5),
            first_goal=FirstGoalPrediction(team="France"),
            confidence_score=64.0,
            confidence_level=ConfidenceLevel.MEDIUM,
            confidence_breakdown=PredictionConfidenceBreakdown(
                form_score=60.0,
                h2h_score=50.0,
                injuries_score=55.0,
                lineups_score=50.0,
                odds_score=52.0,
                data_quality_score=72.0,
                total=64.0,
            ),
            risk_level="medium",
        )
        specialist = MatchSpecialistReport(
            fixture_id=1489500,
            signals={
                "expected_lineup_agent": make_signal(
                    "expected_lineup_agent",
                    "expected_lineup",
                    "available",
                    {"lineup_confidence": 60.0, "data_sources": ["api"], "expected_xi_quality": 70.0},
                ),
                "tournament_context_agent": make_signal(
                    "tournament_context_agent",
                    "tournament_context",
                    "available",
                    {"group_context_strength": 50.0, "data_sources": ["standings"], "motivation_score_home": 70.0},
                ),
                "xg_intelligence_agent": make_signal(
                    "xg_intelligence_agent",
                    "sportmonks_xg",
                    "available",
                    {"xg_confidence": 80.0, "xg_total": 2.6, "comparison_available": True, "data_sources": ["xGFixture"]},
                ),
                "sportmonks_prediction_agent": make_signal(
                    "sportmonks_prediction_agent",
                    "sportmonks_prediction",
                    "available",
                    {
                        "sportmonks_confidence": 62.0,
                        "disagreement_vs_internal": 0.2,
                        "sportmonks_odds_available": True,
                        "sportmonks_prediction_available": True,
                    },
                ),
            },
        )
        prediction.audit_report = PredictionAuditReport(
            fixture_id=1489500,
            trace=FinalDecisionTrace(
                baseline_confidence=64.0,
                final_confidence=63.0,
                lineup_promotion_active=True,
                lineup_delta_score=2.0,
                context_promotion_active=True,
                context_delta_score=1.0,
                xg_promotion_active=True,
                xg_delta_score=0.5,
                sportmonks_promotion_active=True,
                sportmonks_confidence_delta=-1.0,
                sportmonks_disagreement_signal="medium:0.200",
                combined_promotion_confidence_delta=-1.0,
            ),
        )

        record = build_validation_record(prediction=prediction, report=report, specialist=specialist)
        checks.append(("record_has_four_promotions", len(record.promotions) == 4))
        checks.append(("record_has_snapshots", bool(record.snapshots.xg_snapshot)))
        checks.append(("record_has_deltas", "lineup_delta_score" in record.promotion_deltas))

        store = RealWorldValidationStore(val_path)
        maybe_record_real_world_validation(
            prediction=prediction,
            report=report,
            specialist=specialist,
            enabled=True,
            store_path=str(val_path),
        )
        checks.append(("capture_writes_store", len(store.load_all()) >= 1))

        svc = RealWorldValidationService(store=store)
        added = svc.backfill_from_phase25_replay(str(ROOT / "data" / "shadow" / "phase25_promotion_replay.jsonl"))
        checks.append(("phase25_backfill", added >= 0))

        settled = svc.settle_from_match_results()
        checks.append(("settle_runs", settled >= 0))

        readiness = svc.readiness()
        checks.append(("readiness_score_range", 0 <= readiness.score <= 100))
        checks.append(("readiness_has_components", readiness.data_quality >= 0))

        weekly, monthly = svc.generate_reports()
        checks.append(("weekly_report_exists", Path(weekly).is_file()))
        checks.append(("monthly_report_exists", Path(monthly).is_file()))

        get_settings.cache_clear()
        s = get_settings()
        checks.append(("promotion_lineup_shadow", s.expected_lineup_promotion_mode == "shadow"))
        checks.append(("promotion_context_shadow", s.tournament_context_promotion_mode == "shadow"))
        checks.append(("promotion_xg_shadow", s.xg_promotion_mode == "shadow"))
        checks.append(("promotion_sm_shadow", s.sportmonks_prediction_promotion_mode == "shadow"))
        checks.append(("validation_mode_shadow", s.real_world_validation_mode == "shadow"))

    checks.append(("phase26_report_exists", REPORT.is_file()))
    if REPORT.is_file():
        text = REPORT.read_text(encoding="utf-8")
        for token in (
            "Storage Design",
            "Metrics Tracked",
            "WorldCupReadinessScore",
            "Reporting Design",
            "Validation Results",
        ):
            checks.append((f"report_has_{token.lower().replace(' ', '_')}", token in text))

    failed = [name for name, ok in checks if not ok]
    passed = len(checks) - len(failed)
    print(f"Phase 26 real-world validation: {passed}/{len(checks)} passed")
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        print("Failed:", ", ".join(failed))
        return 1
    print(f"  readiness={readiness.score:.1f} backfill_added={added} settled={settled}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
