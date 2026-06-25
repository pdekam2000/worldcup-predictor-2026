"""Bridge audit summaries."""

from __future__ import annotations

from collections import Counter
from typing import Any

from worldcup_predictor.egie.goalscorer_bridge.models import BridgeAuditSummary, FixtureBridge
from worldcup_predictor.egie.goalscorer_odds_mapping.models import MappingSummary


def audit_fixture_bridges(bridges: list[FixtureBridge]) -> BridgeAuditSummary:
    conf = Counter(b.bridge_confidence for b in bridges)
    return BridgeAuditSummary(
        total_api_gs_fixtures=len(bridges),
        mapped=conf.get("HIGH", 0),
        partial=conf.get("MEDIUM", 0) + conf.get("LOW", 0),
        unmapped=conf.get("UNMAPPED", 0),
        with_sportmonks_lineups=sum(1 for b in bridges if b.sportmonks_lineups_available),
        confidence_high=conf.get("HIGH", 0),
        confidence_medium=conf.get("MEDIUM", 0),
    )


def merge_player_mapping_audit(
    fixture_audit: BridgeAuditSummary,
    mapping_summary: MappingSummary,
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    fixture_audit.player_mapping_rate = mapping_summary.mapping_rate
    fixture_audit.player_mapped = mapping_summary.mapped_count
    fixture_audit.player_unmapped = mapping_summary.unmapped_count
    return {
        "fixture_bridge": fixture_audit.to_dict(),
        "player_mapping": mapping_summary.to_dict(),
        "player_diagnostics": diagnostics,
    }
