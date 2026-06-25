"""Map goalscorer odds selection names to player_id."""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

import pandas as pd

from worldcup_predictor.egie.goalscorer_odds_mapping.models import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_UNMAPPED,
    MappedOddsSelection,
    MappingSummary,
    RawOddsSelection,
)
from worldcup_predictor.egie.goalscorer_odds_mapping.name_normalizer import (
    compact_key,
    first_initial_last,
    last_name,
    name_tokens,
    normalize_name,
)


class PlayerOddsMapper:
    """Map odds selection_name -> player_id using lineup context."""

    def __init__(self, lineup_df: pd.DataFrame) -> None:
        self._by_fixture: dict[int, list[dict[str, Any]]] = {}
        for fid, grp in lineup_df.groupby("sportmonks_fixture_id"):
            players = []
            for _, row in grp.iterrows():
                players.append({
                    "player_id": int(row["player_id"]),
                    "player_name": str(row.get("player_name") or ""),
                    "team_id": int(row["team_id"]) if pd.notna(row.get("team_id")) else None,
                    "starter": bool(row.get("starter")),
                })
            self._by_fixture[int(fid)] = players

    def _candidates(self, fixture_id: int) -> list[dict[str, Any]]:
        return self._by_fixture.get(int(fixture_id), [])

    def map_selection(self, row: RawOddsSelection) -> tuple[MappedOddsSelection | None, str]:
        candidates = self._candidates(row.sportmonks_fixture_id)
        if not candidates:
            return None, CONFIDENCE_UNMAPPED

        selection = row.selection_name.strip()
        sel_norm = normalize_name(selection)
        sel_compact = compact_key(selection)
        sel_tokens = name_tokens(selection)
        sel_last = last_name(selection)

        best: tuple[dict[str, Any], str, float] | None = None

        for cand in candidates:
            pname = cand["player_name"]
            pnorm = normalize_name(pname)
            pcompact = compact_key(pname)
            ptokens = name_tokens(pname)

            # exact
            if selection.lower() == pname.lower() or sel_norm == pnorm:
                return self._mapped(row, cand, CONFIDENCE_HIGH, "exact", 1.0), CONFIDENCE_HIGH
            if sel_compact == pcompact and sel_compact:
                return self._mapped(row, cand, CONFIDENCE_HIGH, "normalized_exact", 0.99), CONFIDENCE_HIGH

            # last name + first initial
            if sel_last and sel_last == last_name(pname):
                sel_fi = first_initial_last(selection)
                p_fi = first_initial_last(pname)
                if sel_fi == p_fi:
                    best = (cand, "initial_last", 0.95)
                    continue

            # token overlap (team surname match)
            if sel_last and len(sel_last) >= 4 and sel_last in pnorm:
                overlap = len(sel_tokens & ptokens) / max(len(sel_tokens | ptokens), 1)
                if overlap >= 0.5:
                    score = 0.88 + 0.1 * overlap
                    if best is None or score > best[2]:
                        best = (cand, "token_overlap", score)

            # fuzzy full
            ratio = SequenceMatcher(None, sel_norm, pnorm).ratio()
            if ratio >= 0.92:
                if best is None or ratio > best[2]:
                    best = (cand, "fuzzy_high", ratio)
            elif ratio >= 0.85:
                if best is None or ratio > best[2]:
                    best = (cand, "fuzzy_medium", ratio)

        if best is None:
            return None, CONFIDENCE_UNMAPPED

        cand, method, score = best
        if score >= 0.92 or method in ("exact", "normalized_exact", "initial_last"):
            conf = CONFIDENCE_HIGH if score >= 0.95 else CONFIDENCE_MEDIUM
        elif score >= 0.85:
            conf = CONFIDENCE_MEDIUM
        else:
            conf = CONFIDENCE_LOW

        return self._mapped(row, cand, conf, method, score), conf

    def _mapped(
        self,
        row: RawOddsSelection,
        cand: dict[str, Any],
        confidence: str,
        method: str,
        score: float,
    ) -> MappedOddsSelection:
        return MappedOddsSelection(
            sportmonks_fixture_id=row.sportmonks_fixture_id,
            player_id=int(cand["player_id"]),
            player_name=str(cand["player_name"]),
            selection_name=row.selection_name,
            market=row.market,
            bookmaker=row.bookmaker,
            odds=row.odds,
            implied_probability=row.implied_probability,
            mapping_confidence=confidence,
            mapping_method=method,
            mapping_score=round(score, 4),
        )


def map_all_selections(
    raw_rows: list[RawOddsSelection],
    lineup_df: pd.DataFrame,
    *,
    include_low: bool = False,
) -> tuple[list[MappedOddsSelection], list[dict[str, Any]], MappingSummary]:
    mapper = PlayerOddsMapper(lineup_df)
    mapped: list[MappedOddsSelection] = []
    unmapped: list[dict[str, Any]] = []
    conf_counter = {CONFIDENCE_HIGH: 0, CONFIDENCE_MEDIUM: 0, CONFIDENCE_LOW: 0, CONFIDENCE_UNMAPPED: 0}

    for row in raw_rows:
        result, conf = mapper.map_selection(row)
        conf_counter[conf] += 1
        if result is None:
            unmapped.append({**row.to_dict(), "mapping_confidence": CONFIDENCE_UNMAPPED})
            continue
        if result.mapping_confidence == CONFIDENCE_LOW and not include_low:
            unmapped.append({**result.to_dict(), **row.to_dict(), "reason": "low_confidence_rejected"})
            conf_counter[CONFIDENCE_UNMAPPED] += 1
            conf_counter[CONFIDENCE_LOW] -= 1
            continue
        mapped.append(result)

    total = len(raw_rows)
    summary = MappingSummary(
        selection_count=total,
        mapped_count=len(mapped),
        unmapped_count=len(unmapped),
        mapping_rate=round(len(mapped) / total, 4) if total else 0.0,
        confidence_high=conf_counter[CONFIDENCE_HIGH],
        confidence_medium=conf_counter[CONFIDENCE_MEDIUM],
        confidence_low=conf_counter[CONFIDENCE_LOW],
    )
    return mapped, unmapped, summary
