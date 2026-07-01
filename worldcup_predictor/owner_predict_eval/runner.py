"""Part E — One-command owner daily prediction + evaluation runner."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.owner_predict_eval.constants import ARTIFACTS_DIR, PHASE, REPORTS_DIR, with_safety_labels
from worldcup_predictor.owner_predict_eval.data_audit import audit_prediction_data_usage
from worldcup_predictor.owner_predict_eval.dates import date_tag, resolve_process_date, yesterday_of
from worldcup_predictor.owner_predict_eval.fixture_discovery import discover_today_fixtures
from worldcup_predictor.owner_predict_eval.predictions import build_today_predictions
from worldcup_predictor.owner_predict_eval.status_report import derive_recommendation, write_status_report
from worldcup_predictor.owner_predict_eval.yesterday_eval import evaluate_yesterday_predictions


@dataclass
class OwnerDailyRunResult:
    phase: str = PHASE
    process_date: str = ""
    discovery: dict[str, Any] = field(default_factory=dict)
    predictions: dict[str, Any] = field(default_factory=dict)
    yesterday_evaluation: dict[str, Any] = field(default_factory=dict)
    data_audit: dict[str, Any] = field(default_factory=dict)
    owner_daily_summary: dict[str, Any] = field(default_factory=dict)
    recommendation: str = ""
    md_path: str = ""
    json_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return with_safety_labels(
            {
                "phase": self.phase,
                "process_date": self.process_date,
                "discovery": self.discovery,
                "predictions": self.predictions,
                "yesterday_evaluation": self.yesterday_evaluation,
                "data_audit": self.data_audit,
                "owner_daily_summary": self.owner_daily_summary,
                "recommendation": self.recommendation,
                "md_path": self.md_path,
                "json_path": self.json_path,
            }
        )


def daily_report_md_path(target: date) -> Path:
    return REPORTS_DIR / f"OWNER_DAILY_PREDICTION_AND_EVAL_{date_tag(target)}.md"


def daily_report_json_path(target: date) -> Path:
    return ARTIFACTS_DIR / f"owner_daily_prediction_and_eval_{date_tag(target)}.json"


def run_owner_daily_prediction_and_eval(
    *,
    date_arg: str = "today",
    timezone: str = "Europe/Vienna",
    limit: int = 50,
    settings: Settings | None = None,
) -> OwnerDailyRunResult:
    settings = settings or get_settings()
    process_date = resolve_process_date(date_arg, timezone)

    discovery = discover_today_fixtures(
        date_arg=date_arg,
        timezone=timezone,
        limit=limit,
        settings=settings,
        fetch_if_missing=False,
    )
    predictions = build_today_predictions(discovery.to_dict(), settings=settings)
    yesterday_date = yesterday_of(process_date)
    yesterday = evaluate_yesterday_predictions(
        date_arg=yesterday_date.isoformat(),
        timezone=timezone,
        settings=settings,
    )
    fixture_ids = [int(f.fixture_id) for f in discovery.fixtures]
    audit = audit_prediction_data_usage(
        date_arg=date_arg,
        timezone=timezone,
        fixture_ids=fixture_ids,
        settings=settings,
    )

    recommendation = derive_recommendation(
        discovery=discovery.to_dict(),
        predictions=predictions.to_dict(),
        yesterday=yesterday.to_dict(),
        audit=audit.to_dict(),
    )

    owner_daily_summary = _build_owner_daily_summary(
        discovery=discovery.to_dict(),
        predictions=predictions.to_dict(),
        yesterday=yesterday.to_dict(),
        audit=audit.to_dict(),
        recommendation=recommendation,
    )

    result = OwnerDailyRunResult(
        process_date=process_date.isoformat(),
        discovery=discovery.to_dict(),
        predictions=predictions.to_dict(),
        yesterday_evaluation=yesterday.to_dict(),
        data_audit=audit.to_dict(),
        owner_daily_summary=owner_daily_summary,
        recommendation=recommendation,
    )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = daily_report_json_path(process_date)
    md_path = daily_report_md_path(process_date)
    json_path.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    result.json_path = str(json_path)
    result.md_path = str(md_path)

    lines = [
        f"# Owner Daily Prediction and Evaluation — {process_date.isoformat()}",
        "",
        f"**Recommendation:** `{recommendation}`",
        "",
        "## Owner daily summary",
        "",
        f"- Today fixtures count: **{owner_daily_summary['today_fixtures_count']}**",
        f"- Today prediction status: **{owner_daily_summary['today_prediction_status']}**",
        f"- Yesterday fixtures count: **{owner_daily_summary['yesterday_fixtures_count']}**",
        f"- Yesterday evaluated count: **{owner_daily_summary['yesterday_evaluated_count']}**",
        f"- Yesterday missing-results count: **{owner_daily_summary['yesterday_missing_results_count']}**",
        f"- WDE retrain status: **{owner_daily_summary['wde_retrain_status']}**",
        f"- Historical CSV promotion status: **{owner_daily_summary['historical_csv_promotion_status']}**",
        f"- OddAlerts ECSE status: **{owner_daily_summary['oddalerts_ecse_status']}**",
        f"- Final recommendation: **{owner_daily_summary['final_recommendation']}**",
        "",
        "## Answers",
        "",
        f"- Can I predict today? **{_can_predict_today(predictions.to_dict(), discovery.fixture_count)}**",
        f"- Were yesterday's games evaluated? **{_yesterday_evaluated(yesterday.to_dict())}**",
        f"- Was the model retrained with the new database? **{'no' if not audit.wde_retrained_with_historical_csv else 'yes'}**",
        "",
        "## Summary",
        "",
        f"- Today fixtures: {discovery.fixture_count}",
        f"- Today predictions loaded: {predictions.fixture_count}",
        f"- Yesterday evaluated: {yesterday.evaluated_count} / {yesterday.fixture_count} (waiting: {yesterday.waiting_result_count})",
        f"- OddAlerts CSV odds fixtures: {audit.oddalerts_csv_snapshot_count}",
        f"- ECSE OddAlerts mode: {audit.ecse_oddalerts_mode}",
        "",
        "## Safety labels",
        "",
        "- **PUBLIC_PUBLISH:** `false`",
        "- **WDE_RETRAINED:** `false`",
        "- **HISTORICAL_CSV_PROMOTED:** `false`",
        "- **ODDALERTS_ECSE_PRODUCTION:** `false`",
        "- **ODDALERTS_ECSE_SHADOW_ONLY:** `true`",
        "",
        "## Artifacts",
        "",
        f"- Fixtures: `{discovery.artifact_path}`",
        f"- Predictions: `{predictions.json_path}`",
        f"- Yesterday eval: `{yesterday.json_path}`",
        f"- Data audit: `{audit.artifact_path}`",
        "",
        "Owner/internal only — no public publish, no WDE retrain, no production ECSE promotion from shadow.",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")

    write_status_report(
        process_date=process_date,
        run_result=result.to_dict(),
        recommendation=recommendation,
    )
    return result


def _can_predict_today(predictions: dict[str, Any], fixture_count: int) -> str:
    if fixture_count == 0:
        return "no fixtures today"
    rows = predictions.get("predictions") or []
    with_wde = sum(1 for r in rows if r.get("wde"))
    if with_wde == 0:
        return "no — missing WDE predictions"
    if with_wde < len(rows):
        return f"partial — {with_wde}/{len(rows)} have WDE"
    return "yes — predictions loaded for all fixtures"


def _yesterday_evaluated(yesterday: dict[str, Any]) -> str:
    total = int(yesterday.get("fixture_count") or 0)
    ev = int(yesterday.get("evaluated_count") or 0)
    waiting = int(yesterday.get("waiting_result_count") or 0)
    if total == 0:
        return "no fixtures with predictions yesterday"
    if ev == total:
        return f"yes — all {ev} evaluated"
    if ev > 0:
        return f"partial — {ev} evaluated, {waiting} waiting"
    return f"no — {waiting} waiting for results"


def _today_prediction_status(predictions: dict[str, Any], fixture_count: int) -> str:
    if fixture_count == 0:
        return "no_fixtures"
    rows = predictions.get("predictions") or []
    with_wde = sum(1 for r in rows if r.get("wde"))
    if with_wde == 0:
        return "missing_predictions"
    if with_wde < len(rows):
        return f"partial_{with_wde}_of_{len(rows)}"
    return "ready"


def _build_owner_daily_summary(
    *,
    discovery: dict[str, Any],
    predictions: dict[str, Any],
    yesterday: dict[str, Any],
    audit: dict[str, Any],
    recommendation: str,
) -> dict[str, Any]:
    today_count = int(discovery.get("fixture_count") or 0)
    y_total = int(yesterday.get("fixture_count") or 0)
    y_eval = int(yesterday.get("evaluated_count") or 0)
    y_missing = int(yesterday.get("waiting_result_count") or 0)
    return {
        "today_fixtures_count": today_count,
        "today_prediction_status": _today_prediction_status(predictions, today_count),
        "yesterday_fixtures_count": y_total,
        "yesterday_evaluated_count": y_eval,
        "yesterday_missing_results_count": y_missing,
        "wde_retrain_status": "retrained" if audit.get("wde_retrained_with_historical_csv") else "not_retrained",
        "historical_csv_promotion_status": (
            "promoted" if audit.get("historical_csv_promoted_from_staging") else "staged_only"
        ),
        "oddalerts_ecse_status": audit.get("ecse_oddalerts_mode", "shadow"),
        "final_recommendation": recommendation,
    }
