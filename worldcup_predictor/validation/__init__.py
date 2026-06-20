"""Phase 26 — real-world validation framework."""

from worldcup_predictor.validation.capture import (
    build_validation_record,
    maybe_record_real_world_validation,
)
from worldcup_predictor.validation.models import RealWorldValidationRecord, WorldCupReadinessScore
from worldcup_predictor.validation.service import RealWorldValidationService

__all__ = [
    "RealWorldValidationRecord",
    "RealWorldValidationService",
    "WorldCupReadinessScore",
    "build_validation_record",
    "maybe_record_real_world_validation",
]
