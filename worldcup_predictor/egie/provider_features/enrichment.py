"""Apply paid-provider signals to EGIE agent outputs for backtest strategies."""

from __future__ import annotations

import copy
from typing import Any, Literal

from worldcup_predictor.goal_timing.models import GoalTimingAgentOutput
from worldcup_predictor.egie.provider_features.models import ProviderFeatureVector

PaidProviderStrategy = Literal["A", "B", "C", "D", "E", "F"]

STRATEGY_LABELS: dict[str, str] = {
    "A": "baseline_current",
    "B": "baseline_plus_xg",
    "C": "baseline_plus_pressure",
    "D": "baseline_plus_odds",
    "E": "baseline_plus_xg_pressure_odds",
    "F": "full_paid_provider",
}


def _clone_outputs(outputs: dict[str, GoalTimingAgentOutput]) -> dict[str, GoalTimingAgentOutput]:
    return {k: GoalTimingAgentOutput(**copy.deepcopy(v.__dict__)) for k, v in outputs.items()}


def _set_pressure(
    outputs: dict[str, GoalTimingAgentOutput],
    *,
    home: float,
    away: float,
    source: str,
) -> None:
    agent = outputs.get("first_goal_pressure")
    if not agent:
        return
    edge = "home" if home > away + 0.02 else "away" if away > home + 0.02 else "neutral"
    agent.signals = {
        **(agent.signals or {}),
        "home_early_pressure": round(home, 4),
        "away_early_pressure": round(away, 4),
        "pressure_edge": edge,
        "paid_provider_source": source,
    }
    agent.impact_score = min(1.0, 0.35 + abs(home - away))
    agent.missing_data = []
    agent.notes = f"Pressure from paid provider ({source})."


def _set_odds(outputs: dict[str, GoalTimingAgentOutput], pf: ProviderFeatureVector) -> None:
    agent = outputs.get("odds_goal_intelligence")
    if not agent:
        return
    home = pf.odds_implied_home
    away = pf.odds_implied_away
    if home is None or away is None:
        return
    agent.signals = {
        **(agent.signals or {}),
        "reliable_odds": True,
        "implied_home": home,
        "implied_away": away,
        "implied_draw": pf.odds_implied_draw,
        "odds_movement_home": pf.odds_movement_home,
        "market_favorite": "home" if home >= away else "away",
    }
    agent.impact_score = min(1.0, 0.4 + abs(home - away))
    agent.missing_data = []
    agent.notes = "Goal-market odds from stored snapshots."


def _set_lineups(outputs: dict[str, GoalTimingAgentOutput], pf: ProviderFeatureVector) -> None:
    agent = outputs.get("lineup_goal_impact")
    if not agent:
        return
    lh = pf.lineup_strength_home
    la = pf.lineup_strength_away
    if lh is None and la is None:
        return
    agent.signals = {
        **(agent.signals or {}),
        "lineups_available": True,
        "lineup_strength_home": lh,
        "lineup_strength_away": la,
        "lineup_edge": "home" if (lh or 0) > (la or 0) else "away",
    }
    agent.impact_score = min(1.0, 0.45 + abs((lh or 0) - (la or 0)))
    agent.missing_data = []
    agent.notes = "Lineup strength from API-Football EGIE raw."


def _set_xg_pattern(outputs: dict[str, GoalTimingAgentOutput], pf: ProviderFeatureVector) -> None:
    agent = outputs.get("goal_timing_pattern")
    if not agent:
        return
    hx = pf.home_xg_for
    ax = pf.away_xg_for
    if hx is None or ax is None:
        return
    agent.signals = {
        **(agent.signals or {}),
        "home_xg_for": hx,
        "away_xg_for": ax,
        "xg_edge": "home" if hx > ax else "away",
    }
    agent.impact_score = min(1.0, 0.4 + abs(hx - ax) * 0.15)
    agent.notes = "xG edge from Sportmonks / stored xG snapshot."


def enrich_agent_outputs(
    outputs: dict[str, GoalTimingAgentOutput],
    provider_features: ProviderFeatureVector | dict[str, Any] | None,
    strategy: PaidProviderStrategy,
) -> dict[str, GoalTimingAgentOutput]:
    """Return agent outputs adjusted per strategy (A = unchanged)."""
    if strategy == "A" or not provider_features:
        return outputs

    pf = (
        provider_features
        if isinstance(provider_features, ProviderFeatureVector)
        else ProviderFeatureVector(**provider_features)
    )
    out = _clone_outputs(outputs)

    use_xg = strategy in ("B", "E", "F")
    use_pressure = strategy in ("C", "E", "F")
    use_odds = strategy in ("D", "E", "F")
    use_full = strategy == "F"

    if use_xg and pf.coverage.get("xg"):
        _set_xg_pattern(out, pf)
        hx = pf.home_xg_for or 0.0
        ax = pf.away_xg_for or 0.0
        total = max(1e-9, hx + ax)
        _set_pressure(out, home=hx / total, away=ax / total, source="xg_share")

    if use_pressure and pf.coverage.get("pressure") and pf.pressure_index_home is not None:
        _set_pressure(
            out,
            home=float(pf.pressure_index_home),
            away=float(pf.pressure_index_away or 0.0),
            source="sportmonks_pressure",
        )

    if use_odds and pf.coverage.get("odds"):
        _set_odds(out, pf)
        if pf.odds_implied_home is not None and pf.odds_implied_away is not None:
            _set_pressure(
                out,
                home=float(pf.odds_implied_home),
                away=float(pf.odds_implied_away),
                source="odds_implied",
            )

    if use_full:
        if pf.coverage.get("lineups"):
            _set_lineups(out, pf)
        threat = out.get("player_goal_threat")
        if threat and pf.injuries_impact_home is not None:
            threat.signals = {
                **(threat.signals or {}),
                "injuries_impact_home": pf.injuries_impact_home,
                "injuries_impact_away": pf.injuries_impact_away,
            }

    return out
