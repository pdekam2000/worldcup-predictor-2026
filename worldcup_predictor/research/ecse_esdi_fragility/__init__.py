"""ECSE ESDI / Fragility prematch risk research (shadow-only, no selector change)."""

from worldcup_predictor.research.ecse_esdi_fragility.metrics import (
    build_prematch_risk_record,
    esdi_metrics,
    score_features,
)
from worldcup_predictor.research.ecse_esdi_fragility.thresholds import (
    THRESHOLD_VERSION,
    assign_buckets,
    calibrate_thresholds,
)

__all__ = [
    "THRESHOLD_VERSION",
    "assign_buckets",
    "build_prematch_risk_record",
    "calibrate_thresholds",
    "esdi_metrics",
    "score_features",
]
