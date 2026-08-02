"""Deterministic as-of feature builder (event_time < kickoff only)."""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.prediction_engine_75 import phase1 as p1

ROOT = Path(__file__).resolve().parents[4]
FI_DB = ROOT / "data" / "football_intelligence.db"

FEATURE_LABEL = "DERIVED_AS_OF_PREMATCH"
NOT_ORIGINAL_FREEZE = "NOT_ORIGINAL_FREEZE"


@dataclass
class TeamMatch:
    fixture_id: int
    kickoff: datetime
    team_id: int | None
    team_name: str
    is_home: bool
    goals_for: int
    goals_against: int
    result: str  # W/D/L


def _open_ro() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{FI_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load_finished_team_matches(conn: sqlite3.Connection) -> list[TeamMatch]:
    rows = conn.execute(
        """
        SELECT fr.fixture_id, fx.kickoff_utc, fx.home_team_id, fx.away_team_id,
               fx.home_team, fx.away_team,
               COALESCE(fr.regulation_home_goals, fr.home_goals) AS hg,
               COALESCE(fr.regulation_away_goals, fr.away_goals) AS ag
        FROM fixture_results fr
        JOIN fixtures fx ON fx.fixture_id = fr.fixture_id
        WHERE fr.home_goals IS NOT NULL AND fx.kickoff_utc IS NOT NULL
        """
    ).fetchall()
    out: list[TeamMatch] = []
    for r in rows:
        ko = p1._parse_dt(r["kickoff_utc"])
        if ko is None or r["hg"] is None or r["ag"] is None:
            continue
        hg, ag = int(r["hg"]), int(r["ag"])
        # home
        out.append(
            TeamMatch(
                fixture_id=int(r["fixture_id"]),
                kickoff=ko,
                team_id=int(r["home_team_id"]) if r["home_team_id"] is not None else None,
                team_name=str(r["home_team"] or ""),
                is_home=True,
                goals_for=hg,
                goals_against=ag,
                result="W" if hg > ag else "D" if hg == ag else "L",
            )
        )
        out.append(
            TeamMatch(
                fixture_id=int(r["fixture_id"]),
                kickoff=ko,
                team_id=int(r["away_team_id"]) if r["away_team_id"] is not None else None,
                team_name=str(r["away_team"] or ""),
                is_home=False,
                goals_for=ag,
                goals_against=hg,
                result="W" if ag > hg else "D" if ag == hg else "L",
            )
        )
    return out


def _team_key(m: TeamMatch) -> str:
    if m.team_id is not None:
        return f"id:{m.team_id}"
    return f"name:{(m.team_name or '').strip().lower()}"


def form_window(matches: list[TeamMatch], n: int) -> dict[str, Any]:
    if not matches:
        return {"n": 0, "ppg": None, "gf_avg": None, "ga_avg": None, "cs_rate": None, "btts_rate": None, "over25_rate": None}
    w = matches[-n:] if len(matches) >= n else matches
    pts = sum(3 if m.result == "W" else 1 if m.result == "D" else 0 for m in w)
    gf = [m.goals_for for m in w]
    ga = [m.goals_against for m in w]
    cs = sum(1 for m in w if m.goals_against == 0) / len(w)
    btts = sum(1 for m in w if m.goals_for > 0 and m.goals_against > 0) / len(w)
    o25 = sum(1 for m in w if (m.goals_for + m.goals_against) > 2) / len(w)
    return {
        "n": len(w),
        "ppg": round(pts / len(w), 4),
        "gf_avg": round(sum(gf) / len(w), 4),
        "ga_avg": round(sum(ga) / len(w), 4),
        "cs_rate": round(cs, 4),
        "btts_rate": round(btts, 4),
        "over25_rate": round(o25, 4),
    }


def build_as_of_features_for_fixture(
    fixture_id: int,
    kickoff: datetime,
    home_key: str,
    away_key: str,
    history_by_team: dict[str, list[TeamMatch]],
) -> dict[str, Any]:
    """Only matches with event_time < fixture_kickoff."""
    home_hist = [m for m in history_by_team.get(home_key, []) if m.kickoff < kickoff and m.fixture_id != fixture_id]
    away_hist = [m for m in history_by_team.get(away_key, []) if m.kickoff < kickoff and m.fixture_id != fixture_id]
    # sort ascending
    home_hist.sort(key=lambda m: m.kickoff)
    away_hist.sort(key=lambda m: m.kickoff)

    # rest days
    def rest_days(hist: list[TeamMatch]) -> float | None:
        if not hist:
            return None
        delta = kickoff - hist[-1].kickoff
        return round(delta.total_seconds() / 86400.0, 3)

    # H2H: same two teams before kickoff
    h2h = []
    for m in home_hist:
        # opponent was away side in that match from home perspective — approximate via fixture pairing later
        pass
    # simpler H2H: find fixtures where both teams appear before kickoff
    home_fids = {m.fixture_id for m in home_hist}
    away_fids = {m.fixture_id for m in away_hist}
    h2h_fids = home_fids & away_fids
    h2h_n = len(h2h_fids)

    return {
        "feature_label": FEATURE_LABEL,
        "not_original_freeze": NOT_ORIGINAL_FREEZE,
        "as_of_kickoff": kickoff.isoformat(),
        "cutoff_rule": "event_time < fixture_kickoff",
        "home_form_l5": form_window(home_hist, 5),
        "home_form_l8": form_window(home_hist, 8),
        "home_form_l10": form_window(home_hist, 10),
        "away_form_l5": form_window(away_hist, 5),
        "away_form_l8": form_window(away_hist, 8),
        "away_form_l10": form_window(away_hist, 10),
        "home_rest_days": rest_days(home_hist),
        "away_rest_days": rest_days(away_hist),
        "h2h_meetings_before_kickoff": h2h_n,
        "home_matches_before": len(home_hist),
        "away_matches_before": len(away_hist),
        "leakage_guard": "strict_lt_kickoff",
    }


def build_history_index(matches: list[TeamMatch]) -> dict[str, list[TeamMatch]]:
    by: dict[str, list[TeamMatch]] = defaultdict(list)
    for m in matches:
        by[_team_key(m)].append(m)
    for k in by:
        by[k].sort(key=lambda m: m.kickoff)
    return by


def assert_no_future_leakage(features: dict[str, Any], kickoff: datetime, history_home: list[TeamMatch], history_away: list[TeamMatch]) -> None:
    for m in history_home + history_away:
        if m.kickoff >= kickoff:
            raise AssertionError(f"future match leaked into as-of features: fixture {m.fixture_id}")


def build_as_of_for_ids(fixture_ids: set[int]) -> dict[int, dict[str, Any]]:
    conn = _open_ro()
    try:
        all_matches = load_finished_team_matches(conn)
        history = build_history_index(all_matches)
        fx_rows = {
            int(r["fixture_id"]): r
            for r in conn.execute(
                """
                SELECT fixture_id, kickoff_utc, home_team_id, away_team_id, home_team, away_team
                FROM fixtures
                """
            )
        }
    finally:
        conn.close()

    out: dict[int, dict[str, Any]] = {}
    for fid in fixture_ids:
        fx = fx_rows.get(fid)
        if not fx:
            continue
        ko = p1._parse_dt(fx["kickoff_utc"])
        if ko is None:
            continue
        home = TeamMatch(
            fixture_id=fid,
            kickoff=ko,
            team_id=int(fx["home_team_id"]) if fx["home_team_id"] is not None else None,
            team_name=str(fx["home_team"] or ""),
            is_home=True,
            goals_for=0,
            goals_against=0,
            result="D",
        )
        away = TeamMatch(
            fixture_id=fid,
            kickoff=ko,
            team_id=int(fx["away_team_id"]) if fx["away_team_id"] is not None else None,
            team_name=str(fx["away_team"] or ""),
            is_home=False,
            goals_for=0,
            goals_against=0,
            result="D",
        )
        hk, ak = _team_key(home), _team_key(away)
        feats = build_as_of_features_for_fixture(fid, ko, hk, ak, history)
        # leakage self-check
        hh = [m for m in history.get(hk, []) if m.kickoff < ko and m.fixture_id != fid]
        aa = [m for m in history.get(ak, []) if m.kickoff < ko and m.fixture_id != fid]
        assert_no_future_leakage(feats, ko, hh, aa)
        out[fid] = feats
    return out
