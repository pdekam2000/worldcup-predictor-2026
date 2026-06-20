from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

OddsPrimaryMode = Literal["off", "shadow"]


@dataclass
class OddsPrimaryResult:
    lambda_home: float
    lambda_away: float
    lambda_source: str
    odds_lambda_home: float | None = None
    odds_lambda_away: float | None = None
    xg_lambda_home: float | None = None
    xg_lambda_away: float | None = None
    stats_nudge_home: float = 0.0
    stats_nudge_away: float = 0.0
    odds_available: bool = False
    xg_available: bool = False
    used_production_fallback: bool = False
    blend_weights: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def spread(self) -> float:
        return abs(self.lambda_home - self.lambda_away)

    def to_dict(self) -> dict[str, Any]:
        return {
            "lambda_home": round(self.lambda_home, 4),
            "lambda_away": round(self.lambda_away, 4),
            "lambda_source": self.lambda_source,
            "spread": round(self.spread, 4),
            "odds_lambda_home": self.odds_lambda_home,
            "odds_lambda_away": self.odds_lambda_away,
            "xg_lambda_home": self.xg_lambda_home,
            "xg_lambda_away": self.xg_lambda_away,
            "stats_nudge_home": round(self.stats_nudge_home, 4),
            "stats_nudge_away": round(self.stats_nudge_away, 4),
            "odds_available": self.odds_available,
            "xg_available": self.xg_available,
            "used_production_fallback": self.used_production_fallback,
            "blend_weights": self.blend_weights,
            "notes": self.notes,
        }
