"""Adaptive confidence dataclasses — learning-informed, separate from data quality."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

CalibrationLabel = Literal["Excellent", "Good", "Fair", "Limited", "—"]


@dataclass
class AdaptiveConfidenceAdjustment:
    """Learning-based confidence layer applied after base prediction scoring."""

    base_confidence: float
    final_confidence: float
    total_bonus: float
    pattern_bonus: float
    competition_bonus: float
    similar_situation_bonus: float
    bucket_bonus: float
    reason: str
    similar_sample_size: int = 0
    similar_winrate: float | None = None
    base_prediction_quality: float = 0.0
    final_prediction_quality: float = 0.0
    matched_pattern_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ModelExperienceSummary:
    """Aggregate learning memory for dashboard display."""

    verified_matches: int = 0
    patterns_learned: int = 0
    confidence_calibration: CalibrationLabel = "—"
    baseline_winrate: float | None = None
    total_learning_rows: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
