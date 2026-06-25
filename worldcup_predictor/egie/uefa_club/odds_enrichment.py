"""Phase API-K — UEFA odds sub-strategy enrichment (D1–D8), UEFA-only."""

from __future__ import annotations

import copy
from typing import Any

from worldcup_predictor.goal_timing.models import GoalTimingAgentOutput
from worldcup_predictor.egie.uefa_club.odds_intelligence import OddsSubStrategy, parse_uefa_odds_deep


def _clone(outputs: dict[str, GoalTimingAgentOutput]) -> dict[str, GoalTimingAgentOutput]:
    return {k: GoalTimingAgentOutput(**copy.deepcopy(v.__dict__)) for k, v in outputs.items()}


def _apply_pressure(
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
    agent.notes = f"UEFA odds sub-strategy pressure ({source})."


def _apply_odds_agent(
    outputs: dict[str, GoalTimingAgentOutput],
    *,
    home: float | None,
    away: float | None,
    draw: float | None = None,
    movement: float | None = None,
) -> None:
    agent = outputs.get("odds_goal_intelligence")
    if not agent or home is None or away is None:
        return
    agent.signals = {
        **(agent.signals or {}),
        "reliable_odds": True,
        "implied_home": home,
        "implied_away": away,
        "implied_draw": draw,
        "odds_movement_home": movement,
        "market_favorite": "home" if home >= away else "away",
    }
    agent.impact_score = min(1.0, 0.4 + abs(home - away))
    agent.missing_data = []
    agent.notes = "UEFA odds sub-strategy enrichment."


def enrich_odds_substrategy(
    outputs: dict[str, GoalTimingAgentOutput],
    odds_features: dict[str, Any],
    strategy: OddsSubStrategy,
) -> dict[str, GoalTimingAgentOutput]:
    """Apply D1–D8 odds signals to agent outputs (mirrors production D pressure path)."""
    if strategy == "A":
        return outputs

    out = _clone(outputs)
    o = odds_features

    def _pressure_from(home_key: str, away_key: str, source: str) -> bool:
        h, a = o.get(home_key), o.get(away_key)
        if h is None or a is None:
            return False
        _apply_pressure(out, home=float(h), away=float(a), source=source)
        _apply_odds_agent(out, home=float(h), away=float(a), draw=o.get("consensus_implied_draw"))
        return True

    if strategy == "D1":
        _pressure_from("opening_implied_home", "opening_implied_away", "opening_1x2")
    elif strategy == "D2":
        _pressure_from("closing_implied_home", "closing_implied_away", "closing_1x2")
    elif strategy == "D3":
        mh, ma = o.get("movement_home"), o.get("movement_away")
        if mh is not None or ma is not None:
            base = 0.5
            h = base + float(mh or 0) * 2
            a = base + float(ma or 0) * 2
            _apply_pressure(out, home=h, away=a, source="odds_movement")
    elif strategy == "D4":
        _pressure_from("consensus_implied_home", "consensus_implied_away", "consensus_implied")
    elif strategy == "D5":
        _pressure_from("first_team_score_home", "first_team_score_away", "first_goal_odds")
    elif strategy == "D6":
        _pressure_from("first_team_score_home", "first_team_score_away", "team_to_score_first")
    elif strategy == "D7":
        _pressure_from("sharp_implied_home", "sharp_implied_away", "sharp_consensus")
        if o.get("sharp_implied_home") is None:
            _pressure_from("consensus_implied_home", "consensus_implied_away", "consensus_fallback")
    elif strategy == "D8":
        applied = _pressure_from("consensus_implied_home", "consensus_implied_away", "consensus_1x2")
        if o.get("first_team_score_home") is not None and o.get("first_team_score_away") is not None:
            fh, fa = float(o["first_team_score_home"]), float(o["first_team_score_away"])
            ch, ca = float(o.get("consensus_implied_home") or fh), float(o.get("consensus_implied_away") or fa)
            blend_h = (ch + fh) / 2
            blend_a = (ca + fa) / 2
            _apply_pressure(out, home=blend_h, away=blend_a, source="full_odds_blend")
            mh = o.get("movement_home")
            if mh is not None and abs(float(mh)) > 0.01:
                _apply_pressure(out, home=blend_h + float(mh), away=blend_a - float(mh), source="full_odds_movement")
        elif not applied:
            _pressure_from("closing_implied_home", "closing_implied_away", "closing_fallback")

    return out


def coverage_for_odds_strategy(odds_features: dict[str, Any], strategy: OddsSubStrategy) -> bool:
    if strategy == "A":
        return True
    o = odds_features
    if strategy == "D1":
        return o.get("opening_implied_home") is not None
    if strategy == "D2":
        return o.get("closing_implied_home") is not None
    if strategy == "D3":
        return o.get("movement_home") is not None or o.get("movement_away") is not None
    if strategy == "D4":
        return o.get("consensus_implied_home") is not None
    if strategy in ("D5", "D6"):
        return o.get("first_team_score_home") is not None
    if strategy == "D7":
        return o.get("sharp_implied_home") is not None or o.get("consensus_implied_home") is not None
    if strategy == "D8":
        return o.get("consensus_implied_home") is not None or o.get("first_team_score_home") is not None
    return False
