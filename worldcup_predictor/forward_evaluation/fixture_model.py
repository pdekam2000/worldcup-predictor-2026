"""Unified forward-evaluation fixture model — Tier A + Tier B."""

from __future__ import annotations

from typing import Any, Literal

from worldcup_predictor.gpt_actions.competition_normalize import (
    is_friendly_competition,
    is_tier_b_shadow,
    mapping_quality,
    normalize_competition_key,
)
from worldcup_predictor.gpt_actions.owner_scope import (
    TEST_PHASE_DISPLAY,
    TRUSTED_NOTE,
    TEST_PHASE_NOTE,
    fixture_tier,
)
from worldcup_predictor.gpt_actions.tier_b_shadow_registry import TIER_B_SHADOW_DOMAINS
from worldcup_predictor.owner_daily.constants import DAILY_SUPPORTED_COMPETITIONS

ValidationTier = Literal["A", "B"]
DisplayStatus = Literal["TRUSTED", "TEST_PHASE", "NO_PREDICTION_SUPPORT", "UNSUPPORTED", "FRIENDLY"]


def competition_family(competition_key: str | None) -> str:
    canon = normalize_competition_key(competition_key) or str(competition_key or "unknown")
    if canon in DAILY_SUPPORTED_COMPETITIONS:
        if canon == "world_cup_2026":
            return "world_cup"
        if canon in ("champions_league", "europa_league", "conference_league"):
            return "uefa_club"
        return "domestic_top_tier"
    meta = TIER_B_SHADOW_DOMAINS.get(canon) or {}
    country = str(meta.get("country") or "unknown")
    return f"tier_b_{country.lower().replace(' ', '_')}"


def domain_type(competition_key: str | None) -> str:
    canon = normalize_competition_key(competition_key) or str(competition_key or "unknown")
    if canon == "world_cup_2026":
        return "international_tournament"
    if canon in ("champions_league", "europa_league", "conference_league"):
        return "uefa_club"
    if canon in DAILY_SUPPORTED_COMPETITIONS:
        return "domestic_league"
    if is_tier_b_shadow(competition_key):
        return "tier_b_domestic"
    return "unknown"


def display_status_for_tier(tier: str | None) -> DisplayStatus | str:
    if tier == "A":
        return "TRUSTED"
    if tier == "B":
        return "TEST_PHASE"
    return "UNSUPPORTED"


def validation_note_for_tier(tier: str | None) -> str | None:
    if tier == "A":
        return TRUSTED_NOTE
    if tier == "B":
        return TEST_PHASE_NOTE
    return None


def prediction_mode_for_tier(tier: str | None) -> str:
    if tier == "B":
        return "TIER_B_OWNER_SHADOW"
    if tier == "A":
        return "TIER_A_PRODUCTION"
    return "UNSUPPORTED"


def listing_status(
    competition_key: str | None,
    *,
    odds_available: bool | None = None,
    data_quality_blocked: bool = False,
    wde_ecse_supported: bool | None = None,
) -> str:
    if is_friendly_competition(competition_key):
        return "FRIENDLY"
    tier = fixture_tier(competition_key)
    if tier is None:
        return "UNSUPPORTED"
    if data_quality_blocked:
        return "DATA_QUALITY_BLOCKED"
    if odds_available is False:
        return "ODDS_MISSING"
    if wde_ecse_supported is False:
        return "NO_PREDICTION_SUPPORT"
    if tier == "A":
        return "TRUSTED"
    return "TEST_PHASE"


def enrich_unified_fixture(
    *,
    fixture_id: int,
    home_team: str,
    away_team: str,
    competition_key: str,
    kickoff_utc: str,
    status: str,
    scope: str = "owner",
    listing_only: bool = False,
    odds_available: bool | None = None,
    data_quality_blocked: bool = False,
    prediction_eligible: bool | None = None,
) -> dict[str, Any]:
    canon = normalize_competition_key(competition_key) or competition_key
    tier = fixture_tier(competition_key)
    display = display_status_for_tier(tier)
    is_shadow = tier == "B"
    eligible = prediction_eligible
    if eligible is None and not listing_only and tier in ("A", "B"):
        eligible = odds_available is not False and not data_quality_blocked

    return {
        "fixture_id": fixture_id,
        "home_team": home_team,
        "away_team": away_team,
        "competition": canon,
        "competition_raw": competition_key,
        "competition_family": competition_family(competition_key),
        "domain_type": domain_type(competition_key),
        "validation_tier": tier,
        "display_status": display,
        "display_label": "TRUSTED" if tier == "A" else TEST_PHASE_DISPLAY if tier == "B" else display,
        "validation_note": validation_note_for_tier(tier),
        "prediction_mode": prediction_mode_for_tier(tier),
        "public_visible": tier == "A" and not is_shadow,
        "owner_visible": tier in ("A", "B"),
        "owner_shadow": is_shadow,
        "mapping_quality": mapping_quality(competition_key),
        "data_status": "discovered",
        "kickoff": kickoff_utc,
        "kickoff_utc": kickoff_utc,
        "status": status,
        "tier": tier,
        "scope": scope,
        "listing_status": listing_status(
            competition_key,
            odds_available=odds_available,
            data_quality_blocked=data_quality_blocked,
        ),
        "prediction_eligible": eligible,
        "prediction_allowed": tier in ("A", "B"),
    }
