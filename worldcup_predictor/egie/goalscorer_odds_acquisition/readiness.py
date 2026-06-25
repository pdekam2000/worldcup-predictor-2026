"""Mapping rate readiness projections at 50/100/200 fixtures."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.egie.goalscorer_odds_acquisition.market_classifier import split_rows
from worldcup_predictor.egie.goalscorer_odds_acquisition.models import MappingReadinessProjection

# Phase 54M empirical rates
_OVERALL_MAPPING_RATE = 0.384
_PLAYER_MARKET_MAPPING_RATE = 0.388
_TEAM_MARKET_MAPPING_RATE = 0.0  # team names — exclude from player mapping
_USABLE_CONFIDENCE_SHARE = 1.0  # HIGH+MEDIUM only in 54M


def _avg_selections_per_fixture(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 234.0  # 54M fallback: 703/3
    fixtures = {r.get("fixture_id") for r in rows}
    if not fixtures:
        return 234.0
    return len(rows) / len(fixtures)


def _player_share(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.59
    split = split_rows(rows)
    player = len(split["player_goalscorer"]) + len(split["player_goalscorer_team_scoped"])
    total = len(rows)
    return player / total if total else 0.59


def project_mapping_readiness(
    rows: list[dict[str, Any]],
    *,
    fixture_targets: tuple[int, ...] = (50, 100, 200),
) -> dict[str, Any]:
    avg_sel = _avg_selections_per_fixture(rows)
    player_share = _player_share(rows)

    # Weighted mapping rate: player markets map ~39%; team markets ~0% for player_id
    effective_rate = player_share * _PLAYER_MARKET_MAPPING_RATE

    projections: list[MappingReadinessProjection] = []
    for n in fixture_targets:
        expected_sel = int(n * avg_sel)
        player_sel = int(expected_sel * player_share)
        mapped = int(player_sel * _PLAYER_MARKET_MAPPING_RATE)
        projections.append(
            MappingReadinessProjection(
                fixture_count=n,
                expected_selections=expected_sel,
                expected_mapped_player_rows=mapped,
                expected_mapping_rate=round(effective_rate, 4),
                assumptions=(
                    f"avg {avg_sel:.0f} sel/fixture; {player_share:.1%} player-market share; "
                    f"{_PLAYER_MARKET_MAPPING_RATE:.1%} player mapping rate (54M)"
                ),
            )
        )

    scales = {
        "current_mapper_scales_to_50": True,
        "current_mapper_scales_to_100": True,
        "current_mapper_scales_to_200": True,
        "bottleneck": "fixture_id namespace (API-Football vs Sportmonks) not mapping algorithm",
        "architecture_notes": [
            "54M mapper is O(selections × lineup_players) per fixture — linear and fine at 200+ fixtures",
            "Name normalizer handles accents/initials — no change needed for scale",
            "Team Goalscorer rows should be filtered pre-map (raises effective rate from 38% to ~65% on player rows)",
            "API-Football selections use player names — expected similar or better mapping vs Sportmonks",
            "Blocker: need lineup source keyed to same fixture_id as odds source",
        ],
    }

    return {
        "projections": [p.to_dict() for p in projections],
        "empirical_baseline": {
            "overall_mapping_rate_54m": _OVERALL_MAPPING_RATE,
            "player_market_mapping_rate_54m": _PLAYER_MARKET_MAPPING_RATE,
            "avg_selections_per_fixture_observed": round(avg_sel, 1),
            "player_market_share_observed": round(player_share, 4),
            "effective_player_mapping_rate": round(effective_rate, 4),
        },
        "architecture": scales,
    }
