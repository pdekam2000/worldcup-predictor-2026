"""Performance certification for autonomous engines — Phase 61."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from worldcup_predictor.autonomous.store import AutonomousStore
from worldcup_predictor.config.settings import Settings, get_settings

CertificationLevel = Literal["PRODUCTION_READY", "PAPER_READY", "RESEARCH_ONLY", "BLOCKED"]

MARKETS = (
    "1x2",
    "double_chance",
    "btts",
    "over_under_2_5",
    "correct_score",
    "goal_timing",
    "first_goal_team",
    "team_to_score_first",
    "goalscorer",
)

ENGINES = ("production", "elite_shadow")
ROLLING_WINDOWS = (7, 30, 90)

# Conservative thresholds
THRESHOLDS = {
    "PRODUCTION_READY": {"min_evaluated": 30, "min_winrate": 0.52},
    "PAPER_READY": {"min_evaluated": 15, "min_winrate": 0.48},
    "RESEARCH_ONLY": {"min_evaluated": 5, "min_winrate": 0.0},
}


@dataclass
class PerformanceCertificationResult:
    generated_at: str = ""
    engines: dict[str, Any] = field(default_factory=dict)
    markets: dict[str, Any] = field(default_factory=dict)
    rolling: dict[str, Any] = field(default_factory=dict)
    overall: dict[str, Any] = field(default_factory=dict)
    certification_levels: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "engines": self.engines,
            "markets": self.markets,
            "rolling": self.rolling,
            "overall": self.overall,
            "certification_levels": self.certification_levels,
        }


def _certify(metrics: dict[str, Any]) -> CertificationLevel:
    evaluated = int(metrics.get("evaluated") or 0)
    winrate = metrics.get("winrate")
    if evaluated < THRESHOLDS["RESEARCH_ONLY"]["min_evaluated"]:
        return "BLOCKED"
    if winrate is None:
        return "RESEARCH_ONLY"
    if evaluated >= THRESHOLDS["PRODUCTION_READY"]["min_evaluated"] and winrate >= THRESHOLDS["PRODUCTION_READY"]["min_winrate"]:
        return "PRODUCTION_READY"
    if evaluated >= THRESHOLDS["PAPER_READY"]["min_evaluated"] and winrate >= THRESHOLDS["PAPER_READY"]["min_winrate"]:
        return "PAPER_READY"
    if evaluated >= THRESHOLDS["RESEARCH_ONLY"]["min_evaluated"]:
        return "RESEARCH_ONLY"
    return "BLOCKED"


def run_performance_certification(
    *,
    settings: Settings | None = None,
) -> PerformanceCertificationResult:
    from datetime import datetime, timezone

    settings = settings or get_settings()
    store = AutonomousStore(settings)
    result = PerformanceCertificationResult(
        generated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )

    for engine in ENGINES:
        agg = store.aggregate_performance(engine=engine)
        agg["certification"] = _certify(agg)
        result.engines[engine] = agg
        result.certification_levels[f"engine:{engine}"] = agg["certification"]

    for market in MARKETS:
        market_stats: dict[str, Any] = {}
        for engine in ENGINES:
            agg = store.aggregate_performance(engine=engine, market_id=market)
            agg["certification"] = _certify(agg)
            market_stats[engine] = agg
            result.certification_levels[f"{engine}:{market}"] = agg["certification"]
        result.markets[market] = market_stats

    for days in ROLLING_WINDOWS:
        rolling: dict[str, Any] = {}
        for engine in ENGINES:
            rolling[engine] = store.aggregate_performance(engine=engine, rolling_days=days)
        result.rolling[f"{days}d"] = rolling

    prod = result.engines.get("production") or {}
    elite = result.engines.get("elite_shadow") or {}
    result.overall = {
        "production_evaluated": prod.get("evaluated", 0),
        "production_winrate": prod.get("winrate"),
        "elite_evaluated": elite.get("evaluated", 0),
        "elite_winrate": elite.get("winrate"),
        "production_certification": prod.get("certification", "BLOCKED"),
        "elite_certification": elite.get("certification", "BLOCKED"),
        "thresholds": THRESHOLDS,
        "coverage": {
            "markets_tracked": list(MARKETS),
            "engines_tracked": list(ENGINES),
        },
    }

    report = result.to_dict()
    store.save_certification_report(report)
    return result
