"""Build O/U 2.5 fixture ledger from TF freezes + historical stored predictions (read-only)."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.ou25_regime_mining.metrics import (
    goals_to_ou,
    lambda_bucket,
    norm_ou,
    prob_bucket,
    score_total,
    timing_stage,
)

ROOT = Path(__file__).resolve().parents[3]
EVAL_DB = ROOT / "data" / "evaluation" / "forward_prediction_tracking.db"
FI_DB = ROOT / "data" / "football_intelligence.db"


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        try:
            dt = datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
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


def _pct_to_unit(p: Any) -> float | None:
    if p is None or p == "":
        return None
    x = float(p)
    if x > 1.0:
        x = x / 100.0
    return max(0.0, min(1.0, x))


def _score_goals(score: str) -> tuple[int, int] | None:
    if not score or "-" not in score:
        return None
    try:
        h, a = score.split("-", 1)
        return int(h), int(a)
    except ValueError:
        return None


def ecse_ou_features(ranks: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(ranks, key=lambda r: int(r.get("rank") or 0))
    top5 = ordered[:5]
    top10 = ordered[:10] if len(ordered) >= 10 else ordered
    over5 = under5 = 0
    mass_over5 = mass_under5 = 0.0
    low6 = high_tail = clean = btts_c = 0.0
    for r in top5:
        sc = str(r.get("score") or "")
        g = _score_goals(sc)
        pr = float(r.get("probability") or 0.0)
        if pr > 1:
            pr = pr / 100.0
        if not g:
            continue
        tot = g[0] + g[1]
        if tot > 2:
            over5 += 1
            mass_over5 += pr
        else:
            under5 += 1
            mass_under5 += pr
        if tot <= 2:
            low6 += pr
        if tot >= 4:
            high_tail += pr
        if g[0] == 0 or g[1] == 0:
            clean += pr
        if g[0] > 0 and g[1] > 0:
            btts_c += pr
    over10 = under10 = 0
    mass_over10 = mass_under10 = 0.0
    for r in top10:
        g = _score_goals(str(r.get("score") or ""))
        pr = float(r.get("probability") or 0.0)
        if pr > 1:
            pr = pr / 100.0
        if not g:
            continue
        if g[0] + g[1] > 2:
            over10 += 1
            mass_over10 += pr
        else:
            under10 += 1
            mass_under10 += pr
    return {
        "top5_over_count": over5,
        "top5_under_count": under5,
        "ecse_over_mass_top5": round(mass_over5, 6),
        "ecse_under_mass_top5": round(mass_under5, 6),
        "top5_majority": "over" if over5 > under5 else ("under" if under5 > over5 else "tie"),
        "top10_over_count": over10 if len(ordered) >= 10 else None,
        "top10_under_count": under10 if len(ordered) >= 10 else None,
        "ecse_over_mass_top10": round(mass_over10, 6) if len(ordered) >= 10 else None,
        "ecse_under_mass_top10": round(mass_under10, 6) if len(ordered) >= 10 else None,
        "top10_majority": (
            ("over" if over10 > under10 else ("under" if under10 > over10 else "tie"))
            if len(ordered) >= 10
            else None
        ),
        "low_score_six_mass": round(low6, 6),
        "high_score_tail_mass": round(high_tail, 6),
        "clean_sheet_concentration": round(clean, 6),
        "btts_concentration": round(btts_c, 6),
        "top1_score": str(top5[0]["score"]) if top5 else None,
    }


def _pick_canonical(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def key(r: dict[str, Any]) -> tuple:
        ev = 1 if str(r.get("evaluation_status") or "").upper() == "EVALUATED" else 0
        fr = _parse_dt(r.get("frozen_at")) or datetime.min.replace(tzinfo=timezone.utc)
        return (ev, fr)

    return sorted(rows, key=key)[-1]


def load_tf_rows() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not EVAL_DB.exists():
        return [], {"error": "missing_eval_db"}
    conn = _connect(EVAL_DB)
    try:
        freezes = [dict(r) for r in conn.execute("SELECT * FROM frozen_predictions").fetchall()]
        results = {int(r["fixture_id"]): dict(r) for r in conn.execute("SELECT * FROM actual_results").fetchall()}
        ranks_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in conn.execute(
            "SELECT prediction_id, rank, score, probability FROM exact_score_rankings ORDER BY prediction_id, rank"
        ):
            ranks_map[str(r["prediction_id"])].append(dict(r))
        by_fx: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in freezes:
            if row.get("fixture_id") is None:
                continue
            by_fx[int(row["fixture_id"])].append(row)

        out: list[dict[str, Any]] = []
        for fid, rows in by_fx.items():
            result = results.get(fid)
            if not result or not result.get("actual_ou25"):
                # still allow if goals present
                if not result or result.get("actual_home_goals") is None:
                    continue
            canon = _pick_canonical(rows)
            kick = _parse_dt(canon.get("kickoff"))
            frozen = _parse_dt(canon.get("frozen_at"))
            gen = _parse_dt(canon.get("generated_at"))
            pred_ts = gen or frozen
            if kick and pred_ts and pred_ts >= kick:
                continue  # post-kickoff excluded
            if kick and frozen and frozen >= kick:
                continue

            payload = {}
            if canon.get("complete_payload_json"):
                try:
                    payload = json.loads(canon["complete_payload_json"])
                except json.JSONDecodeError:
                    payload = {}
            ou_p = payload.get("ou25") or {}
            btts_p = payload.get("btts") or {}
            ecse_p = payload.get("ecse") or {}

            over_prob = _pct_to_unit(
                (ou_p.get("probabilities") or {}).get("over_2_5")
                if isinstance(ou_p.get("probabilities"), dict)
                else None
            )
            under_prob = _pct_to_unit(
                (ou_p.get("probabilities") or {}).get("under_2_5")
                if isinstance(ou_p.get("probabilities"), dict)
                else None
            )
            if over_prob is None and ou_p.get("probability") is not None and norm_ou(ou_p.get("selection") or canon.get("ou25_prediction")) == "over_2_5":
                over_prob = _pct_to_unit(ou_p.get("probability"))
                under_prob = 1.0 - over_prob if over_prob is not None else None
            if under_prob is None and ou_p.get("probability") is not None and norm_ou(ou_p.get("selection") or canon.get("ou25_prediction")) == "under_2_5":
                under_prob = _pct_to_unit(ou_p.get("probability"))
                over_prob = 1.0 - under_prob if under_prob is not None else None

            selected = norm_ou(canon.get("ou25_prediction") or ou_p.get("selection"))
            if not selected:
                continue

            actual = norm_ou(result.get("actual_ou25"))
            if actual is None:
                actual = goals_to_ou(result.get("actual_home_goals"), result.get("actual_away_goals"))
            if actual is None:
                continue

            ranks = ranks_map.get(str(canon["prediction_id"]), [])
            # expand from ecse payload top5/top10 if ranks thin
            if len(ranks) < 5 and isinstance(ecse_p.get("top5"), list):
                ranks = []
                for i, item in enumerate(ecse_p.get("top5") or [], start=1):
                    if isinstance(item, dict):
                        ranks.append(
                            {
                                "rank": i,
                                "score": item.get("score") or item.get("exact_score"),
                                "probability": item.get("probability") or item.get("p"),
                            }
                        )
                    elif isinstance(item, str):
                        ranks.append({"rank": i, "score": item.split()[0], "probability": None})
            feat = ecse_ou_features(ranks)
            hours = None
            if kick and frozen:
                hours = (kick - frozen).total_seconds() / 3600.0

            conf = over_prob if selected == "over_2_5" else under_prob
            btts_yes = _pct_to_unit(btts_p.get("yes_probability") or canon.get("btts_probability"))
            btts_sel = str(canon.get("btts_prediction") or btts_p.get("prediction") or "").lower()
            if btts_sel in {"yes", "no"}:
                pass
            else:
                btts_sel = None

            wde = _norm_1x2(canon.get("wde_decision"))
            # ECSE direction from top1
            ecse_dir = None
            if feat.get("top1_score"):
                g = _score_goals(str(feat["top1_score"]))
                if g:
                    if g[0] > g[1]:
                        ecse_dir = "home_win"
                    elif g[0] < g[1]:
                        ecse_dir = "away_win"
                    else:
                        ecse_dir = "draw"

            home_p = _pct_to_unit(canon.get("home_probability"))
            draw_p = _pct_to_unit(canon.get("draw_probability"))
            away_p = _pct_to_unit(canon.get("away_probability"))

            total_goals = None
            if result.get("actual_home_goals") is not None:
                total_goals = int(result["actual_home_goals"]) + int(result["actual_away_goals"])
            elif result.get("actual_score"):
                total_goals = score_total(result.get("actual_score"))

            row_out = {
                "fixture_id": fid,
                "kickoff": canon.get("kickoff"),
                "league": canon.get("competition"),
                "country": None,
                "home": canon.get("home_team_name"),
                "away": canon.get("away_team_name"),
                "match_name": canon.get("match_name"),
                "snapshot_stage": timing_stage(hours),
                "hours_to_kickoff": hours,
                "over_probability": over_prob,
                "under_probability": under_prob,
                "selected_side": selected,
                "confidence": conf,
                "total_lambda": float(canon["total_lambda"]) if canon.get("total_lambda") is not None else (
                    float(canon["lambda_home"]) + float(canon["lambda_away"])
                    if canon.get("lambda_home") is not None and canon.get("lambda_away") is not None
                    else None
                ),
                "lambda_home": canon.get("lambda_home"),
                "lambda_away": canon.get("lambda_away"),
                "top3_mass": canon.get("top3_mass"),
                "top5_mass": canon.get("top5_mass"),
                "top10_mass": canon.get("top10_mass"),
                "entropy": canon.get("entropy"),
                "btts_prediction": btts_sel,
                "btts_yes_probability": btts_yes,
                "btts_no_probability": (1.0 - btts_yes) if btts_yes is not None else None,
                "wde_home_p": home_p,
                "wde_draw_p": draw_p,
                "wde_away_p": away_p,
                "wde_decision": wde,
                "ecse_direction": ecse_dir,
                "odds_home": canon.get("odds_home"),
                "odds_draw": canon.get("odds_draw"),
                "odds_away": canon.get("odds_away"),
                "ou_odds_over": None,
                "ou_odds_under": None,
                "ou_odds_class": "UNPRICED",
                "bookmaker_count": canon.get("bookmaker_count"),
                "no_bet": None,
                "no_bet_reasons": None,
                "model_agreement": (
                    "AGREE" if wde and ecse_dir and wde == ecse_dir else ("DISAGREE" if wde and ecse_dir else "PARTIAL")
                ),
                "data_quality": canon.get("data_quality"),
                "actual_total_goals": total_goals,
                "actual_ou25": actual,
                "hit": selected == actual,
                "cohort": "TRUE_FORWARD",
                "source": "frozen_predictions",
                "prediction_id": canon.get("prediction_id"),
                "freeze_hash": canon.get("payload_hash") or canon.get("content_hash"),
                "tier": canon.get("tier") or canon.get("validation_tier"),
                **feat,
                "lambda_bucket": lambda_bucket(
                    float(canon["total_lambda"])
                    if canon.get("total_lambda") is not None
                    else None
                ),
                "prob_bucket": prob_bucket(conf),
            }
            out.append(row_out)
        manifest = {
            "source": str(EVAL_DB.relative_to(ROOT)),
            "raw_freezes": len(freezes),
            "unique_fixtures_with_ou_result": len(out),
            "cohort": "TRUE_FORWARD",
        }
        return out, manifest
    finally:
        conn.close()


def load_historical_rows() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not FI_DB.exists():
        return [], {"error": "missing_fi_db"}
    conn = _connect(FI_DB)
    try:
        rows = conn.execute(
            """
            SELECT w.fixture_id, w.competition_key, w.kickoff_utc AS w_kickoff, w.predicted_at,
                   w.payload_json, w.prediction_scope, w.validation_tier, w.source,
                   f.kickoff_utc AS f_kickoff, f.home_team, f.away_team, f.competition_type,
                   fr.home_goals, fr.away_goals, fr.over_under_2_5, fr.total_goals,
                   fr.regulation_home_goals, fr.regulation_away_goals
            FROM worldcup_stored_predictions w
            JOIN fixtures f ON f.fixture_id = w.fixture_id
            JOIN fixture_results fr ON fr.fixture_id = w.fixture_id
            WHERE w.payload_json LIKE '%over_under_2_5%'
              AND fr.home_goals IS NOT NULL AND fr.away_goals IS NOT NULL
              AND COALESCE(w.is_quarantined, 0) = 0
            """
        ).fetchall()
    except sqlite3.OperationalError:
        rows = conn.execute(
            """
            SELECT w.fixture_id, w.competition_key, w.kickoff_utc AS w_kickoff, w.predicted_at,
                   w.payload_json, w.prediction_scope, w.validation_tier, w.source,
                   f.kickoff_utc AS f_kickoff, f.home_team, f.away_team,
                   fr.home_goals, fr.away_goals, fr.over_under_2_5, fr.total_goals,
                   fr.regulation_home_goals, fr.regulation_away_goals
            FROM worldcup_stored_predictions w
            JOIN fixtures f ON f.fixture_id = w.fixture_id
            JOIN fixture_results fr ON fr.fixture_id = w.fixture_id
            WHERE w.payload_json LIKE '%over_under_2_5%'
              AND fr.home_goals IS NOT NULL AND fr.away_goals IS NOT NULL
            """
        ).fetchall()

    out: list[dict[str, Any]] = []
    skipped = {"post_kickoff": 0, "missing_selection": 0, "missing_actual": 0}
    for r in rows:
        d = dict(r)
        kick = _parse_dt(d.get("f_kickoff") or d.get("w_kickoff"))
        pred = _parse_dt(d.get("predicted_at"))
        if not kick or not pred or pred >= kick:
            skipped["post_kickoff"] += 1
            continue
        try:
            payload = json.loads(d["payload_json"] or "{}")
        except json.JSONDecodeError:
            skipped["missing_selection"] += 1
            continue
        ou_prob = (payload.get("probabilities") or {}).get("over_under_2_5") or {}
        detailed = (payload.get("detailed_markets") or {}).get("over_under_2_5") or {}
        selected = norm_ou(ou_prob.get("selection") if isinstance(ou_prob, dict) else None)
        over_prob = under_prob = None
        if isinstance(detailed, dict) and detailed.get("option_a") is not None:
            # label_a/b
            la = str(detailed.get("label_a") or "over").lower()
            lb = str(detailed.get("label_b") or "under").lower()
            oa = float(detailed["option_a"])
            ob = float(detailed["option_b"])
            if "over" in la:
                over_prob, under_prob = oa, ob
            else:
                over_prob, under_prob = ob, oa
        if selected is None and over_prob is not None and under_prob is not None:
            selected = "over_2_5" if over_prob >= under_prob else "under_2_5"
        if not selected:
            skipped["missing_selection"] += 1
            continue

        hg = d.get("regulation_home_goals")
        ag = d.get("regulation_away_goals")
        if hg is None:
            hg = d.get("home_goals")
        if ag is None:
            ag = d.get("away_goals")
        actual = norm_ou(d.get("over_under_2_5")) or goals_to_ou(hg, ag)
        if actual is None:
            skipped["missing_actual"] += 1
            continue

        # WDE/ECSE from payload if present
        probs = payload.get("probabilities") or {}
        wde_block = probs.get("match_result") or probs.get("1x2") or {}
        home_p = _pct_to_unit(
            wde_block.get("home") or wde_block.get("home_win") or (payload.get("wde") or {}).get("home_probability")
        )
        draw_p = _pct_to_unit(wde_block.get("draw") or (payload.get("wde") or {}).get("draw_probability"))
        away_p = _pct_to_unit(
            wde_block.get("away") or wde_block.get("away_win") or (payload.get("wde") or {}).get("away_probability")
        )
        wde_block_payload = payload.get("wde") if isinstance(payload.get("wde"), dict) else {}
        pred_block = payload.get("prediction") if isinstance(payload.get("prediction"), dict) else {}
        wde = _norm_1x2(wde_block_payload.get("decision_pick") or pred_block.get("1x2"))
        ecse = payload.get("ecse") if isinstance(payload.get("ecse"), dict) else {}
        if not ecse and isinstance(payload.get("exact_score"), dict):
            ecse = payload.get("exact_score") or {}
        ranks = []
        top5 = ecse.get("top5") or ecse.get("top_5") or []
        if isinstance(top5, list):
            for i, item in enumerate(top5, start=1):
                if isinstance(item, dict):
                    ranks.append(
                        {
                            "rank": i,
                            "score": item.get("score") or item.get("exact_score"),
                            "probability": item.get("probability") or item.get("p"),
                        }
                    )
        feat = ecse_ou_features(ranks)
        conf = over_prob if selected == "over_2_5" else under_prob
        probs_root = payload.get("probabilities") if isinstance(payload.get("probabilities"), dict) else {}
        detailed_root = payload.get("detailed_markets") if isinstance(payload.get("detailed_markets"), dict) else {}
        btts = probs_root.get("btts") if isinstance(probs_root.get("btts"), dict) else None
        if btts is None:
            btts = detailed_root.get("btts") if isinstance(detailed_root.get("btts"), dict) else {}
        btts_yes = None
        btts_sel = None
        if isinstance(btts, dict):
            if btts.get("option_a") is not None:
                la = str(btts.get("label_a") or "yes").lower()
                oa = float(btts["option_a"])
                ob = float(btts.get("option_b") or (1 - oa))
                btts_yes = oa if "yes" in la else ob
            if btts.get("selection"):
                btts_sel = str(btts["selection"]).lower()
            elif btts_yes is not None:
                btts_sel = "yes" if btts_yes >= 0.5 else "no"

        lh = ecse.get("lambda_home")
        la_ = ecse.get("lambda_away")
        total_l = None
        if lh is not None and la_ is not None:
            total_l = float(lh) + float(la_)

        hours = (kick - pred).total_seconds() / 3600.0
        out.append(
            {
                "fixture_id": int(d["fixture_id"]),
                "kickoff": kick.isoformat() if kick else None,
                "league": d.get("competition_key"),
                "country": None,
                "home": d.get("home_team"),
                "away": d.get("away_team"),
                "match_name": None,
                "snapshot_stage": timing_stage(hours),
                "hours_to_kickoff": hours,
                "over_probability": over_prob,
                "under_probability": under_prob,
                "selected_side": selected,
                "confidence": conf,
                "total_lambda": total_l,
                "lambda_home": lh,
                "lambda_away": la_,
                "top3_mass": ecse.get("top3_mass"),
                "top5_mass": ecse.get("top5_mass"),
                "top10_mass": ecse.get("top10_mass"),
                "entropy": ecse.get("entropy"),
                "btts_prediction": btts_sel,
                "btts_yes_probability": btts_yes,
                "btts_no_probability": (1.0 - btts_yes) if btts_yes is not None else None,
                "wde_home_p": home_p,
                "wde_draw_p": draw_p,
                "wde_away_p": away_p,
                "wde_decision": wde,
                "ecse_direction": (
                    (lambda g: None if not g else ("home_win" if g[0] > g[1] else ("away_win" if g[0] < g[1] else "draw")))(
                        _score_goals(str(feat["top1_score"])) if feat.get("top1_score") else None
                    )
                ),
                "odds_home": None,
                "odds_draw": None,
                "odds_away": None,
                "ou_odds_over": None,
                "ou_odds_under": None,
                "ou_odds_class": "UNPRICED",
                "bookmaker_count": None,
                "no_bet": payload.get("no_bet"),
                "no_bet_reasons": payload.get("no_bet_reasons") or payload.get("warnings"),
                "model_agreement": None,
                "data_quality": d.get("validation_tier"),
                "actual_total_goals": int(hg) + int(ag) if hg is not None else d.get("total_goals"),
                "actual_ou25": actual,
                "hit": selected == actual,
                "cohort": "HISTORICAL_PREMATCH",
                "source": "worldcup_stored_predictions",
                "prediction_id": None,
                "freeze_hash": None,
                "tier": d.get("validation_tier"),
                **feat,
                "lambda_bucket": lambda_bucket(total_l),
                "prob_bucket": prob_bucket(conf),
            }
        )

    # attach CSV O/U odds (official prematch if available)
    odds_inv = attach_ou_odds(conn, out)

    manifest = {
        "source": str(FI_DB.relative_to(ROOT)),
        "joined_finished": len(rows),
        "prematch_kept": len(out),
        "skipped": skipped,
        "cohort": "HISTORICAL_PREMATCH",
        "odds_attach": odds_inv,
    }
    return out, manifest


def attach_ou_odds(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> dict[str, Any]:
    fx_ids = [int(r["fixture_id"]) for r in rows]
    if not fx_ids:
        return {"official_priced": 0}
    # historical_csv_odds_prematch_clean
    placeholders = ",".join("?" for _ in fx_ids)
    try:
        odds_rows = conn.execute(
            f"""
            SELECT registry_fixture_id, selection, closing_odds, opening_odds, kickoff_utc, closing_unix, bookmaker
            FROM historical_csv_odds_prematch_clean
            WHERE market='over_under' AND selection IN ('over_25','under_25')
              AND registry_fixture_id IN ({placeholders})
              AND prematch_verified=1
            """,
            fx_ids,
        ).fetchall()
    except sqlite3.Error:
        odds_rows = []

    by_fx: dict[int, dict[str, list]] = defaultdict(lambda: {"over": [], "under": []})
    for r in odds_rows:
        fid = int(r["registry_fixture_id"])
        sel = str(r["selection"])
        o = r["closing_odds"] or r["opening_odds"]
        if o is None:
            continue
        if sel == "over_25":
            by_fx[fid]["over"].append(float(o))
        else:
            by_fx[fid]["under"].append(float(o))

    # totals_market_shadow — research only if no timestamp
    try:
        tot = conn.execute(
            f"""
            SELECT fixture_id, over_odds, under_odds, odds_timestamp, line
            FROM totals_market_shadow_snapshots
            WHERE line=2.5 AND fixture_id IN ({placeholders})
            """,
            fx_ids,
        ).fetchall()
    except sqlite3.Error:
        tot = []
    tot_by = {int(r["fixture_id"]): dict(r) for r in tot}

    official = research = unpriced = 0
    for row in rows:
        fid = int(row["fixture_id"])
        if fid in by_fx and by_fx[fid]["over"] and by_fx[fid]["under"]:
            row["ou_odds_over"] = sum(by_fx[fid]["over"]) / len(by_fx[fid]["over"])
            row["ou_odds_under"] = sum(by_fx[fid]["under"]) / len(by_fx[fid]["under"])
            row["ou_odds_class"] = "OFFICIAL_PRICED"
            official += 1
        elif fid in tot_by and tot_by[fid].get("over_odds") and tot_by[fid].get("under_odds"):
            row["ou_odds_over"] = float(tot_by[fid]["over_odds"])
            row["ou_odds_under"] = float(tot_by[fid]["under_odds"])
            if tot_by[fid].get("odds_timestamp"):
                row["ou_odds_class"] = "OFFICIAL_PRICED"
                official += 1
            else:
                row["ou_odds_class"] = "RESEARCH_SCREENSHOT_PRICED"
                research += 1
        else:
            unpriced += 1
            row["ou_odds_class"] = "UNPRICED"
    return {"official_priced": official, "research_priced": research, "unpriced": unpriced, "csv_odds_rows": len(odds_rows)}


def build_ledger() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    tf, tf_m = load_tf_rows()
    hist, hist_m = load_historical_rows()
    tf_ids = {int(r["fixture_id"]) for r in tf}
    # prefer TF when overlap
    hist_only = [r for r in hist if int(r["fixture_id"]) not in tf_ids]
    combined = tf + hist_only
    manifest = {
        "true_forward": tf_m,
        "historical": hist_m,
        "tf_n": len(tf),
        "historical_n": len(hist),
        "historical_only_n": len(hist_only),
        "combined_unique_n": len(combined),
        "overlap_dropped_from_hist": len(hist) - len(hist_only),
        "read_only": True,
    }
    return combined, manifest
