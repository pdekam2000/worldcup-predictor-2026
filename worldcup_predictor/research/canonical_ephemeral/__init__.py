"""CANONICAL_RESEARCH_EPHEMERAL — internal research-only prediction facade."""

from worldcup_predictor.research.canonical_ephemeral.constants import EXECUTION_MODE
from worldcup_predictor.research.canonical_ephemeral.write_guard import (
    EphemeralWriteBlocked,
    ephemeral_mode_active,
    ephemeral_write_guard,
)

__all__ = [
    "EXECUTION_MODE",
    "EphemeralCanonicalPrediction",
    "EphemeralWriteBlocked",
    "ResearchContext",
    "ephemeral_mode_active",
    "ephemeral_prediction_to_timing_payload",
    "ephemeral_write_guard",
    "run_ephemeral_canonical_prediction",
]


def __getattr__(name: str):
    if name in {"run_ephemeral_canonical_prediction", "ephemeral_prediction_to_timing_payload"}:
        from worldcup_predictor.research.canonical_ephemeral import facade

        return getattr(facade, name)
    if name in {"EphemeralCanonicalPrediction", "ResearchContext"}:
        from worldcup_predictor.research.canonical_ephemeral import types

        return getattr(types, name)
    raise AttributeError(name)
