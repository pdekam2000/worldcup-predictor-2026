"""Owner discovery scope — production vs Tier B shadow."""

from __future__ import annotations

from typing import Any, Literal

from worldcup_predictor.gpt_actions.competition_normalize import (
    is_friendly_competition,
    is_tier_b_shadow,
    mapping_quality,
    normalize_competition_key,
)
from worldcup_predictor.gpt_actions.tier_b_shadow_registry import tier_b_discovery_keys
from worldcup_predictor.owner_daily.constants import DAILY_SUPPORTED_COMPETITIONS
from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture

DiscoveryScope = Literal["production", "owner", "shadow", "trusted", "test_phase"]
PredictionScope = Literal["production", "owner_shadow", "owner"]
ListingFilter = Literal["all", "trusted", "test_phase", "prediction_eligible"]

TRUSTED_NOTE = "Validated competition/domain under current production policy."
TEST_PHASE_NOTE = (
    "Competition/domain is under forward evaluation. Full model output is available, "
    "but trust status is still being validated."
)
TEST_PHASE_DISPLAY = "TEST PHASE — UNDER FORWARD EVALUATION"


def validate_discovery_scope(scope: str) -> DiscoveryScope:
    s = (scope or "production").strip().lower()
    if s == "trusted":
        return "production"
    if s == "test_phase":
        return "shadow"
    if s not in ("production", "owner", "shadow"):
        raise ValueError("scope must be production, owner, shadow, trusted, or test_phase")
    return s  # type: ignore[return-value]


def validate_prediction_scope(scope: str) -> PredictionScope:
    s = (scope or "production").strip().lower()
    if s not in ("production", "owner_shadow", "owner"):
        raise ValueError("prediction_scope must be production, owner_shadow, or owner")
    return s  # type: ignore[return-value]


def competition_keys_for_scope(scope: DiscoveryScope) -> list[str]:
    production = list(DAILY_SUPPORTED_COMPETITIONS)
    tier_b = tier_b_discovery_keys()
    if scope == "production":
        return production
    if scope == "shadow":
        return tier_b
    return sorted(set(production + tier_b))


def is_tier_a_competition(competition_key: str | None) -> bool:
    canon = normalize_competition_key(competition_key)
    return canon in DAILY_SUPPORTED_COMPETITIONS if canon else False


def fixture_tier(competition_key: str | None) -> str | None:
    if is_friendly_competition(competition_key):
        return None
    if is_tier_a_competition(competition_key):
        return "A"
    if is_tier_b_shadow(competition_key):
        return "B"
    return None


def fixture_allowed_for_discovery(f: DailyFixture, scope: DiscoveryScope) -> bool:
    if is_friendly_competition(f.competition_key):
        return False
    tier = fixture_tier(f.competition_key)
    if tier is None:
        return False
    if scope == "production":
        return tier == "A"
    if scope == "shadow":
        return tier == "B"
    return tier in ("A", "B")


def validation_note_for_tier(tier: str | None) -> str | None:
    if tier == "A":
        return TRUSTED_NOTE
    if tier == "B":
        return TEST_PHASE_NOTE
    return None


def enrich_discovered_fixture(f: DailyFixture, *, scope: DiscoveryScope) -> dict[str, Any]:
    from worldcup_predictor.forward_evaluation.fixture_model import enrich_unified_fixture

    return enrich_unified_fixture(
        fixture_id=f.fixture_id,
        home_team=f.home_team,
        away_team=f.away_team,
        competition_key=f.competition_key,
        kickoff_utc=f.kickoff_utc,
        status=f.status,
        scope=scope,
    )


def display_labels_for_tier(tier: str | None) -> dict[str, str | None]:
    if tier == "A":
        return {"display_status": "TRUSTED", "display_label": "TRUSTED", "validation_note": validation_note_for_tier("A")}
    if tier == "B":
        return {
            "display_status": "TEST_PHASE",
            "display_label": TEST_PHASE_DISPLAY,
            "validation_note": validation_note_for_tier("B"),
        }
    return {"display_status": "UNSUPPORTED", "display_label": "UNSUPPORTED", "validation_note": None}


def fixture_allowed_for_prediction(
    competition_key: str | None,
    *,
    prediction_scope: PredictionScope,
) -> tuple[bool, str | None]:
    if is_friendly_competition(competition_key):
        return False, "friendlies_unsupported"
    tier = fixture_tier(competition_key)
    if tier is None:
        return False, "unsupported_competition"
    if prediction_scope == "production":
        return tier == "A", "tier_b_requires_owner_shadow_scope" if tier == "B" else None
    if prediction_scope == "owner_shadow":
        return tier == "B", "tier_a_requires_production_scope" if tier == "A" else None
    return tier in ("A", "B"), None
