"""Central thresholds for the market consistency guard (Phase 42B-FIX)."""

from __future__ import annotations

import os
from typing import Any

# --- Default numeric thresholds (probability scale 0.0–1.0 unless noted) ---

_DEFAULT_BTTS_NO = 0.70
_DEFAULT_BTTS_YES = 0.70
_DEFAULT_UNDER25 = 0.70
_DEFAULT_UNDER15 = 0.70
_DEFAULT_OVER25 = 0.70
_DEFAULT_LOW_TEAM_SCORING = 0.35
_DEFAULT_STRONG_GOALSCORER_CONFIDENCE = 0.72
_DEFAULT_BTTS_YES_CLEAN_SHEET_SCORE_PROB = 0.25
_DEFAULT_DRAW_SCORING_SHARE = 0.45
_DEFAULT_POISSON_LAMBDA_FLOOR = 0.05
_DEFAULT_EARLY_EXPECTED_MINUTE_MAX = 35

_DEFAULT_EARLY_MINUTE_BANDS = frozenset({"0-15", "16-30", "0_15", "16_30"})


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


CONSISTENCY_BTTS_NO_THRESHOLD: float = _env_float("WCP_CONSISTENCY_BTTS_NO_THRESHOLD", _DEFAULT_BTTS_NO)
CONSISTENCY_BTTS_YES_THRESHOLD: float = _env_float("WCP_CONSISTENCY_BTTS_YES_THRESHOLD", _DEFAULT_BTTS_YES)
CONSISTENCY_UNDER25_THRESHOLD: float = _env_float("WCP_CONSISTENCY_UNDER25_THRESHOLD", _DEFAULT_UNDER25)
CONSISTENCY_OVER25_THRESHOLD: float = _env_float("WCP_CONSISTENCY_OVER25_THRESHOLD", _DEFAULT_OVER25)
CONSISTENCY_UNDER15_THRESHOLD: float = _env_float("WCP_CONSISTENCY_UNDER15_THRESHOLD", _DEFAULT_UNDER15)
CONSISTENCY_LOW_TEAM_SCORING_PROB_THRESHOLD: float = _env_float(
    "WCP_CONSISTENCY_LOW_TEAM_SCORING_PROB_THRESHOLD",
    _DEFAULT_LOW_TEAM_SCORING,
)
CONSISTENCY_STRONG_GOALSCORER_CONFIDENCE: float = _env_float(
    "WCP_CONSISTENCY_STRONG_GOALSCORER_CONFIDENCE",
    _DEFAULT_STRONG_GOALSCORER_CONFIDENCE,
)
CONSISTENCY_BTTS_YES_CLEAN_SHEET_SCORE_PROB_WITHHOLD: float = _env_float(
    "WCP_CONSISTENCY_BTTS_YES_CLEAN_SHEET_SCORE_PROB_WITHHOLD",
    _DEFAULT_BTTS_YES_CLEAN_SHEET_SCORE_PROB,
)
CONSISTENCY_DRAW_SCORING_SHARE: float = _env_float(
    "WCP_CONSISTENCY_DRAW_SCORING_SHARE",
    _DEFAULT_DRAW_SCORING_SHARE,
)
CONSISTENCY_POISSON_LAMBDA_FLOOR: float = _env_float(
    "WCP_CONSISTENCY_POISSON_LAMBDA_FLOOR",
    _DEFAULT_POISSON_LAMBDA_FLOOR,
)
CONSISTENCY_EARLY_EXPECTED_MINUTE_MAX: int = _env_int(
    "WCP_CONSISTENCY_EARLY_EXPECTED_MINUTE_MAX",
    _DEFAULT_EARLY_EXPECTED_MINUTE_MAX,
)

CONSISTENCY_EARLY_MINUTE_BANDS: frozenset[str] = _DEFAULT_EARLY_MINUTE_BANDS

CONSISTENCY_RULES_VERSION = "42b-fix-final-v1"

WITHHELD_USER_MESSAGE = (
    "This market was withheld because it conflicts with stronger model signals."
)


def get_consistency_thresholds() -> dict[str, Any]:
    """Snapshot of active thresholds for validation / audit."""
    return {
        "btts_no_threshold": CONSISTENCY_BTTS_NO_THRESHOLD,
        "btts_yes_threshold": CONSISTENCY_BTTS_YES_THRESHOLD,
        "under25_threshold": CONSISTENCY_UNDER25_THRESHOLD,
        "over25_threshold": CONSISTENCY_OVER25_THRESHOLD,
        "under15_threshold": CONSISTENCY_UNDER15_THRESHOLD,
        "low_team_scoring_prob_threshold": CONSISTENCY_LOW_TEAM_SCORING_PROB_THRESHOLD,
        "strong_goalscorer_confidence": CONSISTENCY_STRONG_GOALSCORER_CONFIDENCE,
        "btts_yes_clean_sheet_score_prob_withhold": CONSISTENCY_BTTS_YES_CLEAN_SHEET_SCORE_PROB_WITHHOLD,
        "draw_scoring_share": CONSISTENCY_DRAW_SCORING_SHARE,
        "poisson_lambda_floor": CONSISTENCY_POISSON_LAMBDA_FLOOR,
        "early_expected_minute_max": CONSISTENCY_EARLY_EXPECTED_MINUTE_MAX,
        "early_minute_bands": sorted(CONSISTENCY_EARLY_MINUTE_BANDS),
        "rules_version": CONSISTENCY_RULES_VERSION,
    }
