from __future__ import annotations

from pathlib import Path
from typing import Any

# Factor weights as fractions summing to 1.0 (matches WeightedDecisionEngine defaults).
DEFAULT_FACTOR_WEIGHTS: dict[str, float] = {
    "data_quality": 0.15,
    "team_form": 0.15,
    "injuries_suspensions": 0.12,
    "lineup_strength": 0.12,
    "tactics_matchup": 0.12,
    "player_quality": 0.10,
    "odds_market_signal": 0.10,
    "motivation_psychology": 0.08,
    "weather_referee_context": 0.06,
}

# Populated after successful calibration run (also loaded from reports/calibration/).
CALIBRATED_FACTOR_WEIGHTS: dict[str, float] | None = None

DEFAULT_THRESHOLDS: dict[str, float] = {
    "analysis_ready_confidence_minimum": 60.0,
    "no_bet_confidence_minimum": 60.0,
    "data_quality_confidence_cap_below": 50.0,
    "data_quality_cap_value": 45.0,
    "data_quality_no_bet_threshold": 50.0,
    "missing_lineups_first_goal_cap": 30.0,
    "specialist_conflict_penalty_per_conflict": 4.0,
    "specialist_conflict_penalty_max": 12.0,
    "specialist_conflict_high_count": 2.0,
    "odds_disagreement_penalty": 5.0,
    "severe_weather_over_penalty": 15.0,
    "high_confidence_level_minimum": 70.0,
    "medium_confidence_level_minimum": 50.0,
}

CALIBRATED_THRESHOLDS: dict[str, float] | None = None

CALIBRATION_REPORT_DIR = Path("reports/calibration")
CALIBRATED_WEIGHTS_FILE = CALIBRATION_REPORT_DIR / "calibrated_weights.json"
CALIBRATED_THRESHOLDS_FILE = CALIBRATION_REPORT_DIR / "calibrated_thresholds.json"

MARKET_FACTOR_PRIORITIES: dict[str, list[str]] = {
    "1x2": ["team_form", "odds_market_signal", "motivation_psychology", "player_quality", "injuries_suspensions"],
    "over_under": ["tactics_matchup", "weather_referee_context", "odds_market_signal", "team_form"],
    "halftime": ["tactics_matchup", "team_form", "lineup_strength", "weather_referee_context"],
}


def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    if total <= 0:
        return get_factor_weights(use_calibrated=False)
    return {key: round(value / total, 4) for key, value in weights.items()}


def get_factor_weights(*, use_calibrated: bool = True) -> dict[str, float]:
    if use_calibrated:
        if CALIBRATED_FACTOR_WEIGHTS:
            return dict(CALIBRATED_FACTOR_WEIGHTS)
        loaded = _load_json_weights(CALIBRATED_WEIGHTS_FILE)
        if loaded:
            return loaded
    return dict(DEFAULT_FACTOR_WEIGHTS)


def get_thresholds(*, use_calibrated: bool = True) -> dict[str, float]:
    if use_calibrated:
        if CALIBRATED_THRESHOLDS:
            return dict(CALIBRATED_THRESHOLDS)
        loaded = _load_json_thresholds(CALIBRATED_THRESHOLDS_FILE)
        if loaded:
            return loaded
    return dict(DEFAULT_THRESHOLDS)


def apply_calibrated(
    factor_weights: dict[str, float] | None = None,
    thresholds: dict[str, float] | None = None,
    *,
    persist: bool = True,
) -> None:
    """Apply calibrated values in-process and optionally persist to reports/calibration/."""
    global CALIBRATED_FACTOR_WEIGHTS, CALIBRATED_THRESHOLDS

    if factor_weights is not None:
        normalized = normalize_weights(factor_weights)
        CALIBRATED_FACTOR_WEIGHTS = normalized
        if persist:
            _write_json(CALIBRATED_WEIGHTS_FILE, normalized)

    if thresholds is not None:
        merged = {**DEFAULT_THRESHOLDS, **thresholds}
        CALIBRATED_THRESHOLDS = merged
        if persist:
            _write_json(CALIBRATED_THRESHOLDS_FILE, merged)


def _load_json_weights(path: Path) -> dict[str, float] | None:
    data = _read_json(path)
    if not data:
        return None
    return normalize_weights({str(k): float(v) for k, v in data.items()})


def _load_json_thresholds(path: Path) -> dict[str, float] | None:
    data = _read_json(path)
    if not data:
        return None
    return {**DEFAULT_THRESHOLDS, **{str(k): float(v) for k, v in data.items()}}


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        import json

        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _write_json(path: Path, payload: dict[str, float]) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
