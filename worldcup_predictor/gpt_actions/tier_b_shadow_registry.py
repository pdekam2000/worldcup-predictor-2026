"""Tier B Shadow domain registry — owner GPT only, not public production."""

from __future__ import annotations

from typing import Any

TIER_B_SHADOW_DOMAINS: dict[str, dict[str, Any]] = {
    "allsvenskan": {
        "canonical_key": "allsvenskan",
        "provider_league_id": 113,
        "aliases": ("league_113", "allsvenskan", "Allsvenskan"),
        "country": "Sweden",
        "owner_shadow_visible": True,
        "public_prediction_enabled": False,
        "tier": "B",
        "forward_shadow_required": True,
    },
    "superettan": {
        "canonical_key": "superettan",
        "provider_league_id": 114,
        "aliases": ("league_114", "superettan", "Superettan"),
        "country": "Sweden",
        "owner_shadow_visible": True,
        "public_prediction_enabled": False,
        "tier": "B",
        "forward_shadow_required": True,
    },
    "a_lyga": {
        "canonical_key": "a_lyga",
        "provider_league_id": 362,
        "aliases": ("league_362", "a_lyga", "A Lyga"),
        "country": "Lithuania",
        "owner_shadow_visible": True,
        "public_prediction_enabled": False,
        "tier": "B",
        "forward_shadow_required": True,
    },
    "one_lyga": {
        "canonical_key": "one_lyga",
        "provider_league_id": 361,
        "aliases": ("league_361", "one_lyga", "1 Lyga"),
        "country": "Lithuania",
        "owner_shadow_visible": True,
        "public_prediction_enabled": False,
        "tier": "B",
        "forward_shadow_required": True,
    },
    "virsliga": {
        "canonical_key": "virsliga",
        "provider_league_id": 365,
        "aliases": ("league_365", "virsliga", "Virsliga"),
        "country": "Latvia",
        "owner_shadow_visible": True,
        "public_prediction_enabled": False,
        "tier": "B",
        "forward_shadow_required": True,
    },
    "urvalsdeild": {
        "canonical_key": "urvalsdeild",
        "provider_league_id": 164,
        "aliases": ("league_164", "urvalsdeild", "Úrvalsdeild", "Urvalsdeild"),
        "country": "Iceland",
        "owner_shadow_visible": True,
        "public_prediction_enabled": False,
        "tier": "B",
        "forward_shadow_required": True,
    },
    "one_deild": {
        "canonical_key": "one_deild",
        "provider_league_id": 165,
        "aliases": ("league_165", "one_deild", "1. Deild"),
        "country": "Iceland",
        "owner_shadow_visible": True,
        "public_prediction_enabled": False,
        "tier": "B",
        "forward_shadow_required": True,
    },
    "eliteserien": {
        "canonical_key": "eliteserien",
        "provider_league_id": 103,
        "aliases": ("league_103", "eliteserien", "Eliteserien"),
        "country": "Norway",
        "owner_shadow_visible": True,
        "public_prediction_enabled": False,
        "tier": "B",
        "forward_shadow_required": True,
    },
    "veikkausliiga": {
        "canonical_key": "veikkausliiga",
        "provider_league_id": 244,
        "aliases": ("league_244", "veikkausliiga", "Veikkausliiga"),
        "country": "Finland",
        "owner_shadow_visible": True,
        "public_prediction_enabled": False,
        "tier": "B",
        "forward_shadow_required": True,
    },
    "la_liga": {
        "canonical_key": "la_liga",
        "provider_league_id": 140,
        "aliases": ("league_140", "la_liga", "La Liga"),
        "country": "Spain",
        "owner_shadow_visible": True,
        "public_prediction_enabled": False,
        "tier": "B",
        "forward_shadow_required": True,
    },
    "serie_a": {
        "canonical_key": "serie_a",
        "provider_league_id": 135,
        "aliases": ("league_135", "serie_a", "Serie A"),
        "country": "Italy",
        "owner_shadow_visible": True,
        "public_prediction_enabled": False,
        "tier": "B",
        "forward_shadow_required": True,
    },
    "ligue_1": {
        "canonical_key": "ligue_1",
        "provider_league_id": 61,
        "aliases": ("league_61", "ligue_1", "Ligue 1"),
        "country": "France",
        "owner_shadow_visible": True,
        "public_prediction_enabled": False,
        "tier": "B",
        "forward_shadow_required": True,
    },
}

TIER_B_CANONICAL_KEYS: frozenset[str] = frozenset(TIER_B_SHADOW_DOMAINS.keys())

FRIENDLY_BLOCKED_KEYS: frozenset[str] = frozenset({"league_667", "friendlies", "club_friendlies"})


def tier_b_domain_keys() -> tuple[str, ...]:
    return tuple(TIER_B_SHADOW_DOMAINS.keys())


def tier_b_discovery_keys() -> list[str]:
    """Canonical + league_* aliases for DB discovery."""
    keys: list[str] = []
    for meta in TIER_B_SHADOW_DOMAINS.values():
        keys.append(meta["canonical_key"])
        keys.extend(a for a in meta["aliases"] if str(a).startswith("league_"))
    return sorted(set(keys))


def get_tier_b_domain(canonical_key: str) -> dict[str, Any] | None:
    return TIER_B_SHADOW_DOMAINS.get(canonical_key)
