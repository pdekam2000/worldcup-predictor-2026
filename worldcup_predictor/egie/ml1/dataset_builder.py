"""Build unified ML-1 datasets from SQLite + UEFA odds cache."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from worldcup_predictor.egie.uefa_club.first_goal_market_audit import parse_first_goal_markets
from worldcup_predictor.egie.uefa_club.sportmonks_ingest import cache_path, load_cache
from worldcup_predictor.goal_timing.minute_ranges import minute_to_range_key

ROOT = Path(__file__).resolve().parents[3]
DB_PATH = ROOT / "data" / "football_intelligence.db"
ARTIFACTS = ROOT / "artifacts"
UEFA_MAPPING = ARTIFACTS / "uefa_fixture_mapping.json"

LEAGUE_KEYS = ("premier_league", "bundesliga", "champions_league", "europa_league", "conference_league")


def _parse_kickoff(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        try:
            return datetime.strptime(raw[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None


def _mw_label(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "home_win"
    if home_goals < away_goals:
        return "away_win"
    return "draw"


def _load_finished_fixtures() -> list[dict[str, Any]]:
    if not DB_PATH.is_file():
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT f.fixture_id, f.competition_key, f.home_team, f.away_team, f.kickoff_utc,
               r.home_goals, r.away_goals, r.total_goals, r.winner
        FROM fixtures f
        JOIN fixture_results r ON r.fixture_id = f.fixture_id
        WHERE f.is_placeholder = 0
          AND f.status IN ('FT', 'AET', 'PEN', 'FINISHED')
          AND r.home_goals IS NOT NULL AND r.away_goals IS NOT NULL
        ORDER BY f.kickoff_utc ASC
        """
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _load_first_goals() -> dict[int, dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT e.fixture_id, e.minute, e.extra_minute, e.team, f.home_team, f.away_team
        FROM fixture_goal_events e
        JOIN fixtures f ON f.fixture_id = e.fixture_id
        WHERE e.sort_index = 0
        """
    ).fetchall()
    conn.close()
    out: dict[int, dict[str, Any]] = {}
    for r in rows:
        fid = int(r["fixture_id"])
        team = str(r["team"] or "")
        home = str(r["home_team"] or "")
        away = str(r["away_team"] or "")
        minute = int(r["minute"] or 0) + int(r["extra_minute"] or 0)
        if team == home:
            side = "home"
        elif team == away:
            side = "away"
        else:
            side = "unknown"
        out[fid] = {
            "first_goal_team_side": side,
            "first_goal_minute": minute,
            "goal_range": minute_to_range_key(minute),
        }
    return out


def _parse_api_odds_payload(payload: dict[str, Any]) -> dict[str, float | None]:
    """Extract implied MW / BTTS / O2.5 from API-Football odds snapshot."""
    out: dict[str, float | None] = {
        "odds_mw_home": None,
        "odds_mw_draw": None,
        "odds_mw_away": None,
        "odds_btts_yes": None,
        "odds_btts_no": None,
        "odds_over_25": None,
        "odds_under_25": None,
    }
    api = payload.get("api_sports") or {}
    bookmakers = api.get("bookmakers") or api.get("response") or []
    if isinstance(bookmakers, dict):
        bookmakers = bookmakers.get("bookmakers") or []
    if not isinstance(bookmakers, list):
        return out

    def _impl(odd: Any) -> float | None:
        try:
            v = float(odd)
            return round(1.0 / v, 4) if v > 1.0 else None
        except (TypeError, ValueError):
            return None

    for bk in bookmakers:
        for bet in bk.get("bets") or []:
            name = str(bet.get("name") or "").lower()
            values = bet.get("values") or []
            if "match winner" in name or name == "1x2":
                for val in values:
                    lab = str(val.get("value") or "").lower()
                    impl = _impl(val.get("odd"))
                    if lab in ("home", "1"):
                        out["odds_mw_home"] = impl
                    elif lab in ("draw", "x"):
                        out["odds_mw_draw"] = impl
                    elif lab in ("away", "2"):
                        out["odds_mw_away"] = impl
            elif "both teams" in name:
                for val in values:
                    lab = str(val.get("value") or "").lower()
                    impl = _impl(val.get("odd"))
                    if lab == "yes":
                        out["odds_btts_yes"] = impl
                    elif lab == "no":
                        out["odds_btts_no"] = impl
            elif "goals over/under" in name and "2.5" in name:
                for val in values:
                    lab = str(val.get("value") or "").lower()
                    impl = _impl(val.get("odd"))
                    if "over" in lab:
                        out["odds_over_25"] = impl
                    elif "under" in lab:
                        out["odds_under_25"] = impl
    return out


def _load_odds_by_fixture() -> dict[int, dict[str, float | None]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT fixture_id, payload_json FROM odds_snapshots").fetchall()
    conn.close()
    out: dict[int, dict[str, float | None]] = {}
    for r in rows:
        try:
            payload = json.loads(r["payload_json"])
        except json.JSONDecodeError:
            continue
        parsed = _parse_api_odds_payload(payload)
        if any(v is not None for v in parsed.values()):
            out[int(r["fixture_id"])] = parsed
    return out


def _rolling_form(fixtures: list[dict[str, Any]]) -> dict[int, dict[str, float]]:
    """Leakage-safe rolling form from prior finished matches per team."""
    team_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=5))
    form: dict[int, dict[str, float]] = {}

    for fx in fixtures:
        fid = int(fx["fixture_id"])
        home = str(fx["home_team"])
        away = str(fx["away_team"])
        hg = int(fx["home_goals"])
        ag = int(fx["away_goals"])

        def _avg(team: str, key: str) -> float:
            hist = team_history.get(team) or deque()
            if not hist:
                return 0.0
            return round(sum(h[key] for h in hist) / len(hist), 4)

        form[fid] = {
            "home_gf_l5": _avg(home, "gf"),
            "home_ga_l5": _avg(home, "ga"),
            "away_gf_l5": _avg(away, "gf"),
            "away_ga_l5": _avg(away, "ga"),
            "home_btts_l5": _avg(home, "btts"),
            "away_btts_l5": _avg(away, "btts"),
            "home_points_l5": _avg(home, "pts"),
            "away_points_l5": _avg(away, "pts"),
        }

        for team, gf, ga, opp_gf in ((home, hg, ag, ag), (away, ag, hg, hg)):
            btts = 1.0 if gf > 0 and opp_gf > 0 else 0.0
            pts = 3.0 if gf > ga else (1.0 if gf == ga else 0.0)
            team_history[team].append({"gf": gf, "ga": ga, "btts": btts, "pts": pts})

    return form


def _load_uefa_odds_features(settings=None) -> dict[int, dict[str, Any]]:
    from worldcup_predictor.config.settings import get_settings

    settings = settings or get_settings()
    mapping = json.loads(UEFA_MAPPING.read_text(encoding="utf-8")) if UEFA_MAPPING.is_file() else {}
    out: dict[int, dict[str, Any]] = {}
    for fx in mapping.get("fixtures") or []:
        sm_id = int(fx.get("sportmonks_fixture_id") or 0)
        if not sm_id:
            continue
        cache = load_cache(cache_path(settings, sm_id))
        if not cache:
            continue
        deep = parse_first_goal_markets(cache.get("payload"))
        out[sm_id] = deep
    return out


def build_uefa_evaluation_rows(*, settings=None) -> list[dict[str, Any]]:
    """UEFA rows with Sportmonks odds + parsed FG labels (separate ID space from API-Football)."""
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.egie.uefa_club.feature_extractors import parse_match_result

    settings = settings or get_settings()
    mapping = json.loads(UEFA_MAPPING.read_text(encoding="utf-8")) if UEFA_MAPPING.is_file() else {}
    rows: list[dict[str, Any]] = []

    for fx in mapping.get("fixtures") or []:
        sm_id = int(fx.get("sportmonks_fixture_id") or 0)
        if not sm_id:
            continue
        cache = load_cache(cache_path(settings, sm_id))
        if not cache:
            continue
        payload = cache.get("payload")
        deep = parse_first_goal_markets(payload)
        if not any(deep.get(k) is not None for k in ("sharp_implied_home", "consensus_implied_home")):
            continue
        result = parse_match_result(
            payload,
            home_team=str(fx.get("home_team") or ""),
            away_team=str(fx.get("away_team") or ""),
        )
        actual = result.get("first_goal_team_side")
        if actual not in ("home", "away"):
            continue
        rows.append(
            {
                "sportmonks_fixture_id": sm_id,
                "kickoff_utc": fx.get("kickoff_utc"),
                "competition_key": fx.get("competition_key"),
                "home_team": fx.get("home_team"),
                "away_team": fx.get("away_team"),
                "label_fg_team": actual,
                "home_gf_l5": 0.33,
                "away_gf_l5": 0.33,
                **{f"sm_{k}": v for k, v in deep.items() if isinstance(v, (int, float)) or v is None},
            }
        )
    return rows


def build_unified_dataset(*, settings=None) -> pd.DataFrame:
    fixtures = _load_finished_fixtures()
    first_goals = _load_first_goals()
    rolling = _rolling_form(fixtures)
    api_odds = _load_odds_by_fixture()
    uefa_odds = _load_uefa_odds_features(settings)

    rows: list[dict[str, Any]] = []
    for fx in fixtures:
        fid = int(fx["fixture_id"])
        hg = int(fx["home_goals"])
        ag = int(fx["away_goals"])
        total = int(fx.get("total_goals") or hg + ag)
        fg = first_goals.get(fid, {})
        form = rolling.get(fid, {})
        odds = api_odds.get(fid, {})
        uefa = uefa_odds.get(fid, {})

        row: dict[str, Any] = {
            "fixture_id": fid,
            "competition_key": fx["competition_key"],
            "kickoff_utc": fx["kickoff_utc"],
            "home_team": fx["home_team"],
            "away_team": fx["away_team"],
            "label_mw": _mw_label(hg, ag),
            "label_btts": 1 if hg > 0 and ag > 0 else 0,
            "label_over_15": 1 if total >= 2 else 0,
            "label_over_25": 1 if total >= 3 else 0,
            "label_over_35": 1 if total >= 4 else 0,
            "label_fg_team": fg.get("first_goal_team_side"),
            "label_goal_range": fg.get("goal_range"),
            "home_goals": hg,
            "away_goals": ag,
            "total_goals": total,
            **form,
            **{k: v for k, v in odds.items()},
        }
        # Sportmonks / UEFA odds (stronger signal family)
        for key in (
            "consensus_implied_home",
            "consensus_implied_draw",
            "consensus_implied_away",
            "closing_implied_home",
            "closing_implied_draw",
            "closing_implied_away",
            "sharp_implied_home",
            "sharp_implied_away",
            "first_team_score_home",
            "first_team_score_away",
            "odds_movement_home",
            "odds_movement_away",
        ):
            row[f"sm_{key}"] = uefa.get(key)
        rows.append(row)

    return pd.DataFrame(rows)


def build_dataset_inventory(df: pd.DataFrame, *, uefa_odds_rows: int = 0) -> dict[str, Any]:
    markets = {
        "match_winner": "label_mw",
        "btts": "label_btts",
        "over_1_5": "label_over_15",
        "over_2_5": "label_over_25",
        "over_3_5": "label_over_35",
        "first_goal_team": "label_fg_team",
        "goal_range": "label_goal_range",
    }
    inv: dict[str, Any] = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "total_rows": int(len(df)),
        "markets": {},
        "sources": {
            "api_football_fixtures": int(len(df)),
            "rolling_form": int(len(df)),
            "api_odds_snapshots": int(df[["odds_mw_home", "odds_mw_draw", "odds_mw_away"]].notna().any(axis=1).sum()),
            "uefa_sportmonks_odds": uefa_odds_rows or int(
                df[["sm_sharp_implied_home", "sm_consensus_implied_home"]].notna().any(axis=1).sum()
            ),
            "goal_event_labels": int(df["label_fg_team"].notna().sum()),
        },
        "league_coverage": {str(k): int(v) for k, v in df["competition_key"].value_counts().items()},
    }
    for market, col in markets.items():
        valid = df[col].notna() & (df[col] != "unknown")
        sub = df[valid]
        inv["markets"][market] = {
            "row_count": int(len(sub)),
            "label_column": col,
            "positive_or_class_counts": (
                {str(k): int(v) for k, v in sub[col].value_counts().head(10).items()}
                if market not in ("btts", "over_1_5", "over_2_5", "over_3_5")
                else {
                    "positive": int(sub[col].sum()),
                    "negative": int(len(sub) - sub[col].sum()),
                }
            ),
        }
    return inv
