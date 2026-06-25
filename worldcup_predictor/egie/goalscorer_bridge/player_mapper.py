"""Player mapping for bridged API-Football goalscorer odds."""

from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd
from sqlalchemy import text

from worldcup_predictor.database.postgres.session import postgres_configured, session_scope
from worldcup_predictor.egie.goalscorer_bridge.team_mapper import side_for_market
from worldcup_predictor.egie.goalscorer_odds_mapping.mapper import PlayerOddsMapper
from worldcup_predictor.egie.goalscorer_odds_mapping.models import (
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_UNMAPPED,
    MappedOddsSelection,
    MappingSummary,
    RawOddsSelection,
    USABLE_CONFIDENCES,
)


class BridgedPlayerOddsMapper(PlayerOddsMapper):
    """Extend 54M mapper with team-side constraint for Home/Away GS markets."""

    def __init__(
        self,
        lineup_df: pd.DataFrame,
        *,
        home_team_id: int | None = None,
        away_team_id: int | None = None,
    ) -> None:
        super().__init__(lineup_df)
        self._home_team_id = home_team_id
        self._away_team_id = away_team_id

    def _filtered_candidates(self, fixture_id: int, market: str) -> list[dict[str, Any]]:
        candidates = self._candidates(fixture_id)
        side = side_for_market(market)
        if side == "home" and self._home_team_id is not None:
            return [c for c in candidates if c.get("team_id") == self._home_team_id]
        if side == "away" and self._away_team_id is not None:
            return [c for c in candidates if c.get("team_id") == self._away_team_id]
        return candidates

    def map_selection(self, row: RawOddsSelection) -> tuple[MappedOddsSelection | None, str]:
        candidates = self._filtered_candidates(row.sportmonks_fixture_id, row.market)
        if not candidates:
            return None, CONFIDENCE_UNMAPPED

        original = self._by_fixture.get(int(row.sportmonks_fixture_id), [])
        self._by_fixture[int(row.sportmonks_fixture_id)] = candidates
        try:
            return super().map_selection(row)
        finally:
            self._by_fixture[int(row.sportmonks_fixture_id)] = original


def load_lineup_df_for_fixtures(sportmonks_fixture_ids: list[int]) -> pd.DataFrame:
    if not sportmonks_fixture_ids or not postgres_configured():
        return pd.DataFrame()

    ids = ",".join(str(int(x)) for x in sportmonks_fixture_ids)
    with session_scope() as session:
        rows = session.execute(
            text(
                f"""
                SELECT sportmonks_fixture_id, player_id, player_name, team_id, starter
                FROM fs_player_match_stats
                WHERE sportmonks_fixture_id IN ({ids})
                """
            )
        ).mappings().all()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([dict(r) for r in rows])
    df["target_anytime"] = 0
    return df


def map_bridged_odds(
    raw_rows: list[RawOddsSelection],
    lineup_df: pd.DataFrame,
    bridges: list[Any],
) -> tuple[list[MappedOddsSelection], list[dict[str, Any]], MappingSummary, dict[str, Any]]:
    bridge_by_sm: dict[int, Any] = {}
    for b in bridges:
        sm = getattr(b, "sportmonks_fixture_id", None) or (b.get("sportmonks_fixture_id") if isinstance(b, dict) else None)
        if sm:
            bridge_by_sm[int(sm)] = b

    mapper_cache: dict[int, BridgedPlayerOddsMapper] = {}

    def _mapper_for(row: RawOddsSelection) -> BridgedPlayerOddsMapper:
        fid = int(row.sportmonks_fixture_id)
        if fid not in mapper_cache:
            bridge = bridge_by_sm.get(fid)
            home_tid = away_tid = None
            if bridge is not None:
                home_tid = getattr(bridge, "home_team_id", None) or (bridge.get("home_team_id") if isinstance(bridge, dict) else None)
                away_tid = getattr(bridge, "away_team_id", None) or (bridge.get("away_team_id") if isinstance(bridge, dict) else None)
            mapper_cache[fid] = BridgedPlayerOddsMapper(
                lineup_df,
                home_team_id=int(home_tid) if home_tid else None,
                away_team_id=int(away_tid) if away_tid else None,
            )
        return mapper_cache[fid]

    mapped: list[MappedOddsSelection] = []
    unmapped: list[dict[str, Any]] = []
    conf_counter: Counter[str] = Counter()
    reason_counter: Counter[str] = Counter()

    for row in raw_rows:
        result, conf = _mapper_for(row).map_selection(row)
        conf_counter[conf] += 1
        if result is None:
            unmapped.append({**row.to_dict(), "mapping_confidence": CONFIDENCE_UNMAPPED, "reason": "no_match"})
            reason_counter["no_match"] += 1
            continue
        if result.mapping_confidence not in USABLE_CONFIDENCES:
            unmapped.append({**result.to_dict(), **row.to_dict(), "reason": "low_confidence_rejected"})
            reason_counter["low_confidence"] += 1
            continue
        mapped.append(result)

    total = len(raw_rows)
    summary = MappingSummary(
        selection_count=total,
        mapped_count=len(mapped),
        unmapped_count=len(unmapped),
        mapping_rate=round(len(mapped) / total, 4) if total else 0.0,
        confidence_high=sum(1 for m in mapped if m.mapping_confidence == CONFIDENCE_HIGH),
        confidence_medium=sum(1 for m in mapped if m.mapping_confidence == CONFIDENCE_MEDIUM),
    )
    diagnostics = {
        "confidence_distribution": dict(conf_counter),
        "unmapped_reasons": dict(reason_counter.most_common(10)),
    }
    return mapped, unmapped, summary, diagnostics
