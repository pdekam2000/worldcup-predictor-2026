"""Part H — One-command owner daily full refresh (predict, eval, panel, validate)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.owner_predict_eval.constants import PHASE, with_safety_labels
from worldcup_predictor.owner_predict_eval.control_panel import build_owner_daily_control_panel
from worldcup_predictor.owner_predict_eval.runner import run_owner_daily_prediction_and_eval
from worldcup_predictor.owner_predict_eval.validation import validate_owner_daily_prediction_and_eval
from worldcup_predictor.owner_predict_eval.yesterday_eval import evaluate_yesterday_predictions


@dataclass
class FullRefreshResult:
    phase: str = PHASE
    date_arg: str = ""
    process_date: str = ""
    recommendation: str = ""
    action_required: str = ""
    today_fixture_count: int = 0
    yesterday_evaluated_count: int = 0
    yesterday_missing_count: int = 0
    best_tip_status: str = ""
    validation_passed: bool | None = None
    validation_check_count: int = 0
    steps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return with_safety_labels(
            {
                "phase": self.phase,
                "date_arg": self.date_arg,
                "process_date": self.process_date,
                "recommendation": self.recommendation,
                "action_required": self.action_required,
                "today_fixture_count": self.today_fixture_count,
                "yesterday_evaluated_count": self.yesterday_evaluated_count,
                "yesterday_missing_count": self.yesterday_missing_count,
                "best_tip_status": self.best_tip_status,
                "validation_passed": self.validation_passed,
                "validation_check_count": self.validation_check_count,
                "steps": self.steps,
            }
        )


def run_owner_daily_full_refresh(
    *,
    date_arg: str = "today",
    timezone: str = "Europe/Vienna",
    skip_validation: bool = False,
    refresh_missing_results: bool = True,
    settings: Settings | None = None,
) -> FullRefreshResult:
    settings = settings or get_settings()
    steps: list[str] = []

    run = run_owner_daily_prediction_and_eval(
        date_arg=date_arg,
        timezone=timezone,
        settings=settings,
    )
    steps.append("run_owner_daily_prediction_and_eval")

    if refresh_missing_results:
        evaluate_yesterday_predictions(
            date_arg=date_arg,
            timezone=timezone,
            settings=settings,
            refresh_missing_results=True,
        )
        steps.append("evaluate_owner_yesterday_predictions_refresh")

    panel = build_owner_daily_control_panel(date_arg=date_arg, timezone=timezone)
    steps.append("build_owner_daily_control_panel")

    validation_passed: bool | None = None
    validation_check_count = 0
    if not skip_validation:
        validation = validate_owner_daily_prediction_and_eval(
            date_arg=date_arg,
            timezone=timezone,
            settings=settings,
        )
        validation_passed = validation.passed
        validation_check_count = len(validation.checks)
        steps.append("validate_owner_daily_prediction_and_eval")

    best_tip = panel.best_tip_candidate or {}
    best_tip_status = str(best_tip.get("status") or "UNKNOWN")

    return FullRefreshResult(
        date_arg=date_arg,
        process_date=panel.process_date,
        recommendation=panel.recommendation,
        action_required=panel.action_required,
        today_fixture_count=len(panel.today_fixtures),
        yesterday_evaluated_count=int(panel.yesterday_evaluation.get("evaluated_count") or 0),
        yesterday_missing_count=int(panel.yesterday_evaluation.get("missing_count") or 0),
        best_tip_status=best_tip_status,
        validation_passed=validation_passed,
        validation_check_count=validation_check_count,
        steps=steps,
    )
