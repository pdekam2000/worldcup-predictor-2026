"""Phase 56A — Market Behavior Intelligence models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

MBIMarketKey = Literal[
    "match_winner",
    "first_team_to_score",
    "anytime_goalscorer",
    "first_goalscorer",
    "over_under",
]

MBIRecommendation = Literal["MBI_HIGH_VALUE", "MBI_MEDIUM_VALUE", "MBI_NO_VALUE"]

VALID_RECOMMENDATIONS: frozenset[str] = frozenset(
    {"MBI_HIGH_VALUE", "MBI_MEDIUM_VALUE", "MBI_NO_VALUE"}
)

TARGET_MARKETS: tuple[str, ...] = (
    "match_winner",
    "first_team_to_score",
    "anytime_goalscorer",
    "first_goalscorer",
    "over_under",
)

MIN_SAMPLE_WEAK = 15
MIN_SAMPLE_BIAS = 30
MIN_SAMPLE_STRONG = 50

PRIOR_WEIGHTS: tuple[float, ...] = (0.0, 0.01, 0.05, 0.10)


def odds_bucket_edges() -> list[tuple[float, float, str]]:
    """Decimal odds buckets from 1.10 upward in 0.10 steps."""
    buckets: list[tuple[float, float, str]] = []
    start = 1.10
    while start < 11.0:
        end = round(start + 0.10, 2)
        buckets.append((start, end, f"{start:.2f}-{end:.2f}"))
        start = end
    buckets.append((11.0, float("inf"), "11.00+"))
    return buckets


def assign_odds_bucket(odds: float) -> str | None:
    if odds < 1.10:
        return None
    for low, high, label in odds_bucket_edges():
        if low <= odds < high:
            return label
    return "11.00+"


@dataclass
class OddsSelection:
    source: str
    fixture_key: str
    market_key: str
    selection: str
    odds: float
    bookmaker: str
    league: str | None = None
    season: int | None = None
    implied_probability: float | None = None
    bucket: str | None = None
    hit: bool | None = None
    outcome_label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "fixture_key": self.fixture_key,
            "market_key": self.market_key,
            "selection": self.selection,
            "odds": self.odds,
            "bookmaker": self.bookmaker,
            "league": self.league,
            "season": self.season,
            "implied_probability": self.implied_probability,
            "bucket": self.bucket,
            "hit": self.hit,
            "outcome_label": self.outcome_label,
        }


@dataclass
class BucketStats:
    market_key: str
    bucket: str
    selection: str
    count: int
    hit_rate: float
    implied_mean: float
    calibration_gap: float
    overperformance: float
    underperformance: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_key": self.market_key,
            "bucket": self.bucket,
            "selection": self.selection,
            "count": self.count,
            "hit_rate": self.hit_rate,
            "implied_mean": self.implied_mean,
            "calibration_gap": self.calibration_gap,
            "overperformance": self.overperformance,
            "underperformance": self.underperformance,
        }


@dataclass
class InventorySummary:
    sources: list[dict[str, Any]] = field(default_factory=list)
    total_snapshot_rows: int = 0
    total_selections: int = 0
    markets: dict[str, int] = field(default_factory=dict)
    bookmakers: dict[str, int] = field(default_factory=dict)
    seasons: dict[str, int] = field(default_factory=dict)
    leagues: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sources": self.sources,
            "total_snapshot_rows": self.total_snapshot_rows,
            "total_selections": self.total_selections,
            "markets": self.markets,
            "bookmakers": self.bookmakers,
            "seasons": self.seasons,
            "leagues": self.leagues,
        }
