"""Part G — Status report and recommendation."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from worldcup_predictor.owner_predict_eval.constants import OWNER_DAILY_PREDICT_EVAL_REPORT, PHASE, SAFETY_LABELS


def derive_recommendation(
    *,
    discovery: dict[str, Any],
    predictions: dict[str, Any],
    yesterday: dict[str, Any],
    audit: dict[str, Any],
) -> str:
    fixture_count = int(discovery.get("fixture_count") or 0)
    if fixture_count == 0:
        return "TODAY_NO_FIXTURES"

    rows = predictions.get("predictions") or []
    wde_count = sum(1 for r in rows if r.get("wde"))
    if wde_count == 0:
        return "NEED_PREDICTION_GENERATION"

    if audit.get("wde_retrained_with_historical_csv"):
        pass  # documented in report; does not block owner daily ops

    waiting = int(yesterday.get("waiting_result_count") or 0)
    y_total = int(yesterday.get("fixture_count") or 0)
    y_eval = int(yesterday.get("evaluated_count") or 0)

    missing_odds = sum(
        1 for r in rows if (r.get("data_source_audit") or {}).get("ODDS_SOURCE") == "none"
    )
    if missing_odds == fixture_count:
        return "DO_NOT_USE_FOR_BETS"

    if y_total > 0 and y_eval == 0 and waiting > 0:
        return "NEED_RESULT_SYNC"

    if waiting > 0 and y_eval > 0:
        return "OWNER_DAILY_READY_WITH_MISSING_RESULTS"

    if wde_count < fixture_count or missing_odds > fixture_count // 2:
        return "DO_NOT_USE_FOR_BETS"

    if not audit.get("wde_retrained_with_historical_csv"):
        # Model not retrained is expected; still operational for owner daily if predictions exist
        pass

    return "OWNER_DAILY_READY"


def write_status_report(
    *,
    process_date: date,
    run_result: dict[str, Any],
    recommendation: str,
) -> Path:
    audit = run_result.get("data_audit") or {}
    discovery = run_result.get("discovery") or {}
    predictions = run_result.get("predictions") or {}
    yesterday = run_result.get("yesterday_evaluation") or {}

    lines = [
        "# Owner Daily Prediction Eval Status Report",
        "",
        f"**Phase:** {PHASE}",
        f"**Date:** {process_date.isoformat()}",
        f"**Recommendation:** `{recommendation}`",
        "",
        "## Executive answers",
        "",
        "| Question | Answer |",
        "|----------|--------|",
        f"| Can I predict today? | {_can_predict(predictions, discovery)} |",
        f"| Were yesterday's games evaluated? | {_yesterday(yesterday)} |",
        f"| Was the model retrained with the new database? | {'No' if not audit.get('wde_retrained_with_historical_csv') else 'Yes'} |",
        "",
        "## Data usage audit",
        "",
        f"- WDE retrained with Historical CSV: **{'yes' if audit.get('wde_retrained_with_historical_csv') else 'no'}**",
        f"- Historical CSV promoted from staging: **{'yes' if audit.get('historical_csv_promoted_from_staging') else 'no'}**",
        f"- OddAlerts CSV odds_snapshots in use: **{'yes' if audit.get('oddalerts_csv_odds_snapshots_used') else 'no'}** ({audit.get('oddalerts_csv_snapshot_count', 0)} fixtures)",
        f"- ECSE OddAlerts mode: **{audit.get('ecse_oddalerts_mode', 'shadow')}** (shadow/owner-only expected)",
        "",
        "## Before claiming model trained with new database",
        "",
    ]
    for item in audit.get("prerequisites_before_model_trained_claim") or []:
        lines.append(f"- {item}")

    lines.extend(
        [
            "",
            "## Owner daily summary",
            "",
            f"- Today fixtures: **{int(discovery.get('fixture_count') or 0)}**",
            f"- Today prediction status: **{_prediction_status(predictions, discovery)}**",
            f"- Yesterday fixtures: **{int(yesterday.get('fixture_count') or 0)}**",
            f"- Yesterday evaluated: **{int(yesterday.get('evaluated_count') or 0)}**",
            f"- Yesterday missing results: **{int(yesterday.get('waiting_result_count') or 0)}**",
            f"- WDE retrain status: **{'not_retrained' if not audit.get('wde_retrained_with_historical_csv') else 'retrained'}**",
            f"- Historical CSV promotion: **{'staged_only' if not audit.get('historical_csv_promoted_from_staging') else 'promoted'}**",
            f"- OddAlerts ECSE status: **{audit.get('ecse_oddalerts_mode', 'shadow')}**",
            f"- Final recommendation: **{recommendation}**",
            "",
            "## Constraints honored",
            "",
            "- Owner/internal only — no public publish",
            "- No WDE retraining in this phase",
            "- No production ECSE writes from OddAlerts shadow",
            "- Targeted DB queries per fixture_id",
            "",
            "## Safety labels",
            "",
            *[f"- **{k}:** `{v}`" for k, v in SAFETY_LABELS.items()],
            "",
            f"Full run artifact: `{run_result.get('json_path', '')}`",
        ]
    )

    OWNER_DAILY_PREDICT_EVAL_REPORT.write_text("\n".join(lines), encoding="utf-8")
    return OWNER_DAILY_PREDICT_EVAL_REPORT


def _can_predict(predictions: dict[str, Any], discovery: dict[str, Any]) -> str:
    fc = int(discovery.get("fixture_count") or 0)
    if fc == 0:
        return "No — no fixtures today"
    rows = predictions.get("predictions") or []
    wde = sum(1 for r in rows if r.get("wde"))
    if wde == 0:
        return "No — generate/load WDE predictions first"
    if wde < fc:
        return f"Partial — {wde}/{fc} fixtures have WDE"
    return "Yes — owner predictions loaded"


def _yesterday(yesterday: dict[str, Any]) -> str:
    total = int(yesterday.get("fixture_count") or 0)
    ev = int(yesterday.get("evaluated_count") or 0)
    waiting = int(yesterday.get("waiting_result_count") or 0)
    if total == 0:
        return "N/A — no predicted fixtures yesterday"
    if ev == total:
        return f"Yes — {ev}/{total} evaluated"
    if ev > 0:
        return f"Partial — {ev} evaluated, {waiting} waiting"
    return f"No — {waiting} fixtures waiting for final results"


def _prediction_status(predictions: dict[str, Any], discovery: dict[str, Any]) -> str:
    fc = int(discovery.get("fixture_count") or 0)
    if fc == 0:
        return "no_fixtures"
    rows = predictions.get("predictions") or []
    wde = sum(1 for r in rows if r.get("wde"))
    if wde == 0:
        return "missing_predictions"
    if wde < fc:
        return f"partial_{wde}_of_{fc}"
    return "ready"
