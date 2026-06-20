from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

LambdaBridgeMode = Literal["off", "shadow", "limited", "full"]


@dataclass
class SpecialistLambdaContribution:
    agent_name: str
    delta_home: float = 0.0
    delta_away: float = 0.0
    included: bool = True
    exclusion_reason: str | None = None
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "delta_home": round(self.delta_home, 4),
            "delta_away": round(self.delta_away, 4),
            "included": self.included,
            "exclusion_reason": self.exclusion_reason,
            "note": self.note,
        }


@dataclass
class LambdaBridgeResult:
    lambda_base_home: float
    lambda_base_away: float
    lambda_adjusted_home: float
    lambda_adjusted_away: float
    delta_home_total: float
    delta_away_total: float
    contributions: list[SpecialistLambdaContribution] = field(default_factory=list)
    data_quality_pct: float = 0.0
    data_quality_scale: float = 1.0
    confidence_scale: float = 1.0
    global_cap_applied: bool = False
    global_cap_pre_home: float = 0.0
    global_cap_pre_away: float = 0.0
    config_version: str = "12b-v1"
    mode: LambdaBridgeMode = "shadow"
    error: str | None = None

    @classmethod
    def fallback(
        cls,
        lambda_home: float,
        lambda_away: float,
        *,
        mode: LambdaBridgeMode = "off",
        error: str | None = None,
    ) -> LambdaBridgeResult:
        return cls(
            lambda_base_home=lambda_home,
            lambda_base_away=lambda_away,
            lambda_adjusted_home=lambda_home,
            lambda_adjusted_away=lambda_away,
            delta_home_total=0.0,
            delta_away_total=0.0,
            mode=mode,
            error=error,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "lambda_base": {
                "home": round(self.lambda_base_home, 4),
                "away": round(self.lambda_base_away, 4),
            },
            "lambda_adjusted": {
                "home": round(self.lambda_adjusted_home, 4),
                "away": round(self.lambda_adjusted_away, 4),
            },
            "delta_total": {
                "home": round(self.delta_home_total, 4),
                "away": round(self.delta_away_total, 4),
            },
            "contributions": [c.to_dict() for c in self.contributions],
            "data_quality_pct": self.data_quality_pct,
            "data_quality_scale": round(self.data_quality_scale, 4),
            "confidence_scale": round(self.confidence_scale, 4),
            "global_cap_applied": self.global_cap_applied,
            "config_version": self.config_version,
            "mode": self.mode,
            "error": self.error,
        }
