"""Read-only prematch feature snapshot builder (no provider mutation)."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.challenger.constants import STATUS_DATA_BLOCKED, STATUS_POST_KICKOFF
from worldcup_predictor.challenger.feature_contract import DEFAULT_GBGM_CONTRACT, missingness_indicators


def _parse_dt(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _f(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        x = float(v)
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    except (TypeError, ValueError):
        return None


def _avg(vals: list[float]) -> float | None:
    return sum(vals) / len(vals) if vals else None


def _hash_features(features: dict[str, Any]) -> str:
    raw = json.dumps(features, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_prematch_feature_snapshot(
    conn: sqlite3.Connection,
    fixture_id: int,
    *,
    prediction_time: datetime | None = None,
    include_market: bool = False,
) -> dict[str, Any]:
    """
    Build a read-only feature snapshot using only matches finished BEFORE prediction_time
    (default: kickoff of target fixture). Never includes final score of the target fixture.
    """
    fx = conn.execute(
        """
        SELECT fixture_id, home_team_id, away_team_id, home_team, away_team,
               competition_key, kickoff_utc, status, season
        FROM fixtures WHERE fixture_id=? AND is_placeholder=0
        """,
        (fixture_id,),
    ).fetchone()
    if not fx:
        return {"status": STATUS_DATA_BLOCKED, "reason": "fixture_not_found", "features": {}}

    kickoff = _parse_dt(fx["kickoff_utc"])
    pred_t = prediction_time or kickoff
    if pred_t is None:
        return {"status": STATUS_DATA_BLOCKED, "reason": "missing_kickoff", "features": {}}

    now = datetime.now(timezone.utc)
    status = str(fx["status"] or "NS").upper()
    if status in {"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "FT", "AET", "PEN"} or (kickoff and kickoff <= now and prediction_time is None):
        # For live forward prediction without explicit historical prediction_time, block post-kickoff
        if prediction_time is None and kickoff and kickoff <= now:
            return {
                "status": STATUS_POST_KICKOFF,
                "reason": "post_kickoff",
                "features": {},
                "fixture_id": fixture_id,
            }

    home_id = fx["home_team_id"]
    away_id = fx["away_team_id"]
    comp = fx["competition_key"]
    cutoff = pred_t.strftime("%Y-%m-%dT%H:%M:%S")

    def recent_team_goals(team_id: int | None, *, as_home: bool | None, limit: int = 5) -> tuple[list[float], list[float]]:
        if not team_id:
            return [], []
        if as_home is True:
            q = """
                SELECT r.home_goals, r.away_goals
                FROM fixtures f
                JOIN fixture_results r ON r.fixture_id = f.fixture_id
                WHERE f.home_team_id=? AND f.competition_key=? AND f.status IN ('FT','AET','PEN')
                  AND f.kickoff_utc < ? AND r.home_goals IS NOT NULL AND r.away_goals IS NOT NULL
                ORDER BY f.kickoff_utc DESC LIMIT ?
            """
            rows = conn.execute(q, (team_id, comp, cutoff, limit)).fetchall()
            return [float(r["home_goals"]) for r in rows], [float(r["away_goals"]) for r in rows]
        if as_home is False:
            q = """
                SELECT r.home_goals, r.away_goals
                FROM fixtures f
                JOIN fixture_results r ON r.fixture_id = f.fixture_id
                WHERE f.away_team_id=? AND f.competition_key=? AND f.status IN ('FT','AET','PEN')
                  AND f.kickoff_utc < ? AND r.home_goals IS NOT NULL AND r.away_goals IS NOT NULL
                ORDER BY f.kickoff_utc DESC LIMIT ?
            """
            rows = conn.execute(q, (team_id, comp, cutoff, limit)).fetchall()
            return [float(r["away_goals"]) for r in rows], [float(r["home_goals"]) for r in rows]
        q = """
            SELECT f.home_team_id, r.home_goals, r.away_goals
            FROM fixtures f
            JOIN fixture_results r ON r.fixture_id = f.fixture_id
            WHERE (f.home_team_id=? OR f.away_team_id=?) AND f.competition_key=?
              AND f.status IN ('FT','AET','PEN')
              AND f.kickoff_utc < ? AND r.home_goals IS NOT NULL AND r.away_goals IS NOT NULL
            ORDER BY f.kickoff_utc DESC LIMIT ?
        """
        rows = conn.execute(q, (team_id, team_id, comp, cutoff, limit)).fetchall()
        gf, ga = [], []
        for r in rows:
            if int(r["home_team_id"]) == int(team_id):
                gf.append(float(r["home_goals"]))
                ga.append(float(r["away_goals"]))
            else:
                gf.append(float(r["away_goals"]))
                ga.append(float(r["home_goals"]))
        return gf, ga

    h_gf, h_ga = recent_team_goals(int(home_id) if home_id else None, as_home=True, limit=5)
    a_gf, a_ga = recent_team_goals(int(away_id) if away_id else None, as_home=False, limit=5)

    # League averages strictly before cutoff (exclude target fixture by kickoff < cutoff)
    lg = conn.execute(
        """
        SELECT AVG(r.home_goals) ah, AVG(r.away_goals) aa, COUNT(*) n
        FROM fixtures f
        JOIN fixture_results r ON r.fixture_id = f.fixture_id
        WHERE f.competition_key=? AND f.status IN ('FT','AET','PEN')
          AND f.kickoff_utc < ? AND r.home_goals IS NOT NULL AND r.away_goals IS NOT NULL
        """,
        (comp, cutoff),
    ).fetchone()

    features: dict[str, Any] = {
        "fixture_id": fixture_id,
        "competition_key": comp,
        "home_team_id": home_id,
        "away_team_id": away_id,
        "is_home": 1.0,
        "home_goals_for_avg_l5": _avg(h_gf),
        "home_goals_against_avg_l5": _avg(h_ga),
        "away_goals_for_avg_l5": _avg(a_gf),
        "away_goals_against_avg_l5": _avg(a_ga),
        "league_avg_home_goals": _f(lg["ah"]) if lg else None,
        "league_avg_away_goals": _f(lg["aa"]) if lg else None,
        "league_sample_before_cutoff": int(lg["n"] or 0) if lg else 0,
        "home_l5_sample": len(h_gf),
        "away_l5_sample": len(a_gf),
    }
    features.update(
        missingness_indicators(
            features,
            DEFAULT_GBGM_CONTRACT.required + DEFAULT_GBGM_CONTRACT.optional,
        )
    )

    if include_market:
        features["market_odds_usable"] = 0
        try:
            from worldcup_predictor.odds.canonical_snapshot import get_latest_valid_1x2_odds_snapshot

            snap_odds = get_latest_valid_1x2_odds_snapshot(conn, fixture_id, kickoff_utc=fx["kickoff_utc"])
            if snap_odds is not None:
                d = snap_odds.to_dict() if hasattr(snap_odds, "to_dict") else dict(snap_odds)
                fetched = _parse_dt(str(d.get("fetched_at_utc") or ""))
                if fetched is None or fetched <= pred_t:
                    h, dr, a = _f(d.get("home_odds")), _f(d.get("draw_odds")), _f(d.get("away_odds"))
                    if h and dr and a and h > 1 and dr > 1 and a > 1:
                        ih, idr, ia = 1.0 / h, 1.0 / dr, 1.0 / a
                        s = ih + idr + ia
                        features["implied_home"] = ih / s
                        features["implied_draw"] = idr / s
                        features["implied_away"] = ia / s
                        features["bookmaker_count"] = d.get("bookmaker_count")
                        features["market_odds_usable"] = 1
                else:
                    features["warnings_market"] = "odds_after_prediction_time_rejected"
        except Exception as exc:
            features["warnings_market"] = f"odds_read_failed:{type(exc).__name__}"

    missing, leaked = DEFAULT_GBGM_CONTRACT.validate_keys(set(features.keys()))
    # required may be present as keys with None — treat None as missing
    missing_vals = [k for k in DEFAULT_GBGM_CONTRACT.required if features.get(k) is None]
    status = "OK"
    reason = None
    if leaked:
        status = STATUS_DATA_BLOCKED
        reason = f"forbidden_features:{leaked}"
    elif missing_vals:
        status = STATUS_DATA_BLOCKED
        reason = f"missing_required:{missing_vals}"
    elif int(features.get("league_sample_before_cutoff") or 0) < 20:
        status = STATUS_DATA_BLOCKED
        reason = "insufficient_league_history_before_cutoff"

    snap_id = f"challenger_fs_{fixture_id}_{'MC' if include_market else 'NM'}"
    payload = {
        "status": status,
        "reason": reason,
        "fixture_id": fixture_id,
        "home_team": fx["home_team"],
        "away_team": fx["away_team"],
        "competition_key": comp,
        "kickoff_utc": fx["kickoff_utc"],
        "prediction_time": pred_t.isoformat(),
        "include_market": include_market,
        "feature_snapshot_id": snap_id,
        "features": features,
        "missing_required": missing_vals,
        "leaked_forbidden": leaked,
        "read_only": True,
        "mutates_canonical": False,
    }
    payload["feature_snapshot_hash"] = _hash_features(features)
    return payload
