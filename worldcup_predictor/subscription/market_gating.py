"""Plan-based market gating on prediction payloads — Phase 38A."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.subscription.plan_limits import normalize_plan, plan_allowed_market_keys

# Map API/ranking market keys → canonical tier keys
_CANONICAL_MAP: dict[str, str] = {
    "1x2": "1x2",
    "match_winner": "1x2",
    "home_win": "1x2",
    "draw": "1x2",
    "away_win": "1x2",
    "btts": "btts",
    "both_teams_to_score": "btts",
    "over_under": "over_under",
    "over_under_2_5": "over_under",
    "over_under_25": "over_under",
    "ou_2_5": "over_under",
    "double_chance": "premium",
    "halftime": "premium",
    "ht_1x2": "premium",
    "first_goal": "premium",
    "first_goal_team": "premium",
    "first_goal_scorer": "premium",
    "goalscorer": "premium",
    "goal_minute": "premium",
    "first_half_team_to_score": "premium",
    "correct_score": "premium",
    "correct_scores": "premium",
    "premium": "premium",
    "xg": "premium",
    "high_odds": "premium",
}


def canonical_market_key(raw: str | None) -> str:
    key = str(raw or "").strip().lower().replace(" ", "_").replace("/", "_")
    return _CANONICAL_MAP.get(key, "premium")


def market_allowed_for_plan(plan: str, raw_market_key: str) -> bool:
    allowed = plan_allowed_market_keys(plan)
    if allowed is None:
        return True
    canon = canonical_market_key(raw_market_key)
    if canon == "premium":
        return False
    return canon in allowed


def _strip_detailed_markets(detailed: dict[str, Any], plan: str) -> dict[str, Any]:
    allowed = plan_allowed_market_keys(plan)
    if allowed is None:
        return detailed
    out = dict(detailed)
    if "1x2" not in allowed and "match_winner" not in allowed:
        out.pop("match_winner", None)
    else:
        out["match_winner"] = detailed.get("match_winner")
    if "over_under" not in allowed:
        out.pop("over_under_25", None)
    if "btts" not in allowed:
        out.pop("btts", None)
    for key in (
        "halftime",
        "first_goal",
        "goalscorer",
        "first_half_team_to_score",
        "double_chance",
        "correct_scores",
    ):
        out.pop(key, None)
    return out


def _strip_probabilities(probs: dict[str, Any], plan: str) -> dict[str, Any]:
    allowed = plan_allowed_market_keys(plan)
    if allowed is None:
        return probs
    out = {
        "home_win": probs.get("home_win"),
        "draw": probs.get("draw"),
        "away_win": probs.get("away_win"),
    }
    if "over_under" in allowed:
        if probs.get("over_under_2_5"):
            out["over_under_2_5"] = probs["over_under_2_5"]
    if "btts" in allowed:
        if probs.get("btts"):
            out["btts"] = probs["btts"]
    return out


def _filter_ranked_items(items: list[Any], plan: str) -> list[Any]:
    out: list[Any] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        mk = item.get("market_key") or item.get("market") or ""
        if market_allowed_for_plan(plan, str(mk)):
            out.append(item)
    return out


def apply_plan_market_gate(payload: dict[str, Any], plan: str | None) -> dict[str, Any]:
    """Filter markets in a prediction payload for the user's plan."""
    tier = normalize_plan(plan)
    if plan_allowed_market_keys(tier) is None:
        out = dict(payload)
        out["plan_markets"] = {"tier": tier, "restricted": False}
        return out

    out = dict(payload)
    if isinstance(out.get("detailed_markets"), dict):
        out["detailed_markets"] = _strip_detailed_markets(out["detailed_markets"], tier)
    if isinstance(out.get("probabilities"), dict):
        out["probabilities"] = _strip_probabilities(out["probabilities"], tier)
    if isinstance(out.get("recommended_bets"), list):
        out["recommended_bets"] = _filter_ranked_items(out["recommended_bets"], tier)
    if isinstance(out.get("market_ranking"), list):
        out["market_ranking"] = _filter_ranked_items(out["market_ranking"], tier)
    for pick_key in ("safe_pick", "value_pick", "aggressive_pick", "caution_pick", "best_available_pick", "primary_recommendation"):
        pick = out.get(pick_key)
        if isinstance(pick, dict):
            mk = pick.get("market_key") or pick.get("market") or ""
            if not market_allowed_for_plan(tier, str(mk)):
                out[pick_key] = None
    out["plan_markets"] = {
        "tier": tier,
        "restricted": True,
        "allowed": sorted(plan_allowed_market_keys(tier) or []),
    }
    return out
