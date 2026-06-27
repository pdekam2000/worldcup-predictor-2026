"""Sanitize payloads for public sharing — Phase A20."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.social_trust.constants import BLOCKED_PAYLOAD_KEYS


def _is_blocked_key(key: str) -> bool:
    k = str(key).lower()
    if k in BLOCKED_PAYLOAD_KEYS:
        return True
    return any(part in k for part in ("_internal", "_debug", "password", "secret", "owner_"))


def sanitize_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 8:
        return None
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) > 2000:
            return value[:2000] + "…"
        return value
    if isinstance(value, list):
        return [sanitize_value(v, depth=depth + 1) for v in value[:50]]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, val in value.items():
            if _is_blocked_key(str(key)):
                continue
            out[str(key)] = sanitize_value(val, depth=depth + 1)
        return out
    return str(value)[:500]


def sanitize_pick_payload(data: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "fixture_id",
        "home_team",
        "away_team",
        "league",
        "competition_key",
        "kickoff_utc",
        "market",
        "market_label",
        "prediction",
        "bet_quality_score",
        "bet_quality_tier",
        "confidence",
        "odds_decimal",
        "reason",
        "disclaimer",
    }
    raw = {k: data.get(k) for k in allowed if k in data}
    return sanitize_value(raw)  # type: ignore[return-value]


def sanitize_combo_payload(data: dict[str, Any]) -> dict[str, Any]:
    legs = []
    for leg in (data.get("legs") or [])[:8]:
        if not isinstance(leg, dict):
            continue
        legs.append(
            sanitize_pick_payload(
                {
                    "fixture_id": leg.get("fixture_id"),
                    "home_team": leg.get("home_team"),
                    "away_team": leg.get("away_team"),
                    "market": leg.get("market"),
                    "market_label": leg.get("market_label"),
                    "prediction": leg.get("prediction"),
                    "bet_quality_score": leg.get("bet_quality_score"),
                    "odds_decimal": leg.get("odds_decimal"),
                }
            )
        )
    return sanitize_value(
        {
            "combo_type": data.get("combo_type") or data.get("type"),
            "label": data.get("label"),
            "combined_odds": data.get("combined_odds"),
            "legs": legs,
            "disclaimer": data.get("disclaimer"),
        }
    )  # type: ignore[return-value]


def sanitize_plan_payload(data: dict[str, Any]) -> dict[str, Any]:
    singles = [sanitize_pick_payload(s) for s in (data.get("best_singles") or data.get("best_single_bets") or [])[:8]]
    combos = []
    for c in (data.get("combos") or []):
        if isinstance(c, dict):
            combos.append(sanitize_combo_payload(c))
        elif isinstance(data.get("combos"), dict):
            for v in list(data["combos"].values())[:3]:
                if isinstance(v, dict):
                    combos.append(sanitize_combo_payload(v))
            break
    return sanitize_value(
        {
            "date": data.get("date"),
            "day_quality": data.get("day_quality"),
            "best_singles": singles,
            "combos": combos[:3],
            "disclaimer": data.get("disclaimer"),
        }
    )  # type: ignore[return-value]


def sanitize_paper_report_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Only anonymized virtual portfolio stats — no user identity."""
    allowed = {
        "month",
        "starting_bankroll",
        "ending_bankroll",
        "net_profit_loss",
        "roi_pct",
        "winrate",
        "total_bets",
        "best_market",
        "worst_market",
        "best_combo_type",
        "currency",
        "headline",
        "recommendation_next_month",
        "disclaimer",
        "shared_anonymously",
    }
    raw = {k: data.get(k) for k in allowed if k in data}
    raw["shared_anonymously"] = True
    return sanitize_value(raw)  # type: ignore[return-value]
