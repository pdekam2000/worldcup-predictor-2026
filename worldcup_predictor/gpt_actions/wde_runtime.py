"""Tier B owner-shadow WDE routing — normalization, registry parity, failure taxonomy."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.config.competitions import COMPETITION_REGISTRY, CompetitionConfig
from worldcup_predictor.config.settings import Settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.gpt_actions.competition_normalize import (
    is_tier_b_shadow,
    normalize_competition_key,
)
from worldcup_predictor.gpt_actions.tier_b_shadow_registry import get_tier_b_domain
from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture

_TIER_B_DISPLAY_NAMES: dict[str, str] = {
    "allsvenskan": "Allsvenskan",
    "superettan": "Superettan",
    "a_lyga": "A Lyga",
    "one_lyga": "1 Lyga",
    "virsliga": "Virsliga",
    "urvalsdeild": "Úrvalsdeild",
    "one_deild": "1. Deild",
    "eliteserien": "Eliteserien",
    "veikkausliiga": "Veikkausliiga",
    "la_liga": "La Liga",
    "serie_a": "Serie A",
    "ligue_1": "Ligue 1",
}


def classify_wde_exception(exc: BaseException) -> tuple[str, str]:
    """Map pipeline exceptions to safe internal failure codes."""
    if isinstance(exc, KeyError) and "Unknown competition" in str(exc):
        return "WDE_COMPETITION_UNSUPPORTED", "competition_registry"
    if isinstance(exc, OSError):
        msg = str(exc).lower()
        if "read-only file system" in msg or "errno 30" in msg:
            return "WDE_CACHE_WRITE_FAILED", "api_cache"
        return "WDE_DEPENDENCY_FAILED", "filesystem"
    if isinstance(exc, RuntimeError) and "rate limit" in str(exc).lower():
        return "WDE_DEPENDENCY_FAILED", "api_rate_limit"
    return "WDE_INFERENCE_EXCEPTION", "pipeline"


def register_tier_b_competition_runtime(
    canonical_key: str,
    *,
    repo: FootballIntelligenceRepository,
    season: int | None = None,
) -> CompetitionConfig | None:
    """Register Tier B domain for owner-shadow WDE only (runtime + SQLite)."""
    meta = get_tier_b_domain(canonical_key)
    if not meta:
        return None
    name = _TIER_B_DISPLAY_NAMES.get(canonical_key, canonical_key.replace("_", " ").title())
    resolved_season = int(season or 2026)
    comp = COMPETITION_REGISTRY.get(canonical_key)
    if comp is None:
        comp = CompetitionConfig(
            key=canonical_key,
            name=name,
            league_id=int(meta["provider_league_id"]),
            season=resolved_season,
            country=str(meta.get("country") or ""),
            compensation_type="league",
            supports_table=True,
            enabled=True,
            learning_profile_key=canonical_key,
            notes="Tier B owner-shadow runtime registration (Phase 6C).",
        )
        COMPETITION_REGISTRY[canonical_key] = comp
    repo.upsert_competition(comp)
    return comp


def prepare_daily_fixture_for_wde(
    fixture: DailyFixture,
    *,
    repo: FootballIntelligenceRepository,
    settings: Settings | None = None,
) -> DailyFixture:
    """
    Canonical competition normalization + Tier B registry parity before WDE.

    Does not alter WDE formulas — routing and support gates only.
    """
    _ = settings
    raw_key = fixture.competition_key
    canon = normalize_competition_key(raw_key) or raw_key
    if is_tier_b_shadow(canon):
        register_tier_b_competition_runtime(canon, repo=repo, season=fixture.season)
    if canon == raw_key:
        return fixture
    return DailyFixture(
        fixture_id=fixture.fixture_id,
        provider_fixture_id=fixture.provider_fixture_id,
        competition_key=canon,
        home_team=fixture.home_team,
        away_team=fixture.away_team,
        kickoff_utc=fixture.kickoff_utc,
        status=fixture.status,
        season=fixture.season,
        coverage_sources=list(fixture.coverage_sources),
        provider_ids=dict(fixture.provider_ids),
    )


def wde_skip_detail(
    *,
    reason: str,
    fixture_id: int,
    competition_key: str,
    failure_code: str | None = None,
    failure_stage: str | None = None,
    error: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    detail: dict[str, Any] = {
        "fixture_id": fixture_id,
        "competition_key": competition_key,
        "engine": "wde",
        "reason": reason,
    }
    if failure_code:
        detail["wde_failure_code"] = failure_code
    if failure_stage:
        detail["wde_failure_stage"] = failure_stage
    if error:
        detail["error"] = error
    if extra:
        detail.update(extra)
    return detail


def attach_wde_execution_diagnostics(
    detail: dict[str, Any],
    *,
    wde_execution_status: str,
    failure_code: str | None = None,
    failure_stage: str | None = None,
    failure_dependency: str | None = None,
    failure_module: str | None = None,
    failure_message_sanitized: str | None = None,
    inputs_available: list[str] | None = None,
    inputs_missing: list[str] | None = None,
    fallback_attempted: bool = False,
    fallback_result: str | None = None,
) -> dict[str, Any]:
    """Structured sanitized WDE provenance (no secrets)."""
    detail["wde_execution_status"] = wde_execution_status
    if failure_code:
        detail["wde_failure_code"] = failure_code
    if failure_stage:
        detail["wde_failure_stage"] = failure_stage
    if failure_dependency:
        detail["wde_failure_dependency"] = failure_dependency
    if failure_module:
        detail["wde_failure_module"] = failure_module
    if failure_message_sanitized:
        detail["wde_failure_message_sanitized"] = failure_message_sanitized
    if inputs_available is not None:
        detail["wde_inputs_available"] = list(inputs_available)
    if inputs_missing is not None:
        detail["wde_inputs_missing"] = list(inputs_missing)
    detail["wde_fallback_attempted"] = bool(fallback_attempted)
    if fallback_result:
        detail["wde_fallback_result"] = fallback_result
    return detail
