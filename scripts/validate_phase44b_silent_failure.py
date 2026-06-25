#!/usr/bin/env python3
"""Phase 44B — silent enrichment failure elimination validation."""

from __future__ import annotations

import json
import runpy
from pathlib import Path
from unittest.mock import patch

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> int:
    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    out = Path("artifacts/phase44b_silent_failure_validation.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"phase": "44B", "passed": passed, "total": total, "checks": [
            {"name": n, "ok": ok, "detail": d} for n, ok, d in checks
        ]}, indent=2),
        encoding="utf-8",
    )
    print(f"Phase 44B validation: {passed}/{total} PASS")
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return 0 if passed == total else 1


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    root = Path(__file__).resolve().parents[1]
    record("safe_enrichment_logger_module", (root / "worldcup_predictor/providers/safe_enrichment_logger.py").is_file())

    targets = [
        "worldcup_predictor/orchestration/predict_pipeline.py",
        "worldcup_predictor/intelligence/national_team/integration.py",
        "worldcup_predictor/intelligence/first_goal_intelligence_v2.py",
        "worldcup_predictor/providers/sportmonks_consumption.py",
        "worldcup_predictor/fusion/final_decision_fusion_engine_v2.py",
        "worldcup_predictor/api/display_helpers.py",
        "worldcup_predictor/api/routes/predictions.py",
        "worldcup_predictor/automation/worldcup_background/prediction_runner.py",
    ]
    for rel in targets:
        text = (root / rel).read_text(encoding="utf-8")
        record(f"no_silent_pass_{rel.split('/')[-1]}", "except Exception:\n        pass" not in text and "except:\n        pass" not in text)
        record(f"uses_logger_{rel.split('/')[-1]}", "log_enrichment_failure" in text or "logger." in text)

    # Force enrichment failure — prediction still succeeds
    from worldcup_predictor.config.settings import Settings
    from worldcup_predictor.domain.prediction import (
        ConfidenceLevel,
        FirstGoalPrediction,
        HalftimePrediction,
        MarketPrediction,
        MatchPrediction,
        PredictionConfidenceBreakdown,
    )
    from worldcup_predictor.orchestration.predict_pipeline import PredictPipeline

    settings = Settings()
    pipeline = PredictPipeline(settings)

    base_prediction = MatchPrediction(
        fixture_id=99044,
        competition_key="world_cup_2026",
        match_name="A vs B",
        one_x_two=MarketPrediction(market="1x2", selection="home"),
        over_under=MarketPrediction(market="over_under_2_5", selection="under_2_5"),
        halftime=HalftimePrediction(estimated_total_goals=1.0),
        first_goal=FirstGoalPrediction(team="A"),
        confidence_score=55.0,
        confidence_level=ConfidenceLevel.MEDIUM,
        confidence_breakdown=PredictionConfidenceBreakdown(
            form_score=50, h2h_score=50, injuries_score=50, lineups_score=50,
            odds_score=50, data_quality_score=50, total=55,
        ),
        risk_level="medium",
        no_bet_flag=False,
    )

    class _FakePredictResult:
        success = True
        data = base_prediction

    class _FakeCollect:
        success = True

    with patch("worldcup_predictor.orchestration.predict_pipeline.DataCollectorAgent") as dc, patch(
        "worldcup_predictor.orchestration.predict_pipeline.SpecialistOrchestrator"
    ) as sp, patch("worldcup_predictor.orchestration.predict_pipeline.PredictionAgent") as pa, patch(
        "worldcup_predictor.providers.weather_extraction.attach_weather_to_prediction",
        side_effect=RuntimeError("forced_weather_failure"),
    ), patch(
        "worldcup_predictor.providers.sportmonks_xg_extraction.attach_sportmonks_xg_to_prediction",
        side_effect=RuntimeError("forced_xg_failure"),
    ):
        dc.return_value.run.return_value = _FakeCollect()
        sp.return_value.run.return_value = _FakeCollect()
        pa.return_value.run.return_value = _FakePredictResult()
        result = pipeline.run(99044, record_history=False)

    record("prediction_survives_enrichment_failure", result.success is True)
    record("prediction_fixture_preserved", result.prediction.fixture_id == 99044)

    from worldcup_predictor.providers.safe_enrichment_logger import log_enrichment_failure

    record("logger_callable", callable(log_enrichment_failure))

    # WDE / scoring engine untouched
    wde = (root / "worldcup_predictor/decision/weighted_decision_engine.py").read_text(encoding="utf-8")
    record("wde_not_modified_in_44b", "log_enrichment_failure" not in wde)

    return _report(checks)


if __name__ == "__main__":
    raise SystemExit(main())
