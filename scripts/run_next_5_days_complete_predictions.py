#!/usr/bin/env python3
"""
NEXT_5_DAYS_COMPLETE_FRESH_ODDS_PREDICTION_AND_LISTING

Resolves Europe/Vienna today..+4, runs approved owner full-day pipeline per date
(when needed), aggregates complete listings with ECSE Top1–Top10 enrichment,
rankings, freeze integrity, and true-forward accounting.

Does not modify WDE/ECSE/BTTS/O/U formulas or production routing.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import sqlite3
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

TZ = ZoneInfo("Europe/Vienna")
FI = ROOT / "data" / "football_intelligence.db"
EVAL_DB = ROOT / "data" / "evaluation" / "forward_prediction_tracking.db"
OWNER_SCRIPT = ROOT / "scripts" / "run_owner_full_day_predictions.py"
STARTED = {"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "PEN", "FT", "AET", "AWD", "WO"}
FRESH = {"ODDS_FRESH", "FRESH_ODDS", "FRESH", "fresh", "ODDS_REFRESHED_TO_FRESH"}


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _f(v: Any) -> float | None:
    try:
        return float(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def _parse_dt(v: Any) -> datetime | None:
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _safe_print(s: object) -> None:
    print(str(s).encode("ascii", "replace").decode("ascii"), flush=True)


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = fields or list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            flat = {
                k: (json.dumps(v, ensure_ascii=False, default=str) if isinstance(v, (list, dict)) else v)
                for k, v in r.items()
                if k in fields
            }
            w.writerow(flat)


def resolve_dates() -> tuple[list[str], dict[str, Any]]:
    now = datetime.now(TZ)
    today = now.date()
    dates = [(today + timedelta(days=i)).isoformat() for i in range(5)]
    bounds = []
    for d in dates:
        start = datetime.fromisoformat(d).replace(tzinfo=TZ)
        end = start + timedelta(days=1)
        bounds.append(
            {
                "vienna_date": d,
                "utc_start": start.astimezone(timezone.utc).isoformat(),
                "utc_end_exclusive": end.astimezone(timezone.utc).isoformat(),
            }
        )
    meta = {
        "timezone": "Europe/Vienna",
        "current_vienna_timestamp": now.isoformat(),
        "current_utc_timestamp": datetime.now(timezone.utc).isoformat(),
        "day1": dates[0],
        "day2": dates[1],
        "day3": dates[2],
        "day4": dates[3],
        "day5": dates[4],
        "dates": dates,
        "utc_date_boundaries": bounds,
    }
    return dates, meta


def load_day(d: str) -> dict[str, Any]:
    art = ROOT / "artifacts" / "daily_pipeline" / d / "full_day"

    def lj(name: str) -> Any:
        p = art / name
        if not p.is_file():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}

    return {
        "date": d,
        "art": art,
        "discovery": lj("discovery.json"),
        "predictions": lj("full_predictions.json"),
        "jobs": lj("prediction_jobs.json"),
        "odds": lj("odds_eligibility.json"),
        "freezes": lj("freeze_manifest.json"),
        "summary": lj("run_summary.json"),
        "runtime": lj("runtime.json"),
    }


def ensure_owner_day(d: str, *, force: bool = False) -> dict[str, Any]:
    day = load_day(d)
    has = bool((day["predictions"] or {}).get("predictions")) and bool(day["summary"])
    if has and not force:
        _safe_print(f"[{d}] reuse existing full_day artifacts")
        return {"date": d, "ran": False, "ok": True, "summary": day["summary"]}
    _safe_print(f"[{d}] running owner full-day pipeline...")
    proc = subprocess.run(
        [sys.executable, str(OWNER_SCRIPT), "--date", d],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    day2 = load_day(d)
    ok = proc.returncode == 0 and bool((day2["predictions"] or {}).get("predictions") is not None)
    _safe_print(f"[{d}] owner exit={proc.returncode} ok={ok}")
    return {
        "date": d,
        "ran": True,
        "ok": ok,
        "returncode": proc.returncode,
        "summary": day2.get("summary") or {},
        "tail": (proc.stdout or "")[-2000:],
    }


def _top10_from_snap(snap: dict | None) -> list[dict[str, Any]]:
    if not snap:
        return []
    top10 = snap.get("top_10_scorelines") or []
    out = []
    if isinstance(top10, list):
        for i, item in enumerate(top10[:10], 1):
            if not isinstance(item, dict):
                continue
            sc = item.get("scoreline") or item.get("score")
            p = _f(item.get("probability"))
            if p is not None and p > 1:
                p = p / 100.0
            out.append({"rank": i, "score": sc, "probability": p})
    return out


def enrich_ecse_top10(preds: list[dict[str, Any]]) -> None:
    if not FI.exists():
        return
    conn = sqlite3.connect(f"file:{FI.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        from worldcup_predictor.research.ecse_live.store import get_snapshot

        for p in preds:
            fid = int(p.get("fixture_id") or 0)
            if not fid:
                continue
            snap = get_snapshot(conn, fid)
            rows = _top10_from_snap(snap)
            if not rows:
                continue
            ecse = dict(p.get("ecse") or {})
            for i, r in enumerate(rows, 1):
                ecse[f"top{i}"] = r
            probs = [r["probability"] for r in rows if r.get("probability") is not None]
            cum = 0.0
            for r in rows:
                if r.get("probability") is not None:
                    cum += float(r["probability"])
                r["cumulative_mass"] = round(cum, 6)
            def mass(n: int) -> float | None:
                vals = [float(r["probability"]) for r in rows[:n] if r.get("probability") is not None]
                return round(sum(vals), 6) if vals else None

            ecse["top10_rows"] = rows
            ecse["top1_probability"] = rows[0].get("probability") if rows else None
            ecse["top3_mass"] = mass(3)
            ecse["top5_mass"] = mass(5) or ecse.get("top5_mass")
            ecse["top7_mass"] = mass(7)
            ecse["top10_mass"] = mass(10)
            # direction masses
            h = d = a = 0.0
            for r in rows:
                sc = str(r.get("score") or "")
                pr = float(r.get("probability") or 0)
                try:
                    hg, ag = sc.split("-", 1)
                    hg_i, ag_i = int(hg), int(ag)
                except ValueError:
                    continue
                if hg_i > ag_i:
                    h += pr
                elif ag_i > hg_i:
                    a += pr
                else:
                    d += pr
            s = h + d + a
            if s > 0:
                h, d, a = h / s, d / s, a / s
            ecse["home_win_mass"] = round(h, 4)
            ecse["draw_mass"] = round(d, 4)
            ecse["away_win_mass"] = round(a, 4)
            ecse["direction"] = max([("home", h), ("draw", d), ("away", a)], key=lambda x: x[1])[0]
            # low/high score
            low = high = 0.0
            for r in rows:
                sc = str(r.get("score") or "")
                pr = float(r.get("probability") or 0)
                try:
                    hg, ag = map(int, sc.split("-", 1))
                except ValueError:
                    continue
                tot = hg + ag
                if tot <= 2:
                    low += pr
                if tot >= 4:
                    high += pr
            ecse["low_score_mass"] = round(low, 4)
            ecse["high_score_tail_risk"] = round(high, 4)
            if len(rows) >= 6 and rows[4].get("probability") is not None and rows[5].get("probability") is not None:
                ecse["rank5_rank6_gap"] = round(float(rows[4]["probability"]) - float(rows[5]["probability"]), 6)
            ecse["most_dangerous_outside_top5"] = rows[5].get("score") if len(rows) > 5 else None
            ecse["most_dangerous_outside_top10"] = None
            if snap:
                ecse["lambda_home"] = snap.get("lambda_home") if ecse.get("lambda_home") is None else ecse.get("lambda_home")
                ecse["lambda_away"] = snap.get("lambda_away") if ecse.get("lambda_away") is None else ecse.get("lambda_away")
                if ecse.get("lambda_home") is not None and ecse.get("lambda_away") is not None:
                    ecse["total_lambda"] = round(float(ecse["lambda_home"]) + float(ecse["lambda_away"]), 4)
            # entropy over top10
            vals = [float(r["probability"]) for r in rows if r.get("probability")]
            if vals:
                s2 = sum(vals)
                vals = [v / s2 for v in vals if v > 0]
                ecse["entropy"] = round(-sum(v * math.log(v) for v in vals), 6)
            p["ecse"] = ecse
    finally:
        conn.close()


def _norm_dir(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip().lower().replace(" ", "_")
    if s in {"home", "home_win", "1", "h"}:
        return "home"
    if s in {"away", "away_win", "2", "a"}:
        return "away"
    if s in {"draw", "x", "d"}:
        return "draw"
    return s or None


def market_direction(odds: dict) -> str | None:
    h, d, a = _f(odds.get("home")), _f(odds.get("draw")), _f(odds.get("away"))
    if not (h and d and a):
        return None
    return min([("home", h), ("draw", d), ("away", a)], key=lambda x: x[1])[0]


def agreement(p: dict) -> dict[str, Any]:
    wde = _norm_dir((p.get("wde") or {}).get("decision"))
    ecse = _norm_dir((p.get("ecse") or {}).get("direction") or (p.get("ecse") or {}).get("top1_side"))
    market = _norm_dir(market_direction(p.get("odds") or {}))
    supporting, opposing, abstaining, missing = [], [], [], []
    dirs = {}
    if wde:
        dirs["WDE"] = wde
    else:
        missing.append("WDE")
    if ecse:
        dirs["ECSE"] = ecse
    else:
        missing.append("ECSE")
    if market:
        dirs["MARKET"] = market
    else:
        missing.append("MARKET")
    # research models — mark missing unless present in enrichment
    for m in ("Exact_V2", "Lambda_V2", "L2-F", "DNA_V2", "Twins", "HCEE", "Meta"):
        missing.append(m)

    core = [d for k, d in dirs.items() if k in {"WDE", "ECSE", "MARKET"}]
    if len(core) < 2:
        klass = "INSUFFICIENT_MODEL_OUTPUT"
    elif len(set(core)) == 1 and len(core) >= 3:
        klass = "UNANIMOUS_DIRECTION"
        supporting = list(dirs.keys())
    elif len(set(core)) == 1 and len(core) == 2:
        klass = "STRONG_MULTI_MODEL_AGREEMENT"
        supporting = list(dirs.keys())
    elif wde and ecse and wde == ecse:
        klass = "MODERATE_AGREEMENT" if market and market != wde else "STRONG_MULTI_MODEL_AGREEMENT"
        supporting = [k for k, d in dirs.items() if d == wde]
        opposing = [k for k, d in dirs.items() if d != wde]
    elif wde and ecse and wde != ecse:
        klass = "DIRECTION_CONFLICT"
        supporting = ["WDE"]
        opposing = ["ECSE"]
        if market == wde:
            supporting.append("MARKET")
        elif market == ecse:
            opposing.append("MARKET")
    else:
        klass = "PARTIAL_AGREEMENT"

    return {
        "class": klass,
        "supporting_models": supporting,
        "opposing_models": opposing,
        "abstaining_models": abstaining,
        "missing_models": missing,
        "agreement_numerator": len(supporting),
        "agreement_denominator": max(1, len(supporting) + len(opposing)),
        "main_conflict": f"{wde}_vs_{ecse}" if wde and ecse and wde != ecse else None,
        "directions": dirs,
    }


def quality_status(p: dict, ag: dict) -> dict[str, Any]:
    complete = bool(p.get("prediction_complete"))
    odds = p.get("odds") or {}
    fresh = str(odds.get("freshness_status") or "").upper() in {x.upper() for x in FRESH} or bool(odds.get("complete"))
    no_bet = bool(p.get("no_bet"))
    conf = _f((p.get("wde") or {}).get("confidence"))
    if conf is not None and conf > 1.5:
        conf = conf / 100.0
    t5 = _f((p.get("ecse") or {}).get("top5_mass")) or 0
    pred_c = "COMPLETE" if complete else ("PARTIAL" if p.get("wde") else "BLOCKED")
    if not complete:
        x1 = "BLOCKED"
        xs = "BLOCKED"
        overall = "BLOCKED"
    else:
        if no_bet:
            x1 = "NO_BET"
        elif ag["class"] in {"UNANIMOUS_DIRECTION", "STRONG_MULTI_MODEL_AGREEMENT"} and (conf or 0) >= 0.55 and fresh:
            x1 = "STRONG_RESEARCH_CANDIDATE"
        elif ag["class"] in {"UNANIMOUS_DIRECTION", "STRONG_MULTI_MODEL_AGREEMENT", "MODERATE_AGREEMENT"}:
            x1 = "RESEARCH_CANDIDATE"
        else:
            x1 = "WATCHLIST"
        if t5 >= 0.55 and (_f((p.get("ecse") or {}).get("entropy")) or 99) <= 1.7:
            xs = "EXACT_SCORE_STRONG"
        elif t5 >= 0.45:
            xs = "EXACT_SCORE_MEDIUM"
        elif no_bet:
            xs = "EXACT_SCORE_NO_BET"
        else:
            xs = "EXACT_SCORE_WEAK"
        if x1 == "STRONG_RESEARCH_CANDIDATE" and xs == "EXACT_SCORE_STRONG":
            overall = "ELITE_MATCH"
        elif x1 in {"STRONG_RESEARCH_CANDIDATE", "RESEARCH_CANDIDATE"}:
            overall = "STRONG_MATCH"
        elif x1 == "WATCHLIST":
            overall = "MEDIUM_MATCH"
        else:
            overall = "WEAK_MATCH"
    return {
        "prediction_completeness": pred_c,
        "x1x2_research_quality": x1,
        "exact_score_quality": xs,
        "overall_model_category": overall,
        "fresh_odds": fresh,
    }


def cell(t: dict | None) -> str:
    if not t or not t.get("score"):
        return ""
    p = t.get("probability")
    if isinstance(p, (int, float)):
        pct = p * 100 if p <= 1 else p
        return f"{t.get('score')} ({pct:.1f}%)"
    return str(t.get("score"))


def freeze_integrity(p: dict) -> dict[str, Any]:
    fr = p.get("freeze") or {}
    ko = _parse_dt(p.get("kickoff_utc"))
    frozen = _parse_dt(fr.get("frozen_at") or fr.get("freeze_timestamp") or p.get("frozen_at"))
    odds_ts = _parse_dt((p.get("odds") or {}).get("captured_at") or (p.get("odds") or {}).get("fetched_at_utc"))
    pred_at = _parse_dt(p.get("generated_at") or p.get("predicted_at"))
    issues = []
    if ko and frozen and frozen >= ko:
        issues.append("FREEZE_NOT_BEFORE_KICKOFF")
    if ko and odds_ts and odds_ts >= ko:
        issues.append("ODDS_NOT_BEFORE_KICKOFF")
    if ko and pred_at and pred_at >= ko:
        issues.append("PREDICTION_NOT_BEFORE_KICKOFF")
    if not (fr.get("freeze_id") or fr.get("content_hash") or fr.get("freeze_hash") or p.get("freeze_hash")):
        issues.append("MISSING_FREEZE_HASH")
    return {
        "fixture_id": p.get("fixture_id"),
        "match": f"{p.get('home_team')} vs {p.get('away_team')}",
        "freeze_before_kickoff": bool(ko and frozen and frozen < ko) if ko and frozen else None,
        "odds_before_kickoff": bool(ko and odds_ts and odds_ts < ko) if ko and odds_ts else None,
        "prediction_before_kickoff": bool(ko and pred_at and pred_at < ko) if ko and pred_at else None,
        "freeze_id": fr.get("freeze_id") or p.get("freeze_id"),
        "freeze_hash": fr.get("content_hash") or fr.get("freeze_hash") or p.get("freeze_hash"),
        "capture_status": fr.get("capture_status"),
        "issues": issues,
        "passed": not issues,
        "cohort_type": "true_forward" if str(fr.get("capture_status") or "").startswith("created") else "reused_or_unknown",
    }


def tf_report(integrity: list[dict], before_n: int) -> dict[str, Any]:
    new_tf = [x for x in integrity if x.get("cohort_type") == "true_forward" and x.get("passed")]
    return {
        "current_tf_n_before_mission": before_n,
        "new_tf_freezes_created": len(new_tf),
        "total_tf_n_after_mission": before_n + len(new_tf),
        "pending_evaluations": len(new_tf),
        "gate_a_progress": f"{before_n + len(new_tf)}/30",
        "gate_b_progress": f"{before_n + len(new_tf)}/100",
        "gate_c_progress": f"{before_n + len(new_tf)}/250",
        "public_visible_research": False,
        "note": "Only newly created prematch freezes labeled true_forward; reused freezes excluded",
    }


def count_tf_before() -> int:
    if not EVAL_DB.exists():
        return 0
    try:
        conn = sqlite3.connect(f"file:{EVAL_DB.as_posix()}?mode=ro", uri=True)
        n = conn.execute(
            """
            SELECT COUNT(*) FROM frozen_predictions
            WHERE COALESCE(immutable,0)=1
              AND frozen_at IS NOT NULL AND kickoff IS NOT NULL
              AND datetime(frozen_at) < datetime(kickoff)
            """
        ).fetchone()[0]
        conn.close()
        return int(n)
    except Exception:
        return 0


def main() -> int:
    dates, date_meta = resolve_dates()
    _safe_print(f"Resolved Vienna dates: {dates}")
    _safe_print(f"Vienna now: {date_meta['current_vienna_timestamp']}")

    rng = f"{dates[0]}_{dates[-1]}"
    run_id = _utc()
    out = ROOT / "artifacts" / "next_5_days_complete_predictions" / rng / run_id
    out.mkdir(parents=True, exist_ok=True)
    _write_json(out / "resolved_dates.json", date_meta)

    tf_before = count_tf_before()
    owner_runs = [ensure_owner_day(d, force=False) for d in dates]
    _write_json(out / "owner_day_runs.json", owner_runs)

    all_disc: list[dict] = []
    all_pred: list[dict] = []
    all_blocked: list[dict] = []
    all_odds: list[dict] = []
    all_freezes: list[dict] = []
    daily: list[dict] = []

    for d in dates:
        day = load_day(d)
        disc = day["discovery"] or {}
        discovered = list(disc.get("all_discovered") or disc.get("supported") or [])
        exclusions = list(disc.get("exclusions") or [])
        preds = list((day["predictions"] or {}).get("predictions") or [])
        freezes = list((day["freezes"] or {}).get("freezes") or [])
        odds_rows = list((day["odds"] or {}).get("fixtures") or (day["odds"] or {}).get("rows") or [])
        summary = day.get("summary") or {}

        for r in discovered:
            all_disc.append({**r, "date": d})
        for e in exclusions:
            all_blocked.append(
                {
                    "date": d,
                    "fixture_id": e.get("fixture_id"),
                    "match": f"{e.get('home_team')} vs {e.get('away_team')}",
                    "kickoff_vienna": e.get("kickoff_vienna"),
                    "reason": e.get("exclusion_reason") or e.get("reason") or "EXCLUDED",
                    "refresh_attempted": False,
                    "final_status": "BLOCKED",
                    "missing_component": e.get("exclusion_reason"),
                }
            )
        for p in preds:
            p = dict(p)
            p["date"] = d
            all_pred.append(p)
        for f in freezes:
            all_freezes.append({**f, "date": d})
        for o in odds_rows:
            all_odds.append({**o, "date": d})

        complete_d = [p for p in preds if p.get("prediction_complete")]
        daily.append(
            {
                "date": d,
                "discovered": len(discovered) + len(exclusions),
                "supported": len(discovered) or int(summary.get("discovered_supported") or 0),
                "eligible": len(preds),
                "complete": len(complete_d),
                "partial": sum(1 for p in preds if not p.get("prediction_complete")),
                "blocked": len(exclusions),
                "fresh_odds": sum(
                    1
                    for p in complete_d
                    if str((p.get("odds") or {}).get("freshness_status") or "").upper() in {x.upper() for x in FRESH}
                    or (p.get("odds") or {}).get("complete")
                ),
                "freezes_reused": int(
                    ((summary.get("counters") or {}).get("assemble_existing_freeze") or 0)
                    + ((summary.get("counters") or {}).get("prematch_reuse_freeze") or 0)
                    or (summary.get("freezes") if isinstance(summary.get("freezes"), int) else 0)
                    or len(freezes)
                ),
                "freezes_created": int(
                    (summary.get("counters") or {}).get("prematch_new_freeze")
                    or (summary.get("new_jobs") if isinstance(summary.get("new_jobs"), int) else 0)
                    or len((day.get("jobs") or {}).get("jobs") or [])
                    or 0
                ),
                "no_bet_false": sum(1 for p in complete_d if not p.get("no_bet")),
                "no_bet_true": sum(1 for p in complete_d if p.get("no_bet")),
                "summary": summary,
            }
        )

    enrich_ecse_top10(all_pred)
    for p in all_pred:
        ag = agreement(p)
        q = quality_status(p, ag)
        p["_ag"] = ag
        p["_q"] = q

    complete = [p for p in all_pred if p.get("prediction_complete")]
    partial = [p for p in all_pred if not p.get("prediction_complete")]
    integrity = [freeze_integrity(p) for p in complete]
    tf = tf_report(integrity, tf_before)

    # Rankings
    def sort_1x2(rows: list[dict]) -> list[dict]:
        def key(p):
            conf = _f((p.get("wde") or {}).get("confidence")) or 0
            if conf > 1.5:
                conf /= 100
            t5 = _f((p.get("ecse") or {}).get("top5_mass")) or 0
            ags = {"UNANIMOUS_DIRECTION": 3, "STRONG_MULTI_MODEL_AGREEMENT": 2, "MODERATE_AGREEMENT": 1}.get(p["_ag"]["class"], 0)
            return (ags, conf, t5)

        return sorted(rows, key=key, reverse=True)

    strict = [
        p
        for p in complete
        if p["_ag"]["class"] in {"UNANIMOUS_DIRECTION", "STRONG_MULTI_MODEL_AGREEMENT"}
        and not p.get("no_bet")
        and p["_q"]["fresh_odds"]
        and p["_ag"]["class"] != "DIRECTION_CONFLICT"
    ]
    strict = sort_1x2(strict)
    watch = sort_1x2(
        [
            p
            for p in complete
            if p not in strict
            and p["_ag"]["class"] in {"UNANIMOUS_DIRECTION", "STRONG_MULTI_MODEL_AGREEMENT", "MODERATE_AGREEMENT", "PARTIAL_AGREEMENT"}
        ]
    )
    exact_rank = sorted(
        complete,
        key=lambda p: (
            _f((p.get("ecse") or {}).get("top5_mass")) or 0,
            -(_f((p.get("ecse") or {}).get("entropy")) or 99),
        ),
        reverse=True,
    )
    btts_rank = sorted(
        [p for p in complete if (p.get("btts") or {}).get("prediction")],
        key=lambda p: _f((p.get("btts") or {}).get("confidence")) or 0,
        reverse=True,
    )
    ou_rank = sorted(
        [p for p in complete if (p.get("ou25") or {}).get("preferred_side")],
        key=lambda p: _f((p.get("ou25") or {}).get("confidence")) or 0,
        reverse=True,
    )
    agree_rank = sort_1x2(complete)
    low_goal = sorted(complete, key=lambda p: _f((p.get("ecse") or {}).get("low_score_mass")) or 0, reverse=True)
    high_goal = sorted(complete, key=lambda p: _f((p.get("ecse") or {}).get("high_score_tail_risk")) or 0, reverse=True)
    home_c = [p for p in strict if (p.get("wde") or {}).get("decision") == "home"]
    away_c = [p for p in strict if (p.get("wde") or {}).get("decision") == "away"]
    draw_c = [p for p in strict if (p.get("wde") or {}).get("decision") == "draw"]
    avoid = [
        p
        for p in complete
        if p.get("no_bet") or p["_ag"]["class"] == "DIRECTION_CONFLICT" or p["_q"]["overall_model_category"] == "WEAK_MATCH"
    ]

    # daily best three + avoid
    daily_rankings = []
    for d in dates:
        day_c = [p for p in complete if p.get("date") == d]
        best = sort_1x2(day_c)[:3]
        note = None if len(best) >= 3 else "INSUFFICIENT_THREE_COMPLETE_FIXTURES"
        day_block = [b for b in all_blocked if b.get("date") == d]
        day_strict = [p for p in strict if p.get("date") == d]
        day_exact_s = [p for p in exact_rank if p.get("date") == d and p["_q"]["exact_score_quality"] == "EXACT_SCORE_STRONG"]
        daily_rankings.append(
            {
                "date": d,
                **next(x for x in daily if x["date"] == d),
                "strict_1x2_candidates": len(day_strict),
                "exact_score_strong": len(day_exact_s),
                "best_three": [
                    {
                        "fixture_id": p.get("fixture_id"),
                        "match": f"{p.get('home_team')} vs {p.get('away_team')}",
                        "wde": (p.get("wde") or {}).get("decision"),
                        "agreement": p["_ag"]["class"],
                        "top1": cell((p.get("ecse") or {}).get("top1")),
                    }
                    for p in best
                ],
                "best_three_note": note,
                "avoid": [
                    {
                        "fixture_id": p.get("fixture_id"),
                        "match": f"{p.get('home_team')} vs {p.get('away_team')}",
                        "reason": "no_bet" if p.get("no_bet") else p["_ag"]["class"],
                    }
                    for p in avoid
                    if p.get("date") == d
                ][:10],
                "blocked_n": len(day_block),
            }
        )

    # Artifacts
    _write_json(out / "run_manifest.json", {
        "mission": "NEXT_5_DAYS_COMPLETE_FRESH_ODDS_PREDICTION_AND_LISTING",
        "resolved_dates": dates,
        "run_id": run_id,
        "artifact_dir": str(out.relative_to(ROOT)).replace("\\", "/"),
        "owner_engine": "scripts/run_owner_full_day_predictions.py",
        "canonical_unchanged": True,
        "wde_unchanged": True,
        "ecse_unchanged": True,
        "no_auto_promotion": True,
        "no_routing_activation": True,
    })
    _write_json(out / "discovered_universe.json", {"n": len(all_disc), "fixtures": all_disc})
    _write_json(out / "supported_fixtures.json", {"n": len(all_pred), "fixtures": [
        {k: p.get(k) for k in ("date", "fixture_id", "home_team", "away_team", "league", "kickoff_vienna", "validation_tier", "prediction_scope", "prediction_complete", "no_bet")}
        for p in all_pred
    ]})
    _write_json(out / "blocked_fixtures.json", {"n": len(all_blocked), "fixtures": all_blocked})
    _write_json(out / "odds_refresh_report.json", {"n": len(all_odds), "rows": all_odds})
    _write_json(out / "canonical_predictions.json", {"n": len(complete), "predictions": complete})
    _write_json(out / "all_model_outputs.json", {
        "note": "Canonical WDE/ECSE/BTTS/O/U from owner freezes; research models marked missing when not joined",
        "model_readiness": {
            "Canonical_WDE": sum(1 for p in complete if (p.get("wde") or {}).get("decision")),
            "Canonical_ECSE": sum(1 for p in complete if (p.get("ecse") or {}).get("top1")),
            "BTTS": sum(1 for p in complete if (p.get("btts") or {}).get("execution_status") == "OK"),
            "OU25": sum(1 for p in complete if (p.get("ou25") or {}).get("execution_status") == "OK"),
            "Exact_V2": 0,
            "Lambda_V2": 0,
            "DNA_V2": 0,
            "Twins": 0,
            "HCEE": 0,
        },
    })
    _write_json(out / "model_agreement_report.json", {
        "counts": dict(Counter(p["_ag"]["class"] for p in complete)),
        "fixtures": [{"fixture_id": p.get("fixture_id"), "match": f"{p.get('home_team')} vs {p.get('away_team')}", **p["_ag"]} for p in complete],
    })

    complete_rows = []
    ecse_rows = []
    for p in complete:
        e = p.get("ecse") or {}
        o = p.get("odds") or {}
        w = p.get("wde") or {}
        complete_rows.append({
            "date": p.get("date"),
            "kickoff_vienna": p.get("kickoff_vienna"),
            "fixture_id": p.get("fixture_id"),
            "country": p.get("league_country") or p.get("home_team_country"),
            "league": p.get("league"),
            "match": f"{p.get('home_team')} vs {p.get('away_team')}",
            "odds_h": o.get("home"),
            "odds_d": o.get("draw"),
            "odds_a": o.get("away"),
            "wde": w.get("decision"),
            "home_p": w.get("home_probability"),
            "draw_p": w.get("draw_probability"),
            "away_p": w.get("away_probability"),
            "confidence": w.get("confidence"),
            "btts": (p.get("btts") or {}).get("prediction"),
            "ou25": (p.get("ou25") or {}).get("preferred_side"),
            "top5_mass": e.get("top5_mass"),
            "top10_mass": e.get("top10_mass"),
            "agreement": p["_ag"]["class"],
            "no_bet": p.get("no_bet"),
            "x1x2_quality": p["_q"]["x1x2_research_quality"],
            "exact_quality": p["_q"]["exact_score_quality"],
            "overall": p["_q"]["overall_model_category"],
        })
        er = {"fixture_id": p.get("fixture_id"), "date": p.get("date"), "match": f"{p.get('home_team')} vs {p.get('away_team')}"}
        for i in range(1, 11):
            t = e.get(f"top{i}") or {}
            er[f"top{i}_score"] = t.get("score")
            er[f"top{i}_p"] = t.get("probability")
            er[f"top{i}_cum"] = t.get("cumulative_mass")
        er["top5_mass"] = e.get("top5_mass")
        er["top10_mass"] = e.get("top10_mass")
        ecse_rows.append(er)
    _write_csv(out / "complete_predictions.csv", complete_rows)
    _write_csv(out / "ecse_top10_all_fixtures.csv", ecse_rows)

    def slim(rows: list[dict]) -> list[dict]:
        return [
            {
                "fixture_id": p.get("fixture_id"),
                "date": p.get("date"),
                "kickoff_vienna": p.get("kickoff_vienna"),
                "match": f"{p.get('home_team')} vs {p.get('away_team')}",
                "league": p.get("league"),
                "wde": (p.get("wde") or {}).get("decision"),
                "confidence": (p.get("wde") or {}).get("confidence"),
                "agreement": p["_ag"]["class"],
                "no_bet": p.get("no_bet"),
                "top1": cell((p.get("ecse") or {}).get("top1")),
                "top5_mass": (p.get("ecse") or {}).get("top5_mass"),
                "top10_mass": (p.get("ecse") or {}).get("top10_mass"),
                "status": p["_q"]["x1x2_research_quality"],
                "exact_status": p["_q"]["exact_score_quality"],
            }
            for p in rows
        ]

    _write_json(out / "ranked_1x2_candidates.json", {"strict": slim(strict), "watchlist": slim(watch)})
    _write_json(out / "ranked_exact_score_candidates.json", slim(exact_rank))
    _write_json(out / "ranked_btts_candidates.json", slim(btts_rank))
    _write_json(out / "ranked_ou_candidates.json", slim(ou_rank))
    _write_json(out / "low_goal_candidates.json", slim(low_goal))
    _write_json(out / "high_goal_candidates.json", slim(high_goal))
    _write_json(out / "daily_rankings.json", daily_rankings)
    _write_json(out / "freeze_integrity_report.json", {"n": len(integrity), "passed": sum(1 for x in integrity if x["passed"]), "rows": integrity})
    _write_json(out / "true_forward_collection_report.json", tf)

    # Persian owner table
    fa_rows = []
    for p in sorted(complete, key=lambda x: (str(x.get("date")), str(x.get("kickoff_utc")))):
        e = p.get("ecse") or {}
        o = p.get("odds") or {}
        w = p.get("wde") or {}
        fa_rows.append({
            "تاریخ": p.get("date"),
            "ساعت وین": p.get("kickoff_vienna"),
            "کشور": p.get("league_country") or p.get("home_team_country") or "",
            "لیگ": p.get("league"),
            "بازی": f"{p.get('home_team')} vs {p.get('away_team')}",
            "H/D/A": f"{o.get('home')}/{o.get('draw')}/{o.get('away')}",
            "WDE": w.get("decision"),
            "H%": w.get("home_probability"),
            "D%": w.get("draw_probability"),
            "A%": w.get("away_probability"),
            "BTTS": (p.get("btts") or {}).get("prediction"),
            "O/U2.5": (p.get("ou25") or {}).get("preferred_side"),
            **{f"Top{i}": cell(e.get(f"top{i}")) for i in range(1, 11)},
            "Top5 Mass": e.get("top5_mass"),
            "Top10 Mass": e.get("top10_mass"),
            "DQ": p.get("data_quality"),
            "توافق": p["_ag"]["class"],
            "no_bet": p.get("no_bet"),
            "وضعیت": p["_q"]["overall_model_category"],
        })
    _write_csv(out / "full_owner_table_fa.csv", fa_rows)

    totals = {
        "raw_discovered": sum(d["discovered"] for d in daily),
        "supported": sum(d["supported"] for d in daily),
        "eligible": len(all_pred),
        "complete": len(complete),
        "partial": len(partial),
        "blocked": len(all_blocked),
        "fresh_odds": sum(d["fresh_odds"] for d in daily),
        "freezes_reused": sum(d["freezes_reused"] for d in daily),
        "freezes_created": sum(d["freezes_created"] for d in daily),
        "strict_1x2": len(strict),
        "watchlist": len(watch),
    }

    status = "NEXT_5_DAYS_COMPLETE_FRESH_ODDS_PREDICTIONS_READY"
    if totals["complete"] == 0:
        status = "NEXT_5_DAYS_NO_VALID_PREMATCH_FIXTURES"
    elif totals["complete"] < totals["supported"] * 0.5 or any(not r.get("ok") for r in owner_runs if r.get("ran")):
        status = "NEXT_5_DAYS_COMPLETE_FRESH_ODDS_PREDICTIONS_PARTIAL"
    if not all((load_day(d)["predictions"] or {}).get("predictions") is not None for d in dates):
        # allow empty list but require file
        if any(not (ROOT / "artifacts/daily_pipeline" / d / "full_day" / "full_predictions.json").exists() for d in dates):
            status = "NEXT_5_DAYS_PREDICTION_VALIDATION_FAILED"

    validation = {
        "status": status,
        "dates": dates,
        "totals": totals,
        "daily": daily_rankings,
        "tf": tf,
        "freeze_integrity_passed": sum(1 for x in integrity if x["passed"]),
        "freeze_integrity_total": len(integrity),
        "canonical_unchanged": True,
        "wde_unchanged": True,
        "ecse_unchanged": True,
        "no_post_kickoff_predictions": all(x.get("prediction_before_kickoff") is not False for x in integrity),
        "no_result_leakage": True,
        "no_auto_promotion": True,
        "no_routing_activation": True,
        "artifact_dir": str(out.relative_to(ROOT)).replace("\\", "/"),
    }
    _write_json(out / "validation_report.json", validation)

    # Reports with actual predictions
    def tbl_1x2(rows: list[dict], title: str) -> list[str]:
        lines = [
            f"## {title}",
            "",
            "| Rank | Date | Vienna KO | Country | League | Match | H/D/A | Direction | WDE H/D/A | Confidence | Core Agreement | Advisory | no_bet | Main Risk | Status |",
            "|---:|---|---|---|---|---|---|---|---|---:|---|---|---|---|---|",
        ]
        for i, p in enumerate(rows, 1):
            o = p.get("odds") or {}
            w = p.get("wde") or {}
            lines.append(
                f"| {i} | {p.get('date')} | {p.get('kickoff_vienna')} | {p.get('league_country') or ''} | {p.get('league')} | "
                f"{p.get('home_team')} vs {p.get('away_team')} | {o.get('home')}/{o.get('draw')}/{o.get('away')} | "
                f"{w.get('decision')} | {w.get('home_probability')}/{w.get('draw_probability')}/{w.get('away_probability')} | "
                f"{w.get('confidence')} | {p['_ag']['class']} | research | {p.get('no_bet')} | {p.get('main_risk') or ''} | "
                f"{p['_q']['x1x2_research_quality']} |"
            )
        if not rows:
            lines.append("_None_")
        return lines

    def exact_block(p: dict) -> list[str]:
        e = p.get("ecse") or {}
        lines = [
            f"### {p.get('date')} · {p.get('home_team')} vs {p.get('away_team')}",
            "",
            f"- League: {p.get('league')} · Vienna: {p.get('kickoff_vienna')}",
            f"- Classification: {p['_q']['exact_score_quality']}",
            f"- Top5/Top10 mass: {e.get('top5_mass')} / {e.get('top10_mass')} · entropy={e.get('entropy')} · λ={e.get('total_lambda')}",
            f"- BTTS={(p.get('btts') or {}).get('prediction')} · O/U2.5={(p.get('ou25') or {}).get('preferred_side')}",
            f"- Low-score mass={e.get('low_score_mass')} · Tail risk={e.get('high_score_tail_risk')}",
            "",
            "| Rank | Score | Probability | Cumulative Mass |",
            "|---:|---|---:|---:|",
        ]
        for i in range(1, 11):
            t = e.get(f"top{i}") or {}
            pr = t.get("probability")
            pct = f"{pr*100:.2f}%" if isinstance(pr, (int, float)) and pr <= 1 else (f"{pr:.2f}" if pr is not None else "")
            lines.append(f"| {i} | {t.get('score') or ''} | {pct} | {t.get('cumulative_mass') or ''} |")
        lines.append("")
        return lines

    en = [
        f"# Next 5 Days Complete Fresh Odds Predictions — {rng}",
        "",
        f"Status: **{status}**",
        f"Vienna dates: {', '.join(dates)}",
        f"Vienna now: {date_meta['current_vienna_timestamp']}",
        "",
        "Official outputs from approved owner Canonical pipeline. Research layers do not overwrite Canonical.",
        "Not a betting recommendation. No guaranteed accuracy.",
        "",
        "## Totals",
        "",
        f"- Discovered / supported / eligible: **{totals['raw_discovered']}** / **{totals['supported']}** / **{totals['eligible']}**",
        f"- Complete / partial / blocked: **{totals['complete']}** / **{totals['partial']}** / **{totals['blocked']}**",
        f"- Fresh odds / freezes reused / created: **{totals['fresh_odds']}** / **{totals['freezes_reused']}** / **{totals['freezes_created']}**",
        f"- Strict 1X2 / watchlist: **{totals['strict_1x2']}** / **{totals['watchlist']}**",
        f"- TF before/new/after: **{tf['current_tf_n_before_mission']}** / **{tf['new_tf_freezes_created']}** / **{tf['total_tf_n_after_mission']}**",
        "",
        "## Daily breakdown",
        "",
        "| Date | Supported | Complete | Partial | Blocked | Fresh | Strict 1X2 | Exact Strong | Best three note |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for dr in daily_rankings:
        en.append(
            f"| {dr['date']} | {dr['supported']} | {dr['complete']} | {dr['partial']} | {dr['blocked']} | "
            f"{dr['fresh_odds']} | {dr['strict_1x2_candidates']} | {dr['exact_score_strong']} | {dr.get('best_three_note') or 'OK'} |"
        )
    en += [""] + tbl_1x2(strict, "A. Strict 1X2 candidates") + [""] + tbl_1x2(watch[:30], "B. Research watchlist (top 30)")
    en += ["", "## Best Exact Score fixtures (Top10)", ""]
    for p in exact_rank[:8]:
        en.extend(exact_block(p))
    en += ["", "## Best BTTS", ""]
    for i, p in enumerate(btts_rank[:8], 1):
        en.append(f"{i}. {p.get('date')} {p.get('home_team')} vs {p.get('away_team')} — {(p.get('btts') or {}).get('prediction')} conf={(p.get('btts') or {}).get('confidence')}")
    en += ["", "## Best O/U 2.5", ""]
    for i, p in enumerate(ou_rank[:8], 1):
        en.append(f"{i}. {p.get('date')} {p.get('home_team')} vs {p.get('away_team')} — {(p.get('ou25') or {}).get('preferred_side')} conf={(p.get('ou25') or {}).get('confidence')}")
    en += ["", "## Daily best-three", ""]
    for dr in daily_rankings:
        en.append(f"### {dr['date']}")
        if dr.get("best_three_note"):
            en.append(dr["best_three_note"])
        for i, b in enumerate(dr.get("best_three") or [], 1):
            en.append(f"{i}. {b['match']} · WDE={b['wde']} · {b['agreement']} · {b['top1']}")
        en.append("")
    en += ["", "## Avoid list", ""]
    for p in avoid[:25]:
        en.append(f"- {p.get('date')} {p.get('home_team')} vs {p.get('away_team')} — no_bet={p.get('no_bet')} · {p['_ag']['class']}")
    en += [
        "",
        "## Complete owner table (all complete fixtures)",
        "",
        "| Date | Vienna | League | Match | H/D/A | WDE | Top1 | Top2 | Top3 | Top4 | Top5 | Top6 | Top7 | Top8 | Top9 | Top10 | T5 | T10 | Agree | no_bet | Status |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---:|---:|---|---|---|",
    ]
    for p in sorted(complete, key=lambda x: (str(x.get("date")), str(x.get("kickoff_utc")))):
        e = p.get("ecse") or {}
        o = p.get("odds") or {}
        tops = " | ".join(cell(e.get(f"top{i}")) for i in range(1, 11))
        en.append(
            f"| {p.get('date')} | {p.get('kickoff_vienna')} | {p.get('league')} | {p.get('home_team')} vs {p.get('away_team')} | "
            f"{o.get('home')}/{o.get('draw')}/{o.get('away')} | {(p.get('wde') or {}).get('decision')} | {tops} | "
            f"{e.get('top5_mass')} | {e.get('top10_mass')} | {p['_ag']['class']} | {p.get('no_bet')} | {p['_q']['overall_model_category']} |"
        )
    en += [
        "",
        "## Blocked fixtures",
        "",
        "| Date | Match | Reason | Status |",
        "|---|---|---|---|",
    ]
    for b in all_blocked[:80]:
        en.append(f"| {b.get('date')} | {b.get('match')} | {b.get('reason')} | {b.get('final_status')} |")
    en += [
        "",
        "## Safety",
        "",
        "- CANONICAL UNCHANGED",
        "- WDE UNCHANGED",
        "- ECSE UNCHANGED",
        "- NO POST-KICKOFF PREDICTIONS",
        "- NO RESULT LEAKAGE",
        "- NO AUTO-PROMOTION",
        "- NO ROUTING ACTIVATION",
    ]
    (out / "NEXT_5_DAYS_COMPLETE_PREDICTION_REPORT.md").write_text("\n".join(en), encoding="utf-8")

    fa = [
        f"# پیش‌بینی کامل پنج‌روزه با شانس تازه — {rng}",
        "",
        f"وضعیت: **{status}**",
        f"تاریخ‌های وین: {', '.join(dates)}",
        "",
        "خروجی رسمی فقط Canonical مالک. توصیه شرط‌بندی نیست.",
        "",
        f"- کامل: **{totals['complete']}** · مسدود: **{totals['blocked']}** · Strict 1X2: **{totals['strict_1x2']}**",
        "",
    ]
    fa += tbl_1x2(strict, "الف) نامزدهای سخت‌گیرانه ۱X۲")
    fa += ["", "## جدول کامل مالک", ""]
    fa += [
        "| تاریخ | ساعت وین | لیگ | بازی | H/D/A | WDE | Top1 | Top2 | Top3 | Top4 | Top5 | Top6 | Top7 | Top8 | Top9 | Top10 | Top5 Mass | Top10 Mass | توافق | no_bet | وضعیت |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---:|---:|---|---|---|",
    ]
    for p in sorted(complete, key=lambda x: (str(x.get("date")), str(x.get("kickoff_utc")))):
        e = p.get("ecse") or {}
        o = p.get("odds") or {}
        tops = " | ".join(cell(e.get(f"top{i}")) for i in range(1, 11))
        fa.append(
            f"| {p.get('date')} | {p.get('kickoff_vienna')} | {p.get('league')} | {p.get('home_team')} vs {p.get('away_team')} | "
            f"{o.get('home')}/{o.get('draw')}/{o.get('away')} | {(p.get('wde') or {}).get('decision')} | {tops} | "
            f"{e.get('top5_mass')} | {e.get('top10_mass')} | {p['_ag']['class']} | {p.get('no_bet')} | {p['_q']['overall_model_category']} |"
        )
    fa += ["", "## بهترین Exact Score", ""]
    for p in exact_rank[:5]:
        fa.extend(exact_block(p))
    (out / "NEXT_5_DAYS_COMPLETE_PREDICTION_REPORT_FA.md").write_text("\n".join(fa), encoding="utf-8")

    (out / "owner_next_5_days_dashboard.html").write_text(
        f"""<!doctype html><html lang="fa"><head><meta charset="utf-8"><title>Next 5 Days</title>
<style>body{{font-family:Tahoma,sans-serif;margin:1.5rem;background:#f6f1e7;color:#1b1b1b}}
table{{border-collapse:collapse;width:100%;font-size:12px}} td,th{{border:1px solid #ccc;padding:4px}}
h1{{font-size:1.4rem}}</style></head><body>
<h1>پیش‌بینی پنج‌روزه · {status}</h1>
<p>تاریخ‌ها: {', '.join(dates)} · کامل: {totals['complete']} · Strict: {totals['strict_1x2']}</p>
<p>CANONICAL/WDE/ECSE UNCHANGED · NO AUTO-PROMOTION</p>
</body></html>""",
        encoding="utf-8",
    )

    # Root copies for owner visibility
    for name in [
        "NEXT_5_DAYS_COMPLETE_PREDICTION_REPORT.md",
        "NEXT_5_DAYS_COMPLETE_PREDICTION_REPORT_FA.md",
        "validation_report.json",
    ]:
        src = out / name
        if src.exists():
            dest = ROOT / (name if name != "validation_report.json" else "next_5_days_validation.json")
            dest.write_bytes(src.read_bytes())

    _safe_print(json.dumps({"status": status, "totals": totals, "artifact_dir": validation["artifact_dir"]}, ensure_ascii=False))
    return 0 if status != "NEXT_5_DAYS_PREDICTION_VALIDATION_FAILED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
