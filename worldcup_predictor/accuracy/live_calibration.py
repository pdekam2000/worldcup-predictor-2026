"""Conservative live calibration from recent recalibration report — never raises confidence from small samples."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_CONFIG_PATH = Path("reports/calibration/recent_live_calibration.json")
_CACHE: dict[str, Any] | None = None


@dataclass(frozen=True)
class LiveCalibrationConfig:
    active: bool = False
    verified_sample: int = 0
    sample_adequate: bool = False
    confidence_correction_factor: float = 1.0
    max_confidence_cap: float | None = None
    draw_market_threshold: float = 0.28
    balanced_edge_max: float = 0.025
    ou_goal_threshold_adjustment: float = 0.0
    scoreline_probability_cap: float = 0.40
    fusion_low_diversity_extra_penalty: float = 0.0


def load_live_calibration_config(*, reload: bool = False) -> LiveCalibrationConfig:
    global _CACHE
    if not reload and _CACHE is not None:
        return _config_from_dict(_CACHE)
    if not _CONFIG_PATH.is_file():
        return LiveCalibrationConfig()
    try:
        _CACHE = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        _CACHE = {}
    return _config_from_dict(_CACHE or {})


def _config_from_dict(data: dict[str, Any]) -> LiveCalibrationConfig:
    if not data.get("active"):
        return LiveCalibrationConfig()
    factor = float(data.get("confidence_correction_factor") or 1.0)
    factor = min(1.0, factor)
    cap = data.get("max_confidence_cap")
    return LiveCalibrationConfig(
        active=True,
        verified_sample=int(data.get("verified_sample") or 0),
        sample_adequate=bool(data.get("sample_adequate")),
        confidence_correction_factor=factor,
        max_confidence_cap=float(cap) if cap is not None else None,
        draw_market_threshold=float(data.get("draw_market_threshold") or 0.28),
        balanced_edge_max=float(data.get("balanced_edge_max") or 0.025),
        ou_goal_threshold_adjustment=float(data.get("ou_goal_threshold_adjustment") or 0.0),
        scoreline_probability_cap=float(data.get("scoreline_probability_cap") or 0.40),
        fusion_low_diversity_extra_penalty=float(
            data.get("fusion_low_diversity_extra_penalty") or 0.0
        ),
    )


def apply_confidence_correction(score: float, *, config: LiveCalibrationConfig | None = None) -> float:
    """Reduce confidence when recent verified accuracy underperforms — never auto-boost."""
    cfg = config or load_live_calibration_config()
    if not cfg.active or cfg.confidence_correction_factor >= 1.0:
        adjusted = score
    else:
        adjusted = score * cfg.confidence_correction_factor
    if cfg.max_confidence_cap is not None:
        adjusted = min(adjusted, cfg.max_confidence_cap)
    return round(max(0.0, min(100.0, adjusted)), 1)


def apply_scoreline_cap(probability: float, *, config: LiveCalibrationConfig | None = None) -> float:
    cfg = config or load_live_calibration_config()
    if not cfg.active:
        return probability
    return min(probability, cfg.scoreline_probability_cap)


def fusion_diversity_penalty(diversity_score: float, base_adj: float) -> float:
    cfg = load_live_calibration_config()
    if not cfg.active or cfg.fusion_low_diversity_extra_penalty <= 0:
        return base_adj
    if diversity_score < 40:
        return base_adj - cfg.fusion_low_diversity_extra_penalty
    return base_adj


def ou_expected_goals_threshold(base: float = 2.5) -> float:
    cfg = load_live_calibration_config()
    if not cfg.active:
        return base
    return base + cfg.ou_goal_threshold_adjustment


def should_prefer_draw(
    home_edge_total: float,
    *,
    draw_implied_probability: float | None,
    config: LiveCalibrationConfig | None = None,
) -> bool:
    cfg = config or load_live_calibration_config()
    if not cfg.active:
        return False
    if abs(home_edge_total) > cfg.balanced_edge_max:
        return False
    if draw_implied_probability is None:
        return False
    return float(draw_implied_probability) >= cfg.draw_market_threshold
