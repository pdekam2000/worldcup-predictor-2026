from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

MarketResult = Literal["correct", "wrong", "unavailable"]
MarketColor = Literal["green", "red", "gray"]


@dataclass
class VerificationMarketRecord:
    fixture_id: int
    prediction_id: str
    market: str
    match_name: str
    home_team: str
    away_team: str
    final_score: str | None
    predicted: str
    actual: str
    result: MarketResult
    color: MarketColor
    verified_at: str
    prediction_created_at: str = ""

    def dedupe_key(self) -> tuple[int, str, str]:
        return (self.fixture_id, self.prediction_id, self.market)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VerificationMarketRecord:
        return cls(
            fixture_id=int(data["fixture_id"]),
            prediction_id=str(data["prediction_id"]),
            market=str(data["market"]),
            match_name=str(data["match_name"]),
            home_team=str(data["home_team"]),
            away_team=str(data["away_team"]),
            final_score=data.get("final_score"),
            predicted=str(data["predicted"]),
            actual=str(data["actual"]),
            result=data["result"],  # type: ignore[arg-type]
            color=data["color"],  # type: ignore[arg-type]
            verified_at=str(data["verified_at"]),
            prediction_created_at=str(data.get("prediction_created_at", "")),
        )


@dataclass
class MatchVerificationSummary:
    fixture_id: int
    prediction_id: str
    match_name: str
    final_score: str
    home_team: str
    away_team: str
    markets: list[VerificationMarketRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "prediction_id": self.prediction_id,
            "match_name": self.match_name,
            "final_score": self.final_score,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "markets": [m.to_dict() for m in self.markets],
        }


@dataclass
class VerificationSummaryMetrics:
    total_predictions_checked: int = 0
    evaluated_matches: int = 0
    pending_matches: int = 0
    total_market_rows: int = 0
    one_x_two_winrate: float | None = None
    over_under_winrate: float | None = None
    halftime_bucket_winrate: float | None = None
    scoreline_winrate: float | None = None
    first_goal_team_winrate: float | None = None
    first_goal_scorer_winrate: float | None = None
    model_grade: str = "—"
    strongest_market: str | None = None
    weakest_market: str | None = None
    disclaimer: str = (
        "Automated model verification compares stored predictions with finished results. "
        "Historical accuracy does not guarantee future outcomes — not profit or betting advice."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
