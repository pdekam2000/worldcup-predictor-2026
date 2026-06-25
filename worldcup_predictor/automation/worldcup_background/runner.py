"""Phase 33 auto-cycle runner — predict then evaluate."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from worldcup_predictor.automation.worldcup_background.accuracy_summary import (
    get_accuracy_summary,
    rebuild_accuracy_summary,
)
from worldcup_predictor.automation.worldcup_background.daily_prediction_job import (
    DailyPredictionJobResult,
    run_daily_worldcup_prediction,
)
from worldcup_predictor.automation.worldcup_background.result_evaluation_job import (
    EvaluationJobResult,
    run_evaluate_worldcup_results,
)
from worldcup_predictor.config.settings import Settings, get_settings


def run_daily_worldcup_predict(
    *,
    settings: Settings | None = None,
    window_days: int | None = None,
    force_refresh: bool = False,
    limit: int | None = None,
) -> DailyPredictionJobResult:
    return run_daily_worldcup_prediction(
        settings=settings,
        window_days=window_days,
        force_refresh=force_refresh,
        limit=limit,
    )


def run_evaluate_worldcup_results_cli(
    *,
    settings: Settings | None = None,
    limit: int | None = None,
    mode: str = "stored_first",
) -> EvaluationJobResult:
    return run_evaluate_worldcup_results(
        settings=settings,
        limit=limit,
        mode=mode,  # type: ignore[arg-type]
    )

def run_worldcup_auto_cycle(
    *,
    settings: Settings | None = None,
    window_days: int | None = None,
    report_path: str | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    predict_result = run_daily_worldcup_prediction(settings=settings, window_days=window_days)
    eval_result = run_evaluate_worldcup_results(settings=settings)
    summary = rebuild_accuracy_summary(settings=settings)

    report: dict[str, Any] = {
        "phase": "33",
        "predict": asdict(predict_result),
        "evaluate": asdict(eval_result),
        "accuracy_summary": summary,
    }

    out = Path(report_path or "artifacts/phase33_auto_cycle_report.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return report
