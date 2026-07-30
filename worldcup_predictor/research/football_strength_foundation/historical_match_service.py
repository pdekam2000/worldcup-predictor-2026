"""Leakage-safe historical match query service (research + future infra)."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable

from worldcup_predictor.research.football_strength_foundation.leakage_assertions import (
    raise_if_leaks,
    validate_history_row,
)
from worldcup_predictor.research.lambda_team_strength.metrics import normalize_team, team_match_keys
from worldcup_predictor.research.lambda_team_strength.team_strength import (
    MatchRecord,
    TeamStrengthStore,
    load_strength_store,
    resolve_team_key,
)


TERMINAL_OK = {"ft", "finished", "match finished", "aet", "pen", "after pen", "aet/pen", ""}
EXCLUDED_STATUS = {
    "postponed",
    "cancelled",
    "canceled",
    "abandoned",
    "awarded",
    "walkover",
    "deleted",
    "ns",
    "tbd",
    "scheduled",
    "not started",
}


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    t = str(s).strip().replace("T", " ").replace("Z", "")
    for n, fmt in ((19, "%Y-%m-%d %H:%M:%S"), (16, "%Y-%m-%d %H:%M"), (10, "%Y-%m-%d")):
        try:
            return datetime.strptime(t[:n], fmt if n > 10 else "%Y-%m-%d")
        except Exception:
            continue
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


@dataclass
class HistoricalMatch:
    kickoff: datetime
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int
    league: str
    season: str
    source: str
    fixture_key: str | None = None
    status: str = "ft"


@dataclass
class HistoryQueryResult:
    matches: list[HistoricalMatch]
    team_key: str
    cutoff: datetime
    window: int
    duplicates_removed: int
    leakage_checks_passed: bool
    query_hash: str


class HistoricalMatchService:
    """Reusable leakage-safe history lookups."""

    def __init__(self, store: TeamStrengthStore | None = None, fi_path: str | None = None):
        if store is not None:
            self.store = store
        else:
            if not fi_path:
                raise ValueError("fi_path or store required")
            self.store = load_strength_store(fi_path)

    def resolve_team(self, name: str) -> str:
        return resolve_team_key(self.store, name)

    def matches_for_team(
        self,
        team_name: str,
        cutoff: datetime,
        *,
        window: int = 40,
        target_fixture_id: int | None = None,
        home_away: str | None = None,  # home | away | None
        assert_leakage: bool = True,
    ) -> HistoryQueryResult:
        key = self.resolve_team(team_name)
        raw = self.store.by_team.get(key, [])
        selected: list[HistoricalMatch] = []
        seen: set[str] = set()
        dup = 0
        for m in raw:
            if m.kickoff >= cutoff:
                continue
            # home/away filter
            if home_away == "home" and m.home_norm != key:
                continue
            if home_away == "away" and m.away_norm != key:
                continue
            fk = f"{m.registry_id or ''}|{m.kickoff.isoformat()}|{m.home_norm}|{m.away_norm}"
            if fk in seen:
                dup += 1
                continue
            seen.add(fk)
            if assert_leakage:
                viol = validate_history_row(
                    hist_kickoff=m.kickoff,
                    cutoff=cutoff,
                    hist_fixture_id=m.registry_id,
                    target_fixture_id=target_fixture_id,
                )
                raise_if_leaks(viol)
            selected.append(
                HistoricalMatch(
                    kickoff=m.kickoff,
                    home_team=m.home_norm,
                    away_team=m.away_norm,
                    home_goals=m.home_goals,
                    away_goals=m.away_goals,
                    league=m.league,
                    season=m.season,
                    source="strength_store",
                    fixture_key=fk,
                )
            )
        selected.sort(key=lambda x: x.kickoff)
        if window:
            selected = selected[-window:]
        payload = f"{key}|{cutoff.isoformat()}|{window}|{home_away}|{len(selected)}"
        qh = hashlib.sha256(payload.encode()).hexdigest()[:16]
        return HistoryQueryResult(
            matches=selected,
            team_key=key,
            cutoff=cutoff,
            window=window,
            duplicates_removed=dup,
            leakage_checks_passed=True,
            query_hash=qh,
        )
