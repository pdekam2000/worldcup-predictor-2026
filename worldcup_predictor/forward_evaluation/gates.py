"""Phase 7B Part B — Data quality and odds gates."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.forward_evaluation.constants import (
    DATA_QUALITY_BLOCKED,
    ECSE_UNAVAILABLE,
    ELIGIBLE,
    ODDS_MISSING,
    ODDS_STALE,
    UNSUPPORTED,
    WDE_UNAVAILABLE,
)
from worldcup_predictor.gpt_actions.competition_normalize import is_friendly_competition
from worldcup_predictor.gpt_actions.owner_scope import fixture_allowed_for_prediction, fixture_tier
from worldcup_predictor.gpt_actions.delegation import _match_odds
from worldcup_predictor.gpt_actions.owner_odds import controlled_owner_odds_lookup
from worldcup_predictor.owner.euro_b_fixture_selector import UefaFixtureSelection, odds_readiness_audit
from worldcup_predictor.odds.freshness_metadata import build_fixture_freshness_metadata
from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture


def classify_candidate(
    conn,
    *,
    fixture: dict[str, Any],
    settings,
) -> tuple[str, dict[str, Any]]:
    """Return gate status and audit detail."""
    fid = int(fixture["fixture_id"])
    comp_key = str(fixture.get("competition_raw") or fixture.get("competition") or "")
    tier = fixture.get("tier") or fixture_tier(comp_key)
    detail: dict[str, Any] = {
        "fixture_id": fid,
        "competition": fixture.get("competition"),
        "tier": tier,
        "mapping_quality": fixture.get("mapping_quality"),
    }

    if is_friendly_competition(comp_key):
        return UNSUPPORTED, {**detail, "reason": "friendlies_blocked"}
    allowed, reason = fixture_allowed_for_prediction(comp_key, prediction_scope="owner")
    if not allowed and tier not in ("A", "B"):
        return UNSUPPORTED, {**detail, "reason": reason or "unsupported_competition"}
    if tier not in ("A", "B"):
        return UNSUPPORTED, {**detail, "reason": "unsupported_tier"}

    row = conn.execute(
        "SELECT fixture_id, kickoff_utc, status, round_name, season FROM fixtures WHERE fixture_id=?",
        (fid,),
    ).fetchone()
    if not row:
        return UNSUPPORTED, {**detail, "reason": "fixture_not_in_db"}

    sel = UefaFixtureSelection(
        fixture_id=fid,
        provider_fixture_id=fid,
        competition_key=comp_key,
        home_team=str(fixture.get("home_team") or ""),
        away_team=str(fixture.get("away_team") or ""),
        kickoff_utc=str(fixture.get("kickoff_utc") or row["kickoff_utc"] or ""),
        status=str(fixture.get("status") or row["status"] or "NS"),
        provider_source="api-football",
        crosswalk_confidence=1.0,
        crosswalk_status="canonical_api",
        has_odds=False,
        has_wde=False,
        has_ecse=False,
    )
    audit = odds_readiness_audit(conn, sel)
    detail["odds_audit"] = audit

    if not audit.get("has_odds"):
        return ODDS_MISSING, {**detail, "reason": "no_odds"}
    if not audit.get("lambda_inputs_available"):
        return ECSE_UNAVAILABLE, {**detail, "reason": "missing_lambda_inputs"}

    freshness = build_fixture_freshness_metadata(
        conn,
        fixture_id=fid,
        kickoff_utc=sel.kickoff_utc,
        round_name=row["round_name"] if row else None,
        status=sel.status,
    )
    detail["odds_freshness"] = freshness
    if freshness.get("requires_fresh_odds"):
        return ODDS_STALE, {**detail, "reason": "stale_odds"}

    if tier == "B":
        daily = DailyFixture(
            fixture_id=fid,
            provider_fixture_id=fid,
            competition_key=comp_key,
            home_team=str(fixture.get("home_team") or ""),
            away_team=str(fixture.get("away_team") or ""),
            kickoff_utc=sel.kickoff_utc,
            status=sel.status,
            season=int(row["season"]) if row and row["season"] is not None else None,
        )
        odds_meta = controlled_owner_odds_lookup(
            daily, tier="B", settings=settings, budget=None, allow_provider=False
        )
        bm = int(odds_meta.get("bookmaker_count") or 0)
        detail["odds_meta"] = odds_meta
    else:
        odds = _match_odds(conn, fid)
        bm = int(odds.get("bookmaker_count") or 0)
        detail["odds_meta"] = odds

    if bm <= 0:
        return ODDS_MISSING, {**detail, "reason": "zero_bookmakers"}

    if not settings.api_football_configured:
        return WDE_UNAVAILABLE, {**detail, "reason": "api_football_not_configured"}

    dq = freshness.get("odds_freshness_status") or freshness.get("freshness_flag")
    if str(dq or "").upper() in {"INVALID", "MISSING", "BLOCKED"}:
        return DATA_QUALITY_BLOCKED, {**detail, "reason": "data_quality_blocked"}

    detail["bookmaker_count"] = bm
    return ELIGIBLE, detail
