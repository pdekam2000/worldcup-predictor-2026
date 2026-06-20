"""Specialist → Lambda bridge (Phase 12B shadow simulation)."""

from worldcup_predictor.prediction.lambda_bridge.bridge import SpecialistLambdaBridge
from worldcup_predictor.prediction.lambda_bridge.models import (
    LambdaBridgeMode,
    LambdaBridgeResult,
    SpecialistLambdaContribution,
)

__all__ = [
    "LambdaBridgeMode",
    "LambdaBridgeResult",
    "SpecialistLambdaBridge",
    "SpecialistLambdaContribution",
]
