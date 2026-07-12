"""Build prematch snapshots from provider responses and stored enrichment."""

from __future__ import annotations

import json
from typing import Any

from worldcup_predictor.provider_features.models import PrematchFeatureSnapshot
from worldcup_predictor.provider_features.timestamp_policy import (
    LeakageStatus,
    classify_timing,
    default_prediction_cutoff,
    utc_now_iso,
)


def _lineup_summary(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, list):
        return {"starter_count": 0, "lineup_status": "unknown"}
    starters = 0
    for team in payload:
        if not isinstance(team, dict):
            continue
        xi = team.get("startXI") or team.get("start_xi") or []
        if isinstance(xi, list):
            starters += len(xi)
    status = "confirmed" if starters >= 22 else ("partial" if starters > 0 else "missing")
    return {"starter_count": starters, "lineup_status": status, "team_blocks": len(payload)}


def from_api_football_lineups(
    *,
    fixture_id: int,
    competition_key: str,
    tier: str | None,
    kickoff_utc: str,
    lineups_data: Any,
    fetched_at_utc: str,
    feature_available_at_utc: str | None,
    is_upcoming: bool,
    mapping_confidence: float = 1.0,
) -> PrematchFeatureSnapshot | None:
    summary = _lineup_summary(lineups_data)
    if summary["starter_count"] == 0:
        return None
    cutoff = default_prediction_cutoff(kickoff_utc)
    avail = feature_available_at_utc or fetched_at_utc
    status = classify_timing(
        feature_available_at_utc=avail,
        fetched_at_utc=fetched_at_utc,
        prediction_cutoff_utc=cutoff,
        kickoff_utc=kickoff_utc,
        is_live_upcoming=is_upcoming,
    )
    return PrematchFeatureSnapshot(
        fixture_id=fixture_id,
        competition_key=competition_key,
        tier=tier,
        provider="api-football",
        provider_fixture_id=fixture_id,
        feature_family="lineup",
        feature_name="starting_xi_summary",
        feature_value=summary,
        feature_available_at_utc=avail,
        fetched_at_utc=fetched_at_utc,
        prediction_cutoff_utc=cutoff,
        kickoff_utc=kickoff_utc,
        source_endpoint="fixtures/lineups",
        leakage_status=status.value,
        mapping_confidence=mapping_confidence,
        data_quality="OK" if summary["lineup_status"] == "confirmed" else "PARTIAL",
        completeness_mask={"lineup": 1},
    )


def from_api_football_injuries(
    *,
    fixture_id: int,
    competition_key: str,
    tier: str | None,
    kickoff_utc: str,
    injuries_data: Any,
    fetched_at_utc: str,
    feature_available_at_utc: str | None,
    is_upcoming: bool,
    mapping_confidence: float = 1.0,
) -> PrematchFeatureSnapshot | None:
    items = injuries_data if isinstance(injuries_data, list) else []
    if not items:
        return None
    summary = {
        "injury_count": len(items),
        "players": [
            {
                "player": (x.get("player") or {}).get("name") if isinstance(x, dict) else None,
                "type": x.get("type") if isinstance(x, dict) else None,
                "reason": x.get("reason") if isinstance(x, dict) else None,
            }
            for x in items[:30]
        ],
    }
    cutoff = default_prediction_cutoff(kickoff_utc)
    avail = feature_available_at_utc or fetched_at_utc
    status = classify_timing(
        feature_available_at_utc=avail,
        fetched_at_utc=fetched_at_utc,
        prediction_cutoff_utc=cutoff,
        kickoff_utc=kickoff_utc,
        is_live_upcoming=is_upcoming,
    )
    return PrematchFeatureSnapshot(
        fixture_id=fixture_id,
        competition_key=competition_key,
        tier=tier,
        provider="api-football",
        provider_fixture_id=fixture_id,
        feature_family="injury",
        feature_name="injury_list_summary",
        feature_value=summary,
        feature_available_at_utc=avail,
        fetched_at_utc=fetched_at_utc,
        prediction_cutoff_utc=cutoff,
        kickoff_utc=kickoff_utc,
        source_endpoint="injuries",
        leakage_status=status.value,
        mapping_confidence=mapping_confidence,
        data_quality="OK",
        completeness_mask={"injury": 1},
    )


def from_stored_enrichment_lineup(
    *,
    fixture_id: int,
    competition_key: str,
    tier: str | None,
    kickoff_utc: str,
    lineups_json: str,
    enrichment_updated_at: str,
) -> PrematchFeatureSnapshot | None:
    try:
        data = json.loads(lineups_json)
    except json.JSONDecodeError:
        return None
    fetched = utc_now_iso()
    return from_api_football_lineups(
        fixture_id=fixture_id,
        competition_key=competition_key,
        tier=tier,
        kickoff_utc=kickoff_utc,
        lineups_data=data,
        fetched_at_utc=fetched,
        feature_available_at_utc=enrichment_updated_at,
        is_upcoming=False,
        mapping_confidence=0.95,
    )


def from_sportmonks_xg_fixture(
    *,
    fixture_id: int,
    competition_key: str,
    sportmonks_fixture_id: int,
    kickoff_utc: str,
    xg_payload: Any,
    fetched_at_utc: str,
    is_upcoming: bool,
) -> PrematchFeatureSnapshot | None:
    """Store SportMonks xGFixture only when payload indicates prematch expectation."""
    if not xg_payload:
        return None
    # xGFixture on upcoming WC fixtures = prematch expectation; on completed without timestamp = reject
    summary = {"raw_type": "xGFixture", "present": True}
    cutoff = default_prediction_cutoff(kickoff_utc)
    status = classify_timing(
        feature_available_at_utc=fetched_at_utc,
        fetched_at_utc=fetched_at_utc,
        prediction_cutoff_utc=cutoff,
        kickoff_utc=kickoff_utc,
        is_live_upcoming=is_upcoming,
    )
    return PrematchFeatureSnapshot(
        fixture_id=fixture_id,
        competition_key=competition_key,
        tier="A",
        provider="sportmonks",
        provider_fixture_id=sportmonks_fixture_id,
        feature_family="xg_prematch",
        feature_name="xg_fixture_expectation",
        feature_value=summary,
        feature_available_at_utc=fetched_at_utc,
        fetched_at_utc=fetched_at_utc,
        prediction_cutoff_utc=cutoff,
        kickoff_utc=kickoff_utc,
        source_endpoint="fixtures/{id}?include=xGFixture",
        leakage_status=status.value,
        mapping_confidence=0.99,
        data_quality="PARTIAL",
        completeness_mask={"xg_prematch": 1},
        extra_values={"note": "payload_redacted_size_control"},
    )
