"""Standardized per-fixture eligibility and lifecycle status."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from worldcup_predictor.gpt_actions.competition_normalize import is_friendly_competition
from worldcup_predictor.gpt_actions.owner_scope import fixture_tier, is_tier_a_competition
from worldcup_predictor.owner_daily.data_completeness import FixtureCompletenessReport
from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture
from worldcup_predictor.owner_daily.pipeline.constants import (
    ALREADY_FROZEN_IDEMPOTENT_REUSE,
    BLOCKED_FRIENDLY,
    BLOCKED_MISSING_DEPENDENCY,
    BLOCKED_MISSING_ODDS,
    BLOCKED_POST_KICKOFF,
    BLOCKED_PROVIDER_FAILURE,
    BLOCKED_STALE_ODDS,
    BLOCKED_UNSUPPORTED_COMPETITION,
    MANUAL_REVIEW_REQUIRED,
    NO_BET_LOW_DATA_QUALITY,
    PREDICTED_AND_FROZEN,
)


def _parse_kickoff(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _kickoff_vienna(value: str | None, tz_name: str) -> str | None:
    dt = _parse_kickoff(value)
    if not dt:
        return None
    return dt.astimezone(ZoneInfo(tz_name)).strftime("%Y-%m-%d %H:%M %Z")


def prediction_scope_for_tier(tier: str | None) -> str | None:
    if tier == "A":
        return "production"
    if tier == "B":
        return "owner_shadow"
    return None


def classify_lifecycle_status(
    fixture: DailyFixture,
    *,
    completeness: FixtureCompletenessReport | None,
    wde_detail: dict[str, Any] | None,
    ecse_detail: dict[str, Any] | None,
    freeze_capture: dict[str, Any] | None,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Return eligibility + lifecycle status for one fixture."""
    now_utc = now_utc or datetime.now(timezone.utc)
    fid = int(fixture.provider_fixture_id)
    tier = fixture_tier(fixture.competition_key)
    scope = prediction_scope_for_tier(tier)

    missing_deps: list[str] = []
    available: list[str] = []
    unavailable: list[str] = []

    if is_friendly_competition(fixture.competition_key):
        return _blocked(
            fixture,
            BLOCKED_FRIENDLY,
            "Friendly competition excluded by policy",
            tier=tier,
            scope=scope,
            missing=["friendly_policy"],
        )

    if tier is None:
        return _blocked(
            fixture,
            BLOCKED_UNSUPPORTED_COMPETITION,
            f"Competition not in Tier A/B registry: {fixture.competition_key}",
            tier=tier,
            scope=scope,
        )

    kickoff = _parse_kickoff(fixture.kickoff_utc)
    if kickoff and kickoff <= now_utc and str(fixture.status or "").upper() not in ("NS", "TBD", "SCHEDULED"):
        return _blocked(
            fixture,
            BLOCKED_POST_KICKOFF,
            "Fixture already started or finished; prematch prediction not allowed",
            tier=tier,
            scope=scope,
        )

    if completeness:
        if completeness.wde_ready:
            available.append("wde")
        else:
            unavailable.append("wde")
        if completeness.ecse_ready:
            available.append("ecse")
        else:
            unavailable.append("ecse")
        for m in completeness.missing:
            missing_deps.append(m.missing_field)

    wde_reason = (wde_detail or {}).get("reason")
    ecse_reason = (ecse_detail or {}).get("reason")
    wde_gen = wde_detail and wde_detail.get("wde_execution_status") == "executed"
    ecse_gen = ecse_detail and ecse_detail.get("snapshot_write") in ("inserted", "refreshed")

    freshness = (wde_detail or {}).get("odds_freshness") or (ecse_detail or {}).get("odds_freshness") or {}
    stale = bool(freshness.get("requires_fresh_odds")) or wde_reason == "strict_fresh_odds_blocked"

    if stale:
        return _blocked(
            fixture,
            BLOCKED_STALE_ODDS,
            "Odds stale after refresh gate",
            tier=tier,
            scope=scope,
            missing=missing_deps,
            available=available,
            unavailable=unavailable,
            odds_freshness=freshness,
        )

    if wde_reason == "missing_odds" or ecse_reason == "missing_odds":
        return _blocked(
            fixture,
            BLOCKED_MISSING_ODDS,
            "No legitimate prematch 1X2 / lambda odds inputs",
            tier=tier,
            scope=scope,
            missing=missing_deps,
        )

    if wde_reason in ("missing_api_credentials", "missing_team_data") or ecse_reason == "missing_team_strength":
        return _blocked(
            fixture,
            BLOCKED_MISSING_DEPENDENCY,
            wde_reason or ecse_reason or "missing_dependency",
            tier=tier,
            scope=scope,
            missing=missing_deps,
        )

    if wde_reason == "engine_error" or ecse_reason == "engine_error":
        return _blocked(
            fixture,
            BLOCKED_PROVIDER_FAILURE,
            "Engine or provider runtime failure",
            tier=tier,
            scope=scope,
            missing=missing_deps,
        )

    freeze = freeze_capture or {}
    cap_status = str(freeze.get("capture_status") or "")
    if cap_status in ("created", "reused") and not freeze.get("quarantined"):
        status = ALREADY_FROZEN_IDEMPOTENT_REUSE if freeze.get("reused") else PREDICTED_AND_FROZEN
        complete = bool(wde_gen or wde_reason == "existing_prediction") and bool(
            ecse_gen or ecse_reason == "existing_snapshot"
        )
        return _eligible(
            fixture,
            lifecycle_status=status,
            tier=tier,
            scope=scope,
            complete=complete,
            available=available,
            unavailable=unavailable,
            freeze=freeze,
        )

    if wde_gen and ecse_gen:
        return _eligible(
            fixture,
            lifecycle_status=PREDICTED_AND_FROZEN,
            tier=tier,
            scope=scope,
            complete=True,
            available=available,
            unavailable=unavailable,
            freeze=freeze,
            note="Predictions generated; freeze capture pending or skipped",
        )

    if wde_gen or ecse_gen:
        return _eligible(
            fixture,
            lifecycle_status=MANUAL_REVIEW_REQUIRED if not complete_partial(wde_gen, ecse_gen, wde_reason, ecse_reason) else PREDICTED_AND_FROZEN,
            tier=tier,
            scope=scope,
            complete=False,
            available=available,
            unavailable=unavailable,
            freeze=freeze,
            note="PARTIAL_PREDICTION — not all components available",
        )

    if wde_reason == "existing_prediction" and ecse_reason == "existing_snapshot":
        return _eligible(
            fixture,
            lifecycle_status=ALREADY_FROZEN_IDEMPOTENT_REUSE,
            tier=tier,
            scope=scope,
            complete=True,
            available=["wde", "ecse"],
            unavailable=[],
            freeze=freeze,
            note="Existing prematch outputs reused",
        )

    dq = float((wde_detail or {}).get("data_quality") or 0)
    if dq and dq < 0.35:
        return _blocked(
            fixture,
            NO_BET_LOW_DATA_QUALITY,
            "Data quality below minimum threshold",
            tier=tier,
            scope=scope,
        )

    reason = wde_reason or ecse_reason or "not_eligible"
    return _blocked(
        fixture,
        BLOCKED_MISSING_DEPENDENCY,
        str(reason),
        tier=tier,
        scope=scope,
        missing=missing_deps,
        available=available,
        unavailable=unavailable,
    )


def complete_partial(wde_gen: bool, ecse_gen: bool, wde_reason: str | None, ecse_reason: str | None) -> bool:
    return (wde_gen or wde_reason == "existing_prediction") and (
        ecse_gen or ecse_reason == "existing_snapshot"
    )


def _base(fixture: DailyFixture, *, tier: str | None, scope: str | None) -> dict[str, Any]:
    return {
        "fixture_id": int(fixture.provider_fixture_id),
        "provider_fixture_id": int(fixture.provider_fixture_id),
        "match": f"{fixture.home_team} vs {fixture.away_team}",
        "home_team": fixture.home_team,
        "away_team": fixture.away_team,
        "competition": fixture.competition_key,
        "league": fixture.competition_key,
        "kickoff_utc": fixture.kickoff_utc,
        "kickoff_europe_vienna": _kickoff_vienna(fixture.kickoff_utc, "Europe/Vienna"),
        "fixture_status": fixture.status,
        "validation_tier": tier,
        "intended_prediction_scope": scope,
        "discovery_source": ",".join(fixture.coverage_sources or ["unknown"]),
        "is_tier_a": is_tier_a_competition(fixture.competition_key),
    }


def _blocked(
    fixture: DailyFixture,
    lifecycle_status: str,
    reason: str,
    *,
    tier: str | None,
    scope: str | None,
    missing: list[str] | None = None,
    available: list[str] | None = None,
    unavailable: list[str] | None = None,
    odds_freshness: dict | None = None,
) -> dict[str, Any]:
    out = _base(fixture, tier=tier, scope=scope)
    out.update(
        {
            "eligible": False,
            "eligibility_status": lifecycle_status,
            "lifecycle_status": lifecycle_status,
            "eligibility_reason": reason,
            "missing_dependencies": missing or [],
            "available_components": available or [],
            "unavailable_components": unavailable or [],
            "data_quality": None,
            "odds_freshness": odds_freshness,
            "allowed_prediction_scope": None,
            "prediction_completeness": "NONE",
        }
    )
    return out


def _eligible(
    fixture: DailyFixture,
    *,
    lifecycle_status: str,
    tier: str | None,
    scope: str | None,
    complete: bool,
    available: list[str],
    unavailable: list[str],
    freeze: dict | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    out = _base(fixture, tier=tier, scope=scope)
    out.update(
        {
            "eligible": True,
            "eligibility_status": lifecycle_status,
            "lifecycle_status": lifecycle_status,
            "eligibility_reason": note or lifecycle_status,
            "missing_dependencies": unavailable,
            "available_components": available,
            "unavailable_components": unavailable,
            "data_quality": (freeze or {}).get("data_quality_score"),
            "odds_freshness": None,
            "allowed_prediction_scope": scope,
            "prediction_completeness": "FULL" if complete else "PARTIAL",
            "freeze_id": (freeze or {}).get("freeze_id"),
            "freeze_reused": (freeze or {}).get("reused"),
        }
    )
    return out


def build_eligibility_manifest(
    fixtures: list[DailyFixture],
    completeness_map: dict[int, FixtureCompletenessReport],
    prediction_by_fixture: dict[int, dict[str, Any]],
    *,
    timezone: str = "Europe/Vienna",
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for fx in fixtures:
        fid = int(fx.provider_fixture_id)
        pred = prediction_by_fixture.get(fid, {})
        rows.append(
            classify_lifecycle_status(
                fx,
                completeness=completeness_map.get(fid),
                wde_detail=pred.get("wde"),
                ecse_detail=pred.get("ecse"),
                freeze_capture=pred.get("freeze"),
            )
        )
    return rows
