#!/usr/bin/env python3
"""
NEXT_4_DAYS_COMPLETE_MULTI_MODEL_PREDICTION_AND_RANKING
=======================================================

Controlled complete prediction mission for Vienna dates:
  2026-08-01 .. 2026-08-04 inclusive.

Reuses the approved owner full-day pipeline for discovery/odds/canonical/
freeze. Enriches with read-only research shadows. Does NOT promote Exact V2,
Portfolio Manager, Similarity Overlay, or OOD as selection layers.

NOT a production routing activation.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

TZ = ZoneInfo("Europe/Vienna")
PHASE = "NEXT_4_DAYS_COMPLETE_MULTI_MODEL_PREDICTION_AND_RANKING"
STATUS_READY = "NEXT_4_DAYS_COMPLETE_MULTI_MODEL_PREDICTION_READY"
STATUS_PARTIAL = "NEXT_4_DAYS_COMPLETE_MULTI_MODEL_PREDICTION_PARTIAL"
STATUS_NONE = "NEXT_4_DAYS_NO_ELIGIBLE_FIXTURES"
DEFAULT_DATES = ["2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04"]
FI = ROOT / "data" / "football_intelligence.db"


def _safe_print(s: object) -> None:
    print(str(s).encode("ascii", "replace").decode("ascii"), flush=True)


def _load_five_day():
    path = ROOT / "scripts" / "run_five_day_complete_prediction_scan.py"
    spec = importlib.util.spec_from_file_location("five_day_scan", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _f(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _json_dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = fields or list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fields})


def disk_gb(path: Path = Path("/")) -> dict[str, float]:
    try:
        u = shutil.disk_usage(str(path if path.exists() else ROOT))
        return {
            "total_gb": round(u.total / (1 << 30), 2),
            "used_gb": round(u.used / (1 << 30), 2),
            "free_gb": round(u.free / (1 << 30), 2),
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def load_ecse_top10(fixture_id: int) -> dict[str, Any]:
    """Load Canonical ECSE Top1–Top10 from prediction snapshots (immutable rows)."""
    out: dict[str, Any] = {
        "ranking_method": "canonical_ecse_rank",
        "probability_field": "probability",
        "normalization_status": "snapshot",
        "scores": [],
        "available": False,
    }
    if not FI.exists():
        return out
    conn = sqlite3.connect(str(FI))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT top_10_scorelines_json, lambda_home, lambda_away, model_version,
                   confidence_score, data_quality_score, generated_at, is_frozen,
                   prediction_scope
            FROM ecse_prediction_snapshots
            WHERE fixture_id=?
            ORDER BY id DESC LIMIT 1
            """,
            (int(fixture_id),),
        ).fetchone()
        if not row:
            return out
        tops = json.loads(row["top_10_scorelines_json"] or "[]")
        scores = []
        for i, t in enumerate(tops[:10], start=1):
            if isinstance(t, dict):
                scores.append(
                    {
                        "rank": int(t.get("rank") or i),
                        "score": str(t.get("scoreline") or t.get("score") or "").replace(" ", ""),
                        "probability": _f(t.get("probability")),
                    }
                )
            else:
                scores.append({"rank": i, "score": str(t).replace(" ", ""), "probability": None})
        probs = [s["probability"] or 0.0 for s in scores]
        out.update(
            {
                "available": bool(scores),
                "scores": scores,
                "top3_mass": round(sum(probs[:3]), 8),
                "top5_mass": round(sum(probs[:5]), 8),
                "top10_mass": round(sum(probs[:10]), 8),
                "lambda_home": _f(row["lambda_home"]),
                "lambda_away": _f(row["lambda_away"]),
                "lambda_total": None
                if row["lambda_home"] is None or row["lambda_away"] is None
                else round(float(row["lambda_home"]) + float(row["lambda_away"]), 8),
                "model_version": row["model_version"],
                "generated_at": row["generated_at"],
                "is_frozen": bool(row["is_frozen"]),
                "prediction_scope": row["prediction_scope"],
            }
        )
        # Entropy from top10 probs (partial)
        s = sum(probs) or 1.0
        ent = 0.0
        for p in probs:
            if p and p > 0:
                q = p / s
                ent -= q * math.log(q + 1e-15)
        out["entropy_top10_normalized"] = round(ent, 8)
        # Direction / tail mass
        home = draw = away = 0.0
        tail4 = tail5 = 0.0
        for sc in scores:
            parts = str(sc["score"]).split("-")
            if len(parts) != 2:
                continue
            try:
                h, a = int(parts[0]), int(parts[1])
            except ValueError:
                continue
            p = float(sc["probability"] or 0)
            if h > a:
                home += p
            elif a > h:
                away += p
            else:
                draw += p
            if h + a >= 4:
                tail4 += p
            if h + a >= 5:
                tail5 += p
        out["full_mass_1x2"] = {"home": round(home, 8), "draw": round(draw, 8), "away": round(away, 8)}
        out["tail_4plus_mass"] = round(tail4, 8)
        out["tail_5plus_mass"] = round(tail5, 8)
    finally:
        conn.close()
    return out


def classify_mission_agreement(p: dict, ecse10: dict, ev: dict) -> dict[str, Any]:
    """User taxonomy — transparent multi-tag classification."""
    wde = p.get("wde") or {}
    ecse = p.get("ecse") or {}
    dna = ev.get("dna") or {}
    tags: list[str] = []

    can_top = [s["score"] for s in (ecse10.get("scores") or [])[:10] if s.get("score")]
    dna_top = list(dna.get("top5") or [])[:5]
    # Prefer DNA as Exact V2 research proxy when Exact V2 tops absent
    exact_v2_top = list(ev.get("exact_v2_top10") or dna_top)

    def overlap(a: list[str], b: list[str], n: int) -> int:
        return len(set(a[:n]) & set(b[:n]))

    top1_agree = bool(can_top and exact_v2_top and can_top[0] == exact_v2_top[0])
    o3 = overlap(can_top, exact_v2_top, 3)
    o5 = overlap(can_top, exact_v2_top, 5)
    o10 = overlap(can_top, exact_v2_top, 10)

    wde_dir = str(wde.get("decision") or "").lower()
    mass = ecse10.get("full_mass_1x2") or {}
    if (mass.get("home") or 0) >= (mass.get("away") or 0) and (mass.get("home") or 0) >= (mass.get("draw") or 0):
        exact_dir = "home"
    elif (mass.get("away") or 0) >= (mass.get("home") or 0) and (mass.get("away") or 0) >= (mass.get("draw") or 0):
        exact_dir = "away"
    else:
        exact_dir = "draw"
    dir_agree = ("home" in wde_dir and exact_dir == "home") or (
        "away" in wde_dir and exact_dir == "away"
    ) or ("draw" in wde_dir and exact_dir == "draw")

    can_l = _f(ecse.get("total_lambda")) or _f(ecse10.get("lambda_total"))
    dna_goals = _f(dna.get("avg_goals"))
    ent = _f(ecse.get("entropy")) or _f(ecse10.get("entropy_top10_normalized"))
    high_unc = bool(ent is not None and ent >= 2.0) or bool(p.get("consensus") == "HIGH_CONFLICT")

    primary = "MODELS_PARTIALLY_AGREE"
    if p.get("no_bet"):
        primary = "RESEARCH_ONLY_NO_BET"
        tags.append("RESEARCH_ONLY_NO_BET")
    if not dir_agree and (wde.get("execution_status") == "OK") and can_top:
        primary = "DIRECTION_CONFLICT"
        tags.append("DIRECTION_CONFLICT")
    elif top1_agree and o5 >= 3 and dir_agree:
        primary = "MODELS_STRONGLY_AGREE"
        tags.append("MODELS_STRONGLY_AGREE")
    elif dir_agree and o3 >= 2:
        primary = "MODELS_AGREE"
        tags.append("MODELS_AGREE")
    else:
        tags.append("MODELS_PARTIALLY_AGREE")

    if can_l is not None and dna_goals is not None and dna_goals - can_l >= 0.75:
        tags.append("EXACT_V2_HIGH_GOAL_SHIFT")
        if primary == "MODELS_PARTIALLY_AGREE":
            primary = "EXACT_V2_HIGH_GOAL_SHIFT"
    if can_l is not None and can_l <= 2.2 and (ecse10.get("tail_4plus_mass") or 0) < 0.15:
        tags.append("CANONICAL_LOW_GOAL_LEAN")
    if high_unc:
        tags.append("HIGH_UNCERTAINTY")
        if primary not in {"DIRECTION_CONFLICT", "MODELS_STRONGLY_AGREE"}:
            primary = "HIGH_UNCERTAINTY"

    return {
        "primary": primary,
        "secondary_tags": sorted(set(tags) - {primary}),
        "top1_agree": top1_agree,
        "top3_overlap": o3,
        "top5_overlap": o5,
        "top10_overlap": o10,
        "wde_direction": wde_dir,
        "exact_full_mass_direction": exact_dir,
        "direction_agreement": dir_agree,
        "lambda_total_canonical": can_l,
        "dna_avg_goals": dna_goals,
        "entropy": ent,
        "portfolio_similarity_ood_used_for_selection": False,
    }


def research_verdict(p: dict, ag: dict, q_score: float) -> str:
    if not p.get("prediction_complete"):
        return "BLOCKED"
    if p.get("no_bet") and ag.get("primary") == "DIRECTION_CONFLICT":
        return "NO_BET"
    if ag.get("primary") == "MODELS_STRONGLY_AGREE" and q_score >= 55 and not p.get("no_bet"):
        return "STRONG_RESEARCH_CANDIDATE"
    if ag.get("primary") in {"MODELS_AGREE", "MODELS_STRONGLY_AGREE"} and q_score >= 40:
        return "RESEARCH_CANDIDATE"
    if ag.get("primary") in {"HIGH_UNCERTAINTY", "DIRECTION_CONFLICT"}:
        return "NO_BET" if p.get("no_bet") else "WATCHLIST"
    if p.get("no_bet"):
        return "NO_BET"
    return "WATCHLIST"


def run_top10_to_5_for_fixture(p: dict, ecse10: dict) -> dict[str, Any]:
    """Research-only Top10-to-5 when real markets exist; never fabricate odds."""
    try:
        from worldcup_predictor.research.top10_to_5_optimizer.exact_consensus import (
            build_consensus_top10,
            lock_exact_three,
        )
        from worldcup_predictor.research.top10_to_5_optimizer.market_pair_search import search_market_pairs
        from worldcup_predictor.research.top10_to_5_optimizer.odds_loader import (
            load_real_odds_json,
            markets_from_odds_doc,
        )
        from worldcup_predictor.research.top10_to_5_optimizer.stake_optimizer import allocate_stakes
    except Exception as exc:  # noqa: BLE001
        return {"status": "TOP10_TO_5_UNAVAILABLE", "error": str(exc)[:200], "research_only": True}

    scores = ecse10.get("scores") or []
    payload = {
        "canonical": {"scores": [{"score": s["score"], "probability": s.get("probability") or 0, "rank": s.get("rank")} for s in scores]},
    }
    top10 = build_consensus_top10(payload, top10_source="canonical", top_n=10)
    exact = lock_exact_three(top10)
    exact_scores = [e["scoreline"] for e in exact]
    stake = allocate_stakes(mode="profit_floor", budget=25.0)

    odds_paths = [
        ROOT / "data" / "research" / "interwetten_three_fixture_markets.json",
        ROOT
        / "worldcup_predictor"
        / "research"
        / "bet_coverage_optimizer"
        / "fixtures"
        / "interwetten_three_fixture_markets.json",
    ]
    odds_doc = None
    for op in odds_paths:
        if op.exists():
            by = load_real_odds_json(op)
            odds_doc = by.get(int(p["fixture_id"]))
            if odds_doc:
                break
    if not odds_doc:
        return {
            "status": "TOP10_TO_5_MARKET_INSUFFICIENT",
            "exact_scores": exact_scores,
            "raw_covered_mass": None,
            "profitable_mass": None,
            "full_loss_mass": None,
            "research_only": True,
            "note": "no real multi-market book for fixture; exact trio locked from Top10 only",
        }
    markets, val = markets_from_odds_doc(odds_doc, top10_scores=[t["scoreline"] for t in top10])
    if len(markets) < 2:
        return {
            "status": "TOP10_TO_5_MARKET_INSUFFICIENT",
            "exact_scores": exact_scores,
            "market_validation": val,
            "research_only": True,
        }
    search = search_market_pairs(
        markets,
        top10=top10,
        exact_scores=exact_scores,
        stake_plan=stake,
        exact_odds={s: None for s in exact_scores},
    )
    sel = search.get("selected") or {}
    scen = sel.get("scenarios") or {}
    return {
        "status": "TOP10_TO_5_UNPRICED" if scen.get("unknown_mass", 0) > 0 else "TOP10_TO_5_PARTIAL",
        "exact_scores": exact_scores,
        "market_1": (sel.get("market_1") or {}).get("label"),
        "market_2": (sel.get("market_2") or {}).get("label"),
        "raw_covered_mass": scen.get("raw_outcome_coverage_mass") or sel.get("covered_top10_probability_mass"),
        "profitable_mass": scen.get("profitable_outcome_coverage_mass"),
        "partial_recovery_mass": scen.get("partial_recovery_mass"),
        "full_loss_mass": scen.get("full_loss_mass"),
        "uncovered": sel.get("uncovered_top10_scorelines"),
        "stake_plan": stake,
        "research_only": True,
        "monetary_roi_available": False,
    }


def side_by_side_top10(ecse10: dict, exact_v2: list[dict[str, Any]], other: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for i in range(1, 11):
        c = next((s for s in (ecse10.get("scores") or []) if int(s.get("rank") or 0) == i), None)
        if c is None and i - 1 < len(ecse10.get("scores") or []):
            c = (ecse10.get("scores") or [])[i - 1]
        e = exact_v2[i - 1] if i - 1 < len(exact_v2) else None
        o = other[i - 1] if i - 1 < len(other) else None
        rows.append(
            {
                "rank": i,
                "canonical_ecse": None if not c else c.get("score"),
                "canonical_p": None if not c else c.get("probability"),
                "exact_v2": None if not e else e.get("score"),
                "exact_v2_p": None if not e else e.get("probability"),
                "other_challenger": None if not o else o.get("score"),
                "other_p": None if not o else o.get("probability"),
            }
        )
    return rows


def freeze_integrity(p: dict) -> dict[str, Any]:
    fr = p.get("freeze") or {}
    ko = p.get("kickoff_utc")
    gen = p.get("generated_at")
    odds_ts = (p.get("odds") or {}).get("timestamp") or (p.get("odds") or {}).get("odds_timestamp")
    freeze_ts = fr.get("freeze_timestamp") or fr.get("created_at")

    def before(a: Any, b: Any) -> bool | None:
        if not a or not b:
            return None
        try:
            da = datetime.fromisoformat(str(a).replace("Z", "+00:00"))
            db = datetime.fromisoformat(str(b).replace("Z", "+00:00"))
            if da.tzinfo is None:
                da = da.replace(tzinfo=timezone.utc)
            if db.tzinfo is None:
                db = db.replace(tzinfo=timezone.utc)
            return da < db
        except Exception:
            return None

    return {
        "fixture_id": p.get("fixture_id"),
        "freeze_id": fr.get("freeze_id"),
        "content_hash": fr.get("content_hash") or fr.get("freeze_hash"),
        "capture_status": fr.get("capture_status") or fr.get("new_or_reused"),
        "prediction_before_kickoff": before(gen, ko),
        "odds_before_kickoff": before(odds_ts, ko),
        "freeze_before_kickoff": before(freeze_ts, ko) if freeze_ts else p.get("freeze_before_kickoff"),
        "cohort_type": "true_forward",
        "historical_backfill": False,
        "shadow_cannot_fail_canonical": True,
        "portfolio_similarity_ood_not_used": True,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=PHASE)
    ap.add_argument("--dates", nargs="+", default=DEFAULT_DATES)
    ap.add_argument("--force-owner", action="store_true")
    ap.add_argument("--skip-owner", action="store_true", help="Aggregate existing artifacts only")
    ap.add_argument("--output-dir", type=str, default="")
    ap.add_argument("--allow-low-disk", action="store_true", help="Permit aggregation when free disk < 8GB (no heavy owner)")
    ap.add_argument("--light-evidence", action="store_true", help="Skip DNA/Twins corpus build (low disk / fast)")
    ap.add_argument(
        "--enrich-only",
        action="store_true",
        help="Resume existing mission: shadow enrichment only (no Canonical/freeze regeneration)",
    )
    ap.add_argument(
        "--mission-dir",
        type=str,
        default="",
        help="Existing mission artifact dir for --enrich-only",
    )
    args = ap.parse_args(argv)

    if args.enrich_only:
        from pathlib import Path as _P

        enrich_path = ROOT / "scripts" / "enrich_next_4_days_existing_mission.py"
        spec = importlib.util.spec_from_file_location("enrich_next_4", enrich_path)
        enrich_mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(enrich_mod)
        argv2 = ["--dates", *list(args.dates)]
        if args.mission_dir:
            argv2 = ["--mission-dir", args.mission_dir, *argv2]
        elif args.output_dir:
            argv2 = ["--mission-dir", args.output_dir, *argv2]
        return int(enrich_mod.main(argv2))

    dates = list(args.dates)
    if len(dates) != 4:
        _safe_print(f"WARNING: expected 4 dates, got {len(dates)}: {dates}")

    disk_before = disk_gb(ROOT)
    _safe_print(f"Disk before: {disk_before}")
    free = float(disk_before.get("free_gb") or 99)
    if free < 8.0 and not (args.skip_owner and args.allow_low_disk):
        _safe_print("STOP: free disk < 8 GB — refusing heavy batches")
        return 2
    if free < 10.0:
        _safe_print("ALERT: free disk < 10 GB — proceeding with caution, no large backups")
        if not args.light_evidence:
            args.light_evidence = True
            _safe_print("Auto-enabling --light-evidence due to low disk")

    five = _load_five_day()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rng = f"{dates[0]}_{dates[-1]}"
    out = Path(args.output_dir) if args.output_dir else ROOT / "artifacts" / "next_4_days_complete_predictions" / rng / ts
    out.mkdir(parents=True, exist_ok=True)

    commit = "unknown"
    try:
        import subprocess

        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True).strip()
    except Exception:
        pass

    owner_runs = []
    if not args.skip_owner:
        for d in dates:
            owner_runs.append(five.ensure_owner_day(d, force=bool(args.force_owner)))
    else:
        owner_runs = [{"date": d, "ran": False, "ok": True, "skipped": True} for d in dates]

    engines = {"v2": None, "dna_catalog": [], "corpus": None, "errors": ["light_evidence"]}
    if not args.light_evidence:
        engines = five.build_evidence_engines()
    else:
        _safe_print("Light evidence mode: DNA/Twins corpus skipped")
    now_utc = datetime.now(timezone.utc)

    discovered_rows = []
    eligibility_rows = []
    odds_rows = []
    canonical_rows = []
    shadow_rows = []
    exact_tables = {}
    agreement_rows = []
    forensic_rows = []
    t10to5_rows = []
    blocked_rows = []
    freeze_rows = []
    all_complete = []

    shadow_success = {"dna_v2": 0, "twins": 0, "hcee": 0, "exact_v2_proxy": 0, "l2f": 0, "tsbp": 0}
    canonical_ok = 0

    for d in dates:
        day = five.load_day(d)
        disc = day.get("discovery") or {}
        preds = list((day.get("predictions") or {}).get("predictions") or [])
        freezes = list((day.get("freezes") or {}).get("freezes") or [])
        odds = list((day.get("odds") or {}).get("fixtures") or [])

        for r in list(disc.get("all_discovered") or []):
            discovered_rows.append(
                {
                    "date": d,
                    "vienna_ko": r.get("kickoff_vienna"),
                    "fixture_id": r.get("fixture_id"),
                    "country": r.get("league_country") or r.get("country"),
                    "league": r.get("league") or r.get("competition"),
                    "home": r.get("home_team"),
                    "away": r.get("away_team"),
                    "eligibility": "discovered",
                    "reason": "",
                }
            )
        for e in list(disc.get("exclusions") or []):
            reason = e.get("exclusion_reason") or e.get("reason") or "excluded"
            blocked_rows.append(
                {
                    "date": d,
                    "fixture_id": e.get("fixture_id"),
                    "match": f"{e.get('home_team')} vs {e.get('away_team')}",
                    "reason": reason,
                    "stage": "discovery",
                }
            )
            eligibility_rows.append(
                {
                    "date": d,
                    "vienna_ko": e.get("kickoff_vienna"),
                    "fixture_id": e.get("fixture_id"),
                    "country": e.get("league_country"),
                    "league": e.get("league") or e.get("competition"),
                    "home": e.get("home_team"),
                    "away": e.get("away_team"),
                    "eligibility": "excluded",
                    "reason": reason,
                }
            )

        for o in odds:
            odds_rows.append({**o, "date": d})
        for f in freezes:
            freeze_rows.append({**f, "date": d})

        for p in preds:
            p = dict(p)
            p["date"] = d
            fid = int(p.get("fixture_id") or 0)
            eligibility_rows.append(
                {
                    "date": d,
                    "vienna_ko": p.get("kickoff_vienna"),
                    "fixture_id": fid,
                    "country": p.get("league_country"),
                    "league": p.get("league") or p.get("competition"),
                    "home": p.get("home_team"),
                    "away": p.get("away_team"),
                    "eligibility": "eligible" if p.get("prediction_complete") else "predicted_partial",
                    "reason": "" if p.get("prediction_complete") else (p.get("block_reason") or "incomplete"),
                }
            )

            if not p.get("prediction_complete"):
                blocked_rows.append(
                    {
                        "date": d,
                        "fixture_id": fid,
                        "match": f"{p.get('home_team')} vs {p.get('away_team')}",
                        "reason": p.get("block_reason") or "prediction_incomplete",
                        "stage": "prediction",
                    }
                )

            _safe_print(f"enrich {d} {fid}...")
            ev = five.enrich_evidence(p, engines)
            # Exact V2 proxy from DNA top5 (research-only; not promoted)
            exact_v2_list = [{"score": s, "probability": None} for s in (ev.get("dna") or {}).get("top5") or []]
            twin_list = [{"score": s, "probability": None} for s in (ev.get("twins") or {}).get("top5") or []]
            if exact_v2_list:
                shadow_success["exact_v2_proxy"] += 1
                shadow_success["dna_v2"] += 1
            if (ev.get("twins") or {}).get("status") == "OK":
                shadow_success["twins"] += 1
            if (ev.get("hcee") or {}).get("status") == "OK":
                shadow_success["hcee"] += 1

            ecse10 = load_ecse_top10(fid)
            # Fill from prediction ECSE top1-5 if snapshot missing ranks
            if not ecse10.get("available"):
                scores = []
                for i in range(1, 6):
                    t = (p.get("ecse") or {}).get(f"top{i}") or {}
                    if t.get("score"):
                        scores.append({"rank": i, "score": t.get("score"), "probability": t.get("probability")})
                ecse10["scores"] = scores
                ecse10["available"] = bool(scores)
                ecse10["note"] = "fallback_from_prediction_top5_only"

            five_ag = five.agreement(p, ev)
            q = five.quality(p, five_ag, ev)
            mission_ag = classify_mission_agreement(p, ecse10, ev)
            verdict = research_verdict(p, mission_ag, float(q.get("score") or 0))
            t5 = run_top10_to_5_for_fixture(p, ecse10)
            fi_row = freeze_integrity(p)

            if (p.get("wde") or {}).get("execution_status") == "OK" and (p.get("ecse") or {}).get("execution_status") == "OK":
                canonical_ok += 1

            sbs = side_by_side_top10(ecse10, exact_v2_list, twin_list)
            exact_tables[str(fid)] = {
                "fixture_id": fid,
                "match": f"{p.get('home_team')} vs {p.get('away_team')}",
                "date": d,
                "ranking_method_canonical": ecse10.get("ranking_method"),
                "probability_field_canonical": ecse10.get("probability_field"),
                "canonical_top3_mass": ecse10.get("top3_mass") or (p.get("ecse") or {}).get("top3_mass"),
                "canonical_top5_mass": ecse10.get("top5_mass") or (p.get("ecse") or {}).get("top5_mass"),
                "canonical_top10_mass": ecse10.get("top10_mass"),
                "canonical_entropy": (p.get("ecse") or {}).get("entropy"),
                "full_mass_1x2": ecse10.get("full_mass_1x2"),
                "tail_4plus": ecse10.get("tail_4plus_mass"),
                "tail_5plus": ecse10.get("tail_5plus_mass"),
                "exact_v2_source": "dna_v2_top5_research_proxy_not_promoted",
                "other_challenger_source": "historical_twins_top5_research",
                "table": sbs,
            }

            wde = p.get("wde") or {}
            odds = p.get("odds") or {}
            canonical_rows.append(
                {
                    "fixture_id": fid,
                    "date": d,
                    "match": f"{p.get('home_team')} vs {p.get('away_team')}",
                    "wde_h": wde.get("home_probability"),
                    "wde_d": wde.get("draw_probability"),
                    "wde_a": wde.get("away_probability"),
                    "argmax": wde.get("ft_marginal") or wde.get("raw_argmax"),
                    "decision": wde.get("decision"),
                    "override": wde.get("decision_source"),
                    "override_reason": wde.get("decision_override_reason") or wde.get("decision_source"),
                    "confidence": wde.get("confidence"),
                    "quality": wde.get("quality_status"),
                    "consensus": p.get("consensus"),
                    "conflict_count": mission_ag.get("top5_overlap") is not None and five_ag.get("conflicts"),
                    "no_bet": p.get("no_bet"),
                    "btts": (p.get("btts") or {}).get("prediction"),
                    "ou25": (p.get("ou25") or {}).get("preferred_side") or (p.get("ou25") or {}).get("prediction"),
                    "can_lh": (p.get("ecse") or {}).get("lambda_home") or ecse10.get("lambda_home"),
                    "can_la": (p.get("ecse") or {}).get("lambda_away") or ecse10.get("lambda_away"),
                    "can_lt": (p.get("ecse") or {}).get("total_lambda") or ecse10.get("lambda_total"),
                    "kickoff_utc": p.get("kickoff_utc"),
                    "kickoff_vienna": p.get("kickoff_vienna"),
                    "prediction_ts": p.get("generated_at"),
                    "odds_ts": odds.get("timestamp"),
                    "freeze_id": (p.get("freeze") or {}).get("freeze_id"),
                    "job_id": p.get("job_id"),
                    "research_verdict": verdict,
                    "agreement_primary": mission_ag.get("primary"),
                }
            )
            shadow_rows.append(
                {
                    "fixture_id": fid,
                    "dna_v2": ev.get("dna"),
                    "twins": {k: (ev.get("twins") or {}).get(k) for k in ("status", "n", "top5", "avg_goals", "entropy")},
                    "hcee": {k: (ev.get("hcee") or {}).get(k) for k in ("status", "total_risk", "high_score_tail_risk")},
                    "exact_v2_promoted": False,
                    "portfolio_used": False,
                    "similarity_used": False,
                    "ood_used": False,
                }
            )
            agreement_rows.append({"fixture_id": fid, "date": d, "match": f"{p.get('home_team')} vs {p.get('away_team')}", **mission_ag})
            forensic_rows.append(
                {
                    "fixture_id": fid,
                    "hcee": ev.get("hcee"),
                    "esli": ev.get("esli"),
                    "agents_rewrite_probabilities": False,
                }
            )
            t10to5_rows.append({"fixture_id": fid, "date": d, "match": f"{p.get('home_team')} vs {p.get('away_team')}", **t5})
            freeze_rows.append({**fi_row, "date": d})

            rec = {
                **p,
                "_ecse10": ecse10,
                "_ev": ev,
                "_mission_ag": mission_ag,
                "_quality": q,
                "_verdict": verdict,
                "_t10to5": t5,
                "_freeze_integrity": fi_row,
                "_sbs": sbs,
            }
            if p.get("prediction_complete"):
                all_complete.append(rec)

    # Rankings (prematch evidence only — no Portfolio/Similarity/OOD)
    def end_result_score(r: dict) -> float:
        wde = r.get("wde") or {}
        ag = r.get("_mission_ag") or {}
        edge = max(
            _f(wde.get("home_probability")) or 0,
            _f(wde.get("draw_probability")) or 0,
            _f(wde.get("away_probability")) or 0,
        )
        if edge > 1.5:
            edge = edge / 100.0
        conf = _f(wde.get("confidence"))
        if conf is not None and conf > 1.5:
            conf = conf / 100.0
        conf = conf or 0.0
        s = 40 * edge + 25 * conf + 20 * (1 if ag.get("direction_agreement") else 0)
        s += 15 * (1 if ag.get("primary") in {"MODELS_STRONGLY_AGREE", "MODELS_AGREE"} else 0)
        if r.get("no_bet"):
            s -= 40
        if ag.get("primary") == "DIRECTION_CONFLICT":
            s -= 30
        if (r.get("_verdict") or "") in {"NO_BET", "BLOCKED"}:
            s -= 20
        fresh = str((r.get("odds") or {}).get("freshness_status") or r.get("odds_freshness") or "")
        if fresh and "FRESH" not in fresh.upper():
            s -= 15
        return s

    def exact_score_rank_key(r: dict) -> float:
        ec = r.get("ecse") or {}
        ag = r.get("_mission_ag") or {}
        m5 = _f(ec.get("top5_mass")) or _f((r.get("_ecse10") or {}).get("top5_mass")) or 0
        ent = _f(ec.get("entropy")) or 2.5
        s = 50 * m5 + 20 * (1 if ag.get("top1_agree") else 0) + 15 * ((ag.get("top5_overlap") or 0) / 5)
        s += 15 * max(0.0, (2.3 - ent) / 1.0)
        if ag.get("primary") == "DIRECTION_CONFLICT":
            s -= 25
        return s

    def coverage_key(r: dict) -> float:
        t = r.get("_t10to5") or {}
        raw = _f(t.get("raw_covered_mass")) or 0
        full = _f(t.get("full_loss_mass")) or 0.5
        return 70 * raw - 30 * full + (10 if t.get("market_1") else 0)

    def risk_key(r: dict) -> float:
        ag = r.get("_mission_ag") or {}
        risk = 0.0
        if ag.get("primary") == "DIRECTION_CONFLICT":
            risk += 40
        if ag.get("primary") == "HIGH_UNCERTAINTY":
            risk += 30
        if r.get("no_bet"):
            risk += 10
        risk += 5 * (5 - (ag.get("top5_overlap") or 0))
        return risk

    ranked_end = sorted(all_complete, key=end_result_score, reverse=True)
    ranked_exact = sorted(all_complete, key=exact_score_rank_key, reverse=True)
    ranked_agree = sorted(
        all_complete,
        key=lambda r: (
            0 if (r.get("_mission_ag") or {}).get("primary") == "MODELS_STRONGLY_AGREE" else 1,
            0 if (r.get("_mission_ag") or {}).get("primary") == "MODELS_AGREE" else 1,
            -((r.get("_mission_ag") or {}).get("top5_overlap") or 0),
            -exact_score_rank_key(r),
        ),
    )
    ranked_cov = sorted(all_complete, key=coverage_key, reverse=True)
    ranked_avoid = sorted(all_complete, key=risk_key, reverse=True)

    def slim(r: dict, score: float | None = None) -> dict[str, Any]:
        return {
            "fixture_id": r.get("fixture_id"),
            "date": r.get("date"),
            "kickoff_vienna": r.get("kickoff_vienna"),
            "league": r.get("league") or r.get("competition"),
            "country": r.get("league_country"),
            "match": f"{r.get('home_team')} vs {r.get('away_team')}",
            "no_bet": r.get("no_bet"),
            "wde_decision": (r.get("wde") or {}).get("decision"),
            "agreement": (r.get("_mission_ag") or {}).get("primary"),
            "verdict": r.get("_verdict"),
            "odds": r.get("odds"),
            "freeze_id": (r.get("freeze") or {}).get("freeze_id"),
            "job_id": r.get("job_id"),
            "score": score,
            "canonical_top10": (r.get("_ecse10") or {}).get("scores"),
            "side_by_side": r.get("_sbs"),
            "main_risk": r.get("main_risk") or (r.get("_mission_ag") or {}).get("primary"),
        }

    top10_end = [slim(r, end_result_score(r)) for r in ranked_end[:10]]
    top10_exact = [slim(r, exact_score_rank_key(r)) for r in ranked_exact[:10]]
    top10_agree = [slim(r) for r in ranked_agree[:10]]
    top10_cov = [slim(r, coverage_key(r)) for r in ranked_cov[:10]]
    top10_avoid = [slim(r, risk_key(r)) for r in ranked_avoid[:10]]

    def pick_best3(ranked_full: list[dict], score_fn=None, *, allow_no_bet: bool = False) -> list[dict]:
        """Never promote NO_BET merely to fill Best Picks — may return fewer than 3."""
        out = []
        for r in ranked_full:
            sm = slim(r, score_fn(r) if score_fn else None)
            if not allow_no_bet and (sm.get("no_bet") or sm.get("verdict") in {"NO_BET", "BLOCKED"}):
                continue
            out.append(sm)
            if len(out) >= 3:
                break
        return out

    best3_end = pick_best3(ranked_end, end_result_score, allow_no_bet=False)
    best3_exact = pick_best3(ranked_exact, exact_score_rank_key, allow_no_bet=False)
    best3_agree = pick_best3(ranked_agree, allow_no_bet=False)

    shortlist = {
        "best_3_end_result": best3_end,
        "best_3_exact_score": best3_exact,
        "best_3_model_consensus": best3_agree,
        "selection_layers_excluded": [
            "portfolio_manager_baseline",
            "calibrated_portfolio_candidate",
            "similarity_overlay",
            "original_aggressive_ood_filter",
        ],
        "no_promotion": True,
        "no_routing_activation": True,
        "research_only_shadows": True,
    }

    n_eligible = len(all_complete)
    n_disc = len({(r.get("date"), r.get("fixture_id")) for r in discovered_rows + eligibility_rows})
    blocked_n = len(blocked_rows)
    missing_days = [d for d in dates if not (five.load_day(d).get("predictions") or {}).get("predictions")]

    if n_eligible == 0:
        status = STATUS_NONE
    elif missing_days:
        status = STATUS_PARTIAL
    elif args.light_evidence or shadow_success.get("exact_v2_proxy", 0) == 0:
        # Canonical complete, but Exact V2 / DNA shadow enrichment unavailable this run
        status = STATUS_PARTIAL
    elif any(not r.get("ok") for r in owner_runs if r.get("ran")):
        status = STATUS_PARTIAL
    else:
        status = STATUS_READY if n_eligible > 0 else STATUS_NONE
    if n_eligible == 0:
        status = STATUS_NONE

    disk_after = disk_gb(ROOT)
    validation = {
        "status": status,
        "phase": PHASE,
        "dates": dates,
        "commit": commit,
        "disk_before": disk_before,
        "disk_after": disk_after,
        "discovered_fixture_count": n_disc,
        "eligible_predicted_frozen_count": n_eligible,
        "blocked_count": blocked_n,
        "canonical_success_count": canonical_ok,
        "shadow_success_by_model": shadow_success,
        "owner_runs": owner_runs,
        "missing_days": missing_days,
        "no_promotion": True,
        "no_routing_activation": True,
        "canonical_unchanged": True,
        "exact_v2_shadow_only": True,
        "portfolio_similarity_ood_not_used_for_final_ranking": True,
        "cohort_type": "true_forward",
        "artifact_dir": str(out),
    }

    # Write artifacts
    _json_dump(out / "run_manifest.json", validation)
    _json_dump(out / "discovered_universe.json", {"rows": discovered_rows, "count": len(discovered_rows)})
    _json_dump(out / "eligibility_report.json", {"rows": eligibility_rows})
    _json_dump(out / "fresh_odds_report.json", {"rows": odds_rows})
    _json_dump(out / "canonical_predictions.json", {"rows": canonical_rows, "count": len(canonical_rows)})
    _json_dump(out / "shadow_predictions.json", {"rows": shadow_rows, "exact_v2_promoted": False})
    _json_dump(out / "exact_top10_all_models.json", exact_tables)
    _json_dump(out / "model_agreement.json", {"rows": agreement_rows})
    _json_dump(out / "forensic_agent_report.json", {"rows": forensic_rows, "agents_may_not_rewrite_probabilities": True})
    _json_dump(out / "top10_to_5_recommendations.json", {"rows": t10to5_rows, "research_only": True})
    _json_dump(out / "blocked_fixtures.json", {"rows": blocked_rows, "count": blocked_n})
    _json_dump(
        out / "final_rankings.json",
        {
            "end_result_top10": top10_end,
            "exact_score_top10": top10_exact,
            "model_agreement_top10": top10_agree,
            "coverage_top10": top10_cov,
            "avoid_top10": top10_avoid,
        },
    )
    _json_dump(out / "final_owner_shortlist.json", shortlist)
    _json_dump(out / "freeze_integrity_report.json", {"rows": freeze_rows, "cohort_type": "true_forward"})
    _json_dump(out / "validation_report.json", validation)

    # Markdown + HTML report
    md = _build_md(validation, shortlist, top10_end, top10_exact, top10_agree, top10_cov, top10_avoid, exact_tables, agreement_rows, t10to5_rows, blocked_rows, canonical_rows)
    (out / "NEXT_4_DAYS_COMPLETE_PREDICTION_REPORT.md").write_text(md, encoding="utf-8")
    (ROOT / "NEXT_4_DAYS_COMPLETE_PREDICTION_REPORT.md").write_text(md, encoding="utf-8")
    html = f"""<!DOCTYPE html><html><head><meta charset='utf-8'/><title>Next 4 Days</title>
<style>body{{font-family:Georgia,serif;background:#101820;color:#e8eef4;margin:2rem}}
h1{{color:#7dd3c0}} code{{color:#f0c674}} .card{{background:#1b2630;padding:1rem;margin:1rem 0;border-left:4px solid #7dd3c0}}
table{{border-collapse:collapse;width:100%;font-size:12px}} td,th{{border:1px solid #333;padding:4px}}</style></head>
<body><h1>Next 4 Days Complete Multi-Model</h1>
<div class='card'><strong>Status:</strong> <code>{status}</code><br/>
<strong>Dates:</strong> <code>{dates[0]} .. {dates[-1]}</code><br/>
<strong>Eligible:</strong> <code>{n_eligible}</code><br/>
<strong>Blocked:</strong> <code>{blocked_n}</code><br/>
<strong>Commit:</strong> <code>{commit[:12]}</code><br/>
<strong>Promotion:</strong> NONE — NOT ACTIVATED</div>
<pre>{json.dumps(shortlist, indent=2, default=str)[:8000]}</pre>
</body></html>"""
    (out / "owner_report.html").write_text(html, encoding="utf-8")

    _safe_print(json.dumps({"status": status, "eligible": n_eligible, "blocked": blocked_n, "artifact_dir": str(out)}, indent=2))
    return 0 if status != STATUS_NONE else 1


def _build_md(validation, shortlist, end, exact, agree, cov, avoid, exact_tables, agreement_rows, t10to5, blocked, canonical):
    lines = [
        "# NEXT_4_DAYS_COMPLETE_PREDICTION_REPORT",
        "",
        f"**Status:** `{validation.get('status')}`  ",
        f"**Dates:** `{validation.get('dates')}`  ",
        f"**Commit:** `{validation.get('commit')}`  ",
        "**No promotion and no routing activation occurred.**",
        "",
        "## Counters",
        "",
        f"- Discovered: `{validation.get('discovered_fixture_count')}`",
        f"- Eligible predicted/frozen: `{validation.get('eligible_predicted_frozen_count')}`",
        f"- Blocked: `{validation.get('blocked_count')}`",
        f"- Canonical success: `{validation.get('canonical_success_count')}`",
        f"- Shadow success: `{validation.get('shadow_success_by_model')}`",
        f"- Disk before/after: `{validation.get('disk_before')}` → `{validation.get('disk_after')}`",
        "",
        "## Final shortlist",
        "",
        "### Best 3 End Result",
    ]
    for r in shortlist.get("best_3_end_result") or []:
        lines.append(f"- `{r.get('date')}` `{r.get('match')}` id=`{r.get('fixture_id')}` verdict=`{r.get('verdict')}` decision=`{r.get('wde_decision')}`")
    lines += ["", "### Best 3 Exact Score"]
    for r in shortlist.get("best_3_exact_score") or []:
        lines.append(f"- `{r.get('date')}` `{r.get('match')}` id=`{r.get('fixture_id')}` verdict=`{r.get('verdict')}`")
    lines += ["", "### Best 3 Model Consensus"]
    for r in shortlist.get("best_3_model_consensus") or []:
        lines.append(f"- `{r.get('date')}` `{r.get('match')}` id=`{r.get('fixture_id')}` agree=`{r.get('agreement')}`")
    lines += ["", "## Top 10 End Result"]
    for i, r in enumerate(end, 1):
        lines.append(f"{i}. `{r.get('match')}` ({r.get('date')}) score=`{r.get('score')}`")
    lines += ["", "## Top 10 Exact Score"]
    for i, r in enumerate(exact, 1):
        lines.append(f"{i}. `{r.get('match')}` ({r.get('date')}) score=`{r.get('score')}`")
    lines += ["", "## Top 10 Avoid"]
    for i, r in enumerate(avoid, 1):
        lines.append(f"{i}. `{r.get('match')}` risk=`{r.get('score')}` agree=`{r.get('agreement')}`")
    lines += ["", "## Exact Top1–Top10 (per fixture)", ""]
    for fid, tab in list(exact_tables.items())[:80]:
        lines.append(f"### Fixture {fid} — {tab.get('match')} ({tab.get('date')})")
        lines.append("")
        lines.append("| Rank | Canonical ECSE | p | Exact V2 proxy | p | Twins | p |")
        lines.append("|---:|---|---:|---|---:|---|---:|")
        for row in tab.get("table") or []:
            lines.append(
                f"| {row['rank']} | {row.get('canonical_ecse')} | {row.get('canonical_p')} | "
                f"{row.get('exact_v2')} | {row.get('exact_v2_p')} | {row.get('other_challenger')} | {row.get('other_p')} |"
            )
        lines.append("")
    lines += [
        "",
        "## Notes",
        "",
        "- Exact V2 column uses DNA V2 Top5 research proxy when Exact V2 shadow tops are unavailable; **not promoted**.",
        "- Portfolio / Similarity / OOD were **not** used for final ranking.",
        "- Top10-to-5 monetary ROI marked unavailable without exact-score odds (no fabrication).",
        "",
        "**NOT DEPLOYED / NO ROUTING ACTIVATION**",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
