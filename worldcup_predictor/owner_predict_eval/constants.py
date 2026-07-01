"""PHASE OWNER-DAILY-PREDICT-EVAL-4 — Owner daily prediction + evaluation constants."""

from __future__ import annotations

from pathlib import Path
from typing import Any

PHASE = "OWNER-DAILY-PREDICT-EVAL-4"

SUPPORTED_DATE_FORMATS = "today, now, yesterday, tomorrow, or YYYY-MM-DD"
DEFAULT_TIMEZONE = "Europe/Vienna"

REPORTS_DIR = Path("reports") / "owner"
ARTIFACTS_DIR = Path("artifacts")

OWNER_DAILY_PREDICT_EVAL_REPORT = Path("OWNER_DAILY_PREDICTION_EVAL_STATUS_REPORT.md")

StatusRecommendation = str

SAFETY_LABELS: dict[str, bool] = {
    "PUBLIC_PUBLISH": False,
    "WDE_RETRAINED": False,
    "HISTORICAL_CSV_PROMOTED": False,
    "ODDALERTS_ECSE_PRODUCTION": False,
    "ODDALERTS_ECSE_SHADOW_ONLY": True,
}


def with_safety_labels(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, **SAFETY_LABELS}


def safety_labels_markdown() -> list[str]:
    return [
        "## Safety labels",
        "",
        *[f"- **{key}:** `{value}`" for key, value in SAFETY_LABELS.items()],
        "",
    ]
