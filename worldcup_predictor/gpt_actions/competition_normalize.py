"""Competition key normalization for GPT Actions owner scope."""

from __future__ import annotations

from worldcup_predictor.gpt_actions.tier_b_shadow_registry import (
    FRIENDLY_BLOCKED_KEYS,
    TIER_B_CANONICAL_KEYS,
    TIER_B_SHADOW_DOMAINS,
)

_LEAGUE_ID_TO_CANONICAL: dict[str, str] = {
    f"league_{meta['provider_league_id']}": key for key, meta in TIER_B_SHADOW_DOMAINS.items()
}

_ALIAS_TO_CANONICAL: dict[str, str] = {}
for key, meta in TIER_B_SHADOW_DOMAINS.items():
    _ALIAS_TO_CANONICAL[key] = key
    _ALIAS_TO_CANONICAL[key.lower()] = key
    for alias in meta.get("aliases") or ():
        _ALIAS_TO_CANONICAL[str(alias)] = key
        _ALIAS_TO_CANONICAL[str(alias).lower()] = key


def normalize_competition_key(competition_key: str | None) -> str | None:
    if not competition_key:
        return None
    raw = str(competition_key).strip()
    if raw in _ALIAS_TO_CANONICAL:
        return _ALIAS_TO_CANONICAL[raw]
    low = raw.lower()
    if low in _ALIAS_TO_CANONICAL:
        return _ALIAS_TO_CANONICAL[low]
    if raw.startswith("league_") and raw in _LEAGUE_ID_TO_CANONICAL:
        return _LEAGUE_ID_TO_CANONICAL[raw]
    return raw


def is_friendly_competition(competition_key: str | None) -> bool:
    if not competition_key:
        return False
    raw = str(competition_key).strip().lower()
    if raw in FRIENDLY_BLOCKED_KEYS:
        return True
    if raw == "league_667":
        return True
    return "friendly" in raw


def is_tier_b_shadow(competition_key: str | None) -> bool:
    canon = normalize_competition_key(competition_key)
    return canon in TIER_B_CANONICAL_KEYS if canon else False


def mapping_quality(competition_key: str | None) -> str:
    if is_friendly_competition(competition_key):
        return "blocked_friendly"
    canon = normalize_competition_key(competition_key)
    if not canon:
        return "unknown"
    if canon in TIER_B_CANONICAL_KEYS:
        raw = str(competition_key or "").strip()
        if raw == canon or raw in (canon, canon.lower()):
            return "canonical"
        if raw.startswith("league_"):
            return "alias_resolved"
        return "alias_resolved"
    return "unmapped"
