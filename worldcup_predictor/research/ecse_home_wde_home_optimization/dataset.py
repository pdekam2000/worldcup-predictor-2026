"""Rebuild the ECSE=HOME ∧ WDE=HOME true-forward fixture set (read-only)."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.true_forward_472_evaluation.metrics import timing_stage

ROOT = Path(__file__).resolve().parents[3]
EVAL_DB = ROOT / "data" / "evaluation" / "forward_prediction_tracking.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{EVAL_DB.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _norm_1x2(value: Any) -> str | None:
    if value is None:
        return None
    t = str(value).lower().strip().replace(" ", "_")
    return {
        "home": "home_win",
        "home_win": "home_win",
        "1": "home_win",
        "draw": "draw",
        "x": "draw",
        "away": "away_win",
        "away_win": "away_win",
        "2": "away_win",
    }.get(t)


def _pct(value: Any) -> float | None:
    if value is None or value == "":
        return None
    x = float(value)
    if x > 1.0:
        x /= 100.0
    return max(0.0, min(1.0, x))


def _score_dir(score: str | None) -> str | None:
    if not score or "-" not in str(score):
        return None
    try:
        h, a = str(score).split("-", 1)
        hi, ai = int(h), int(a)
    except ValueError:
        return None
    if hi > ai:
        return "home_win"
    if hi < ai:
        return "away_win"
    return "draw"


def _ecse_dir_from_ranks(ranks: list[dict[str, Any]], payload: dict[str, Any]) -> str | None:
    if ranks:
        ordered = sorted(ranks, key=lambda r: int(r.get("rank") or 0))
        return _score_dir(str(ordered[0].get("score") or ""))
    top1 = (payload.get("ecse") or {}).get("top1")
    if isinstance(top1, dict):
        return _score_dir(str(top1.get("score") or top1.get("exact_score") or ""))
    if isinstance(top1, str):
        return _score_dir(top1.split()[0])
    return None


def _masses_from_probs(home: float | None, draw: float | None, away: float | None) -> dict[str, float | None]:
    return {"home_mass": home, "draw_mass": draw, "away_mass": away}


def _pick_canonical(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def key(r: dict[str, Any]) -> tuple:
        ev = 1 if str(r.get("evaluation_status") or "").upper() == "EVALUATED" else 0
        fr = _parse_dt(r.get("frozen_at")) or datetime.min.replace(tzinfo=timezone.utc)
        return (ev, fr)

    return sorted(rows, key=key)[-1]


def load_base_universe() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """All TF unique fixtures with confirmed result + WDE + ECSE direction."""
    if not EVAL_DB.exists():
        return [], {"error": "missing_eval_db"}
    conn = _connect()
    try:
        freezes = [dict(r) for r in conn.execute("SELECT * FROM frozen_predictions").fetchall()]
        results = {int(r["fixture_id"]): dict(r) for r in conn.execute("SELECT * FROM actual_results")}
        ranks_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in conn.execute(
            "SELECT prediction_id, rank, score, probability FROM exact_score_rankings ORDER BY prediction_id, rank"
        ):
            ranks_map[str(r["prediction_id"])].append(dict(r))
        by_fx: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in freezes:
            if row.get("fixture_id") is not None:
                by_fx[int(row["fixture_id"])].append(row)

        universe: list[dict[str, Any]] = []
        for fid, rows in by_fx.items():
            res = results.get(fid)
            if not res:
                continue
            actual = _norm_1x2(res.get("actual_1x2") or res.get("regulation_result"))
            if not actual:
                continue
            canon = _pick_canonical(rows)
            kick = _parse_dt(canon.get("kickoff"))
            frozen = _parse_dt(canon.get("frozen_at"))
            if kick and frozen and frozen >= kick:
                continue
            payload = {}
            if canon.get("complete_payload_json"):
                try:
                    payload = json.loads(canon["complete_payload_json"])
                except json.JSONDecodeError:
                    payload = {}
            ranks = ranks_map.get(str(canon["prediction_id"]), [])
            wde = _norm_1x2(canon.get("wde_decision"))
            ecse = _ecse_dir_from_ranks(ranks, payload)
            if not wde or not ecse:
                continue

            home_p = _pct(canon.get("home_probability"))
            draw_p = _pct(canon.get("draw_probability"))
            away_p = _pct(canon.get("away_probability"))
            oh = float(canon["odds_home"]) if canon.get("odds_home") is not None else None
            od = float(canon["odds_draw"]) if canon.get("odds_draw") is not None else None
            oa = float(canon["odds_away"]) if canon.get("odds_away") is not None else None
            fav_odds = min(x for x in (oh, od, oa) if x is not None) if any(x is not None for x in (oh, od, oa)) else None
            margin = None
            if oh and od and oa and oh > 1 and od > 1 and oa > 1:
                margin = round((1 / oh + 1 / od + 1 / oa) - 1.0, 6)
            market_fav = None
            if oh and od and oa:
                market_fav = min([("home_win", oh), ("draw", od), ("away_win", oa)], key=lambda x: x[1])[0]

            lh = canon.get("lambda_home")
            la = canon.get("lambda_away")
            total_l = canon.get("total_lambda")
            if total_l is None and lh is not None and la is not None:
                total_l = float(lh) + float(la)

            # ECSE home/draw/away mass from WDE probs as proxy when ECSE marginals absent;
            # also compute from top ranks score-side mass
            home_mass = draw_mass = away_mass = 0.0
            for r in ranks[:10]:
                pr = r.get("probability")
                if pr is None:
                    continue
                p = float(pr)
                if p > 1:
                    p /= 100.0
                d = _score_dir(str(r.get("score") or ""))
                if d == "home_win":
                    home_mass += p
                elif d == "draw":
                    draw_mass += p
                elif d == "away_win":
                    away_mass += p
            # if ranks probs missing, fall back to WDE probs
            if home_mass + draw_mass + away_mass < 1e-9:
                home_mass = home_p or 0.0
                draw_mass = draw_p or 0.0
                away_mass = away_p or 0.0

            ou_p = payload.get("ou25") or {}
            btts_p = payload.get("btts") or {}
            over_prob = None
            under_prob = None
            if isinstance(ou_p.get("probabilities"), dict):
                over_prob = _pct(ou_p["probabilities"].get("over_2_5"))
                under_prob = _pct(ou_p["probabilities"].get("under_2_5"))
            btts_yes = _pct(btts_p.get("yes_probability") or canon.get("btts_probability"))

            hours = None
            if kick and frozen:
                hours = (kick - frozen).total_seconds() / 3600.0

            hit = ecse == actual  # for base rule evaluation we care about home prediction hit
            # For the home_only_agree rule, predicted side is always home_win
            rule_hit = actual == "home_win"

            # shadow specialists availability flags only (no regeneration)
            specialist_flags = {
                "exact_v2_present": False,
                "dna_present": False,
                "twins_present": False,
                "hcee_present": False,
                "team_form_present": False,
                "league_specialist_present": False,
                "high_goal_specialist_present": False,
                "favorite_specialist_present": False,
                "meta_present": False,
            }

            row = {
                "fixture_id": fid,
                "date": kick.date().isoformat() if kick else None,
                "league": canon.get("competition"),
                "country": None,
                "home": canon.get("home_team_name"),
                "away": canon.get("away_team_name"),
                "match_name": canon.get("match_name"),
                "kickoff": canon.get("kickoff"),
                "odds_home": oh,
                "odds_draw": od,
                "odds_away": oa,
                "favorite_odds": fav_odds,
                "favorite_strength": (1.0 / fav_odds) if fav_odds else None,
                "market_favorite": market_fav,
                "market_margin": margin,
                "bookmaker_count": canon.get("bookmaker_count"),
                "wde_decision": wde,
                "ecse_direction": ecse,
                "wde_home_p": home_p,
                "wde_draw_p": draw_p,
                "wde_away_p": away_p,
                "wde_confidence": _pct(canon.get("wde_confidence")) or home_p,
                "ecse_home_mass": round(home_mass, 6),
                "ecse_draw_mass": round(draw_mass, 6),
                "ecse_away_mass": round(away_mass, 6),
                "ecse_home_gap": round(home_mass - max(draw_mass, away_mass), 6),
                "top1_score": str(ranks[0]["score"]) if ranks else None,
                "top5_scores": "|".join(str(r["score"]) for r in ranks[:5]),
                "top10_scores": "|".join(str(r["score"]) for r in ranks[:10]),
                "top3_mass": canon.get("top3_mass"),
                "top5_mass": canon.get("top5_mass"),
                "top10_mass": canon.get("top10_mass"),
                "entropy": canon.get("entropy"),
                "lambda_home": float(lh) if lh is not None else None,
                "lambda_away": float(la) if la is not None else None,
                "total_lambda": float(total_l) if total_l is not None else None,
                "goal_balance": (
                    abs(float(lh) - float(la)) if lh is not None and la is not None else None
                ),
                "btts_prediction": canon.get("btts_prediction") or btts_p.get("prediction"),
                "btts_yes_probability": btts_yes,
                "ou25_prediction": canon.get("ou25_prediction") or ou_p.get("selection"),
                "over_probability": over_prob,
                "under_probability": under_prob,
                "model_agreement": "AGREE" if wde == ecse else "DISAGREE",
                "market_agreement": (
                    "AGREE"
                    if market_fav == "home_win"
                    else ("DISAGREE" if market_fav else "UNKNOWN")
                ),
                "no_bet": None,
                "no_bet_reason": None,
                "warnings": canon.get("warning_summary"),
                "data_quality": canon.get("data_quality"),
                "snapshot_stage": timing_stage(hours),
                "hours_to_kickoff": hours,
                "actual_1x2": actual,
                "actual_score": res.get("actual_score"),
                "actual_home_goals": res.get("actual_home_goals"),
                "actual_away_goals": res.get("actual_away_goals"),
                "direction_hit": rule_hit,  # home prediction correct?
                "ecse_raw_hit": hit,
                "prediction_id": canon.get("prediction_id"),
                "freeze_hash": canon.get("payload_hash") or canon.get("content_hash"),
                "tier": canon.get("tier") or canon.get("validation_tier"),
                "prediction_scope": canon.get("prediction_scope"),
                **specialist_flags,
                "specialists_note": "Shadow specialist outputs not joined; flags false unless extended later",
            }
            universe.append(row)

        # optional shadow presence scan
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table, flag in (
            ("lambda_v2_shadow_outputs", "exact_v2_present"),  # proxy flag name kept honest below
            ("high_score_tail_shadow_outputs", "high_goal_specialist_present"),
        ):
            if table not in tables:
                continue
            fx = {
                int(r[0])
                for r in conn.execute(f"SELECT DISTINCT fixture_id FROM {table}").fetchall()
                if r[0] is not None
            }
            for row in universe:
                if int(row["fixture_id"]) in fx:
                    row[flag] = True
                    if table == "lambda_v2_shadow_outputs":
                        row["exact_v2_present"] = False  # do not mislabel
                        row["lambda_v2_shadow_present"] = True

        manifest = {
            "eval_db": str(EVAL_DB.relative_to(ROOT)),
            "universe_n": len(universe),
            "rule_base": "ecse_direction=home_win AND wde_decision=home_win",
            "ecse_direction_definition": "Top1 exact-score side from frozen exact_score_rankings / ecse payload",
        }
        return universe, manifest
    finally:
        conn.close()


def extract_home_agree(universe: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        r
        for r in universe
        if r.get("ecse_direction") == "home_win" and r.get("wde_decision") == "home_win"
    ]
