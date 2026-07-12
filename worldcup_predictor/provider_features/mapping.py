"""Owner-scope coverage targets for prematch feature backfill."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.gpt_actions.owner_scope import fixture_tier
from worldcup_predictor.gpt_actions.tier_b_shadow_registry import TIER_B_SHADOW_DOMAINS
from worldcup_predictor.owner_daily.constants import DAILY_SUPPORTED_COMPETITIONS

# Pilot phase selections (user-requested subset)
PILOT_TIER_A_KEYS: tuple[str, ...] = ("world_cup_2026",)
PILOT_TIER_B_KEYS: tuple[str, ...] = ("allsvenskan", "eliteserien")

# Owner-scope matrix keys (Tier A production + requested Tier B)
OWNER_SCOPE_MATRIX_KEYS: tuple[str, ...] = (
    "world_cup_2026",
    "allsvenskan",
    "superettan",
    "a_lyga",
    "virsliga",
    "urvalsdeild",
    "eliteserien",
    "veikkausliiga",
)

TIER_A_API_LEAGUE_IDS: dict[str, int] = {
    "world_cup_2026": 1,
    "champions_league": 2,
    "europa_league": 3,
    "conference_league": 848,
    "premier_league": 39,
    "bundesliga": 78,
}

SPORTMONKS_WC = {"league_id": 732, "season_id": 26618, "competition_key": "world_cup_2026"}


def competition_meta(key: str) -> dict[str, Any]:
    if key in DAILY_SUPPORTED_COMPETITIONS:
        return {
            "canonical_key": key,
            "tier": "A",
            "provider_league_id": TIER_A_API_LEAGUE_IDS.get(key),
            "sportmonks_league_id": SPORTMONKS_WC["league_id"] if key == "world_cup_2026" else None,
            "sportmonks_season_id": SPORTMONKS_WC["season_id"] if key == "world_cup_2026" else None,
            "sportmonks_xg_supported": key == "world_cup_2026",
            "api_football_supported": True,
        }
    meta = TIER_B_SHADOW_DOMAINS.get(key)
    if meta:
        return {
            "canonical_key": key,
            "tier": "B",
            "provider_league_id": meta.get("provider_league_id"),
            "sportmonks_league_id": None,
            "sportmonks_season_id": None,
            "sportmonks_xg_supported": False,
            "api_football_supported": True,
            "country": meta.get("country"),
        }
    return {"canonical_key": key, "tier": None}


def pilot_competitions() -> list[dict[str, Any]]:
    keys = list(PILOT_TIER_A_KEYS) + list(PILOT_TIER_B_KEYS)
    return [competition_meta(k) for k in keys]


def tier_for_key(key: str) -> str | None:
    if key in DAILY_SUPPORTED_COMPETITIONS:
        return "A"
    if key in TIER_B_SHADOW_DOMAINS:
        return "B"
    return None
