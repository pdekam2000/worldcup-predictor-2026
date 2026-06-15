from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

DEFAULT_DISCLAIMER = (
    "Model coach recommendations are for calibration and learning only. "
    "Historical performance does not guarantee future results — not profit or betting advice."
)

APPLY_RECOMMENDATIONS_AFTER_USER_APPROVAL = False


@dataclass
class ModelCoachReport:
    strongest_market: str | None = None
    weakest_market: str | None = None
    market_specific_recommendations: dict[str, list[str]] = field(default_factory=dict)
    competition_specific_recommendations: dict[str, list[str]] = field(default_factory=dict)
    recommended_weight_adjustments: dict[str, str] = field(default_factory=dict)
    recommended_confidence_thresholds: dict[str, str] = field(default_factory=dict)
    recommended_market_rules: list[str] = field(default_factory=list)
    recommended_selection_rules: list[str] = field(default_factory=list)
    warnings_about_small_sample_size: list[str] = field(default_factory=list)
    sample_size_warning: str = ""
    suggested_focus_area: str = ""
    decision_agent_advice: list[str] = field(default_factory=list)
    apply_recommendations_after_user_approval: bool = APPLY_RECOMMENDATIONS_AFTER_USER_APPROVAL
    competition_key: str | None = None
    competition_winrates: dict[str, dict[str, float | None]] = field(default_factory=dict)
    market_winrates: dict[str, float | None] = field(default_factory=dict)
    confidence_bucket_performance: list[dict[str, Any]] = field(default_factory=list)
    mistakes_by_market: dict[str, int] = field(default_factory=dict)
    mistakes_by_data_quality_level: dict[str, dict[str, Any]] = field(default_factory=dict)
    mistakes_by_competition: dict[str, dict[str, Any]] = field(default_factory=dict)
    mistakes_by_prediction_version: dict[str, dict[str, Any]] = field(default_factory=dict)
    factors_in_correct_predictions: dict[str, float] = field(default_factory=dict)
    factors_in_wrong_predictions: dict[str, float] = field(default_factory=dict)
    evaluated_matches: int = 0
    total_market_rows: int = 0
    generated_at_utc: str = ""
    disclaimer: str = DEFAULT_DISCLAIMER

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelCoachReport:
        return cls(
            strongest_market=data.get("strongest_market"),
            weakest_market=data.get("weakest_market"),
            market_specific_recommendations=dict(data.get("market_specific_recommendations") or {}),
            competition_specific_recommendations=dict(data.get("competition_specific_recommendations") or {}),
            recommended_weight_adjustments=dict(data.get("recommended_weight_adjustments") or {}),
            recommended_confidence_thresholds=dict(data.get("recommended_confidence_thresholds") or {}),
            recommended_market_rules=list(data.get("recommended_market_rules") or []),
            recommended_selection_rules=list(data.get("recommended_selection_rules") or []),
            warnings_about_small_sample_size=list(data.get("warnings_about_small_sample_size") or []),
            sample_size_warning=str(data.get("sample_size_warning") or ""),
            suggested_focus_area=str(data.get("suggested_focus_area") or ""),
            decision_agent_advice=list(data.get("decision_agent_advice") or []),
            apply_recommendations_after_user_approval=bool(
                data.get("apply_recommendations_after_user_approval", APPLY_RECOMMENDATIONS_AFTER_USER_APPROVAL)
            ),
            competition_key=data.get("competition_key"),
            competition_winrates=dict(data.get("competition_winrates") or {}),
            market_winrates=dict(data.get("market_winrates") or {}),
            confidence_bucket_performance=list(data.get("confidence_bucket_performance") or []),
            mistakes_by_market=dict(data.get("mistakes_by_market") or {}),
            mistakes_by_data_quality_level=dict(data.get("mistakes_by_data_quality_level") or {}),
            mistakes_by_competition=dict(data.get("mistakes_by_competition") or {}),
            mistakes_by_prediction_version=dict(data.get("mistakes_by_prediction_version") or {}),
            factors_in_correct_predictions=dict(data.get("factors_in_correct_predictions") or {}),
            factors_in_wrong_predictions=dict(data.get("factors_in_wrong_predictions") or {}),
            evaluated_matches=int(data.get("evaluated_matches", 0)),
            total_market_rows=int(data.get("total_market_rows", 0)),
            generated_at_utc=str(data.get("generated_at_utc") or ""),
            disclaimer=str(data.get("disclaimer") or DEFAULT_DISCLAIMER),
        )
