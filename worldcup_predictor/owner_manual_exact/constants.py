"""Owner manual exact-score prediction — constants (internal only)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

PHASE = "OWNER-MANUAL-EXACT-SCORE"
DEFAULT_TIMEZONE = "Europe/Vienna"

ARTIFACTS_DIR = Path("artifacts")
REPORTS_DIR = Path("reports") / "owner"
FINAL_REPORT = Path("MANUAL_OWNER_EXACT_SCORE_PREDICTION_REPORT.md")

SAFETY_LABELS: dict[str, bool] = {
    "PUBLIC_PUBLISH": False,
    "WDE_RETRAINED": False,
    "HISTORICAL_CSV_PROMOTED": False,
    "ODDALERTS_ECSE_PRODUCTION": False,
    "ODDALERTS_ECSE_SHADOW_ONLY": True,
}


def with_safety_labels(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, **SAFETY_LABELS}
