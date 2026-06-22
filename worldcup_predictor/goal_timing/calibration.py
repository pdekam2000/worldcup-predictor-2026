"""Calibration layer for goal timing probabilities."""

from __future__ import annotations

from typing import Any


class GoalTimingCalibrator:
    def calibrate(self, raw: dict[str, Any]) -> dict[str, Any]:
        out = dict(raw)
        raw_conf = float(raw.get("raw_confidence") or 0.4)
        out["calibrated_confidence"] = round(min(0.95, max(0.05, raw_conf)), 4)
        return out
