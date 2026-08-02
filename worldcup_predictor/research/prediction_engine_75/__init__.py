"""Prediction Engine 75% research program (Phase 1–3)."""

from worldcup_predictor.research.prediction_engine_75.phase1 import (
    STATUS_BLOCKED,
    STATUS_READY,
    run_phase1,
)
from worldcup_predictor.research.prediction_engine_75.phase2 import (
    STATUS_COMPLETE as PHASE2_COMPLETE,
    STATUS_PARTIAL as PHASE2_PARTIAL,
    run_phase2,
)
from worldcup_predictor.research.prediction_engine_75.phase3 import (
    STATUS_COMPLETE as PHASE3_COMPLETE,
    STATUS_LIMITED as PHASE3_LIMITED,
    run_phase3,
)

__all__ = [
    "STATUS_BLOCKED",
    "STATUS_READY",
    "PHASE2_COMPLETE",
    "PHASE2_PARTIAL",
    "PHASE3_COMPLETE",
    "PHASE3_LIMITED",
    "run_phase1",
    "run_phase2",
    "run_phase3",
]
