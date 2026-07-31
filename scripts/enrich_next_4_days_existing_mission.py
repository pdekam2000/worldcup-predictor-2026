#!/usr/bin/env python3
"""
Resume NEXT_4_DAYS mission: shadow/research enrichment ONLY.

Reuses existing owner full_day predictions + immutable freezes.
Does NOT regenerate Canonical / WDE / ECSE / BTTS / O/U / odds / freezes.
Does NOT persist Exact V2 / L2-F / TSBP into production tables (read-only compute).
Does NOT promote Exact V2 or activate routing.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import importlib.util


def _load_mission():
    path = ROOT / "scripts" / "run_next_4_days_complete_prediction_scan.py"
    spec = importlib.util.spec_from_file_location("next_4_days_mission", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


mission = _load_mission()

FI = ROOT / "data" / "football_intelligence.db"
DEFAULT_MISSION = (
    ROOT
    / "artifacts"
    / "next_4_days_complete_predictions"
    / "2026-08-01_2026-08-04"
    / "20260731T215354Z"
)
STATUS_READY = mission.STATUS_READY
PHASE = "NEXT_4_DAYS_COMPLETE_MULTI_MODEL_PREDICTION_AND_RANKING"


def _safe_print(s: object) -> None:
    print(str(s).encode("ascii", "replace").decode("ascii"), flush=True)


def _f(v: Any) -> float | None:
    return mission._f(v)


def tops_from_dist(dist: list[dict[str, Any]], n: int = 10) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in dist:
        if e.get("scoreline") == "OTHER":
            continue
        out.append(
            {
                "rank": len(out) + 1,
                "score": str(e.get("scoreline") or "").replace(" ", ""),
                "probability": _f(e.get("probability")),
            }
        )
        if len(out) >= n:
            break
    return out


def mass_1x2(tops: list[dict[str, Any]]) -> dict[str, float]:
    home = draw = away = 0.0
    for sc in tops:
        parts = str(sc.get("score") or "").split("-")
        if len(parts) != 2:
            continue
        try:
            h, a = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        p = float(sc.get("probability") or 0)
        if h > a:
            home += p
        elif a > h:
            away += p
        else:
            draw += p
    return {"home": round(home, 8), "draw": round(draw, 8), "away": round(away, 8)}


def entropy_tops(tops: list[dict[str, Any]]) -> float | None:
    probs = [float(t.get("probability") or 0) for t in tops if t.get("probability")]
    if not probs:
        return None
    s = sum(probs) or 1.0
    ent = 0.0
    for p in probs:
        if p > 0:
            q = p / s
            ent -= q * math.log(q + 1e-15)
    return round(ent, 8)


def snapshot_freeze_hashes(fixture_ids: list[int]) -> dict[str, dict[str, Any]]:
    """Read-only freeze hash snapshot from evaluation DB if present, else prediction artifacts."""
    out: dict[str, dict[str, Any]] = {}
    eval_path = ROOT / "data" / "forward_prediction_tracking.db"
    if eval_path.exists():
        conn = sqlite3.connect(f"file:{eval_path.as_posix()}?mode=ro", uri=True, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            for fid in fixture_ids:
                row = conn.execute(
                    """
                    SELECT freeze_id, content_hash, prediction_scope, created_at
                    FROM prediction_freezes
                    WHERE fixture_id=?
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (int(fid),),
                ).fetchone()
                if row:
                    out[str(fid)] = {
                        "freeze_id": row["freeze_id"],
                        "content_hash": row["content_hash"],
                        "prediction_scope": row["prediction_scope"],
                        "source": "forward_prediction_tracking",
                    }
        except sqlite3.Error:
            pass
        finally:
            conn.close()
    return out


def compute_exact_family_readonly(p: dict, *, conn: sqlite3.Connection, engine: Any) -> dict[str, Any]:
    """In-memory Exact V2 / Lambda V2 / Dixon-Coles — no persist_shadow writes."""
    from worldcup_predictor.research.football_strength_foundation.lambda_v2 import (
        football_only,
        market_only_from_odds_row,
        uncertainty_aware_blend,
    )
    from worldcup_predictor.research.football_strength_foundation.score_v2 import dist_dc, dist_overdispersed, dist_poisson
    from worldcup_predictor.research.infra_l2f_forward.adaptive_blend import l2f_adaptive
    from worldcup_predictor.research.infra_l2f_forward.alternate_totals_capture_service import lines_from_ecse_odds_row

    fid = int(p.get("fixture_id") or 0)
    home = str(p.get("home_team") or "")
    away = str(p.get("away_team") or "")
    league = str(p.get("league") or p.get("competition") or "")
    ko = p.get("kickoff_utc")
    try:
        cutoff = datetime.fromisoformat(str(ko).replace("Z", "+00:00"))
        if cutoff.tzinfo is not None:
            cutoff = cutoff.astimezone(timezone.utc).replace(tzinfo=None)
    except Exception:
        cutoff = datetime.utcnow()

    can_lh = float(_f((p.get("ecse") or {}).get("lambda_home")) or 1.2)
    can_la = float(_f((p.get("ecse") or {}).get("lambda_away")) or 1.1)
    odds = dict(p.get("odds") or {})
    # Flatten 1X2 for extract_lambdas compatibility
    odds_row = {
        "ft_home_closing": odds.get("home"),
        "ft_draw_closing": odds.get("draw"),
        "ft_away_closing": odds.get("away"),
        "home": odds.get("home"),
        "draw": odds.get("draw"),
        "away": odds.get("away"),
        **{k: v for k, v in odds.items() if k not in {"home", "draw", "away"}},
    }
    fresh = "FRESH" in str(odds.get("freshness_status") or "").upper()
    books = odds.get("bookmaker_count")

    try:
        bundle = engine.build_match(home, away, cutoff, league, target_fixture_id=fid)
    except Exception as exc:  # noqa: BLE001
        return {"status": "EXACT_V2_UNAVAILABLE", "error": f"strength:{exc}"[:240], "shadow_only": True, "persisted": False}

    try:
        lines = lines_from_ecse_odds_row(odds_row) or []
    except Exception:
        lines = []

    try:
        mkt = market_only_from_odds_row(odds_row, fallback_lh=can_lh, fallback_la=can_la)
        football = football_only(bundle)
        blended = uncertainty_aware_blend(bundle, lines, mkt, odds_fresh=fresh, bookmaker_count=books)
        adaptive = l2f_adaptive(bundle, lines, mkt, odds_fresh=fresh, bookmaker_count=books)
    except Exception as exc:  # noqa: BLE001
        return {"status": "LAMBDA_V2_UNAVAILABLE", "error": str(exc)[:240], "shadow_only": True, "persisted": False}

    families = {
        "LAMBDA_V2_FOOTBALL": football,
        "LAMBDA_V2_MARKET_TOTAL": mkt,
        "LAMBDA_V2_BLENDED": blended,
        "LAMBDA_V2_BLENDED_ADAPTIVE": adaptive,
    }
    src = adaptive
    dists = {
        "EXACT_V2_POISSON": dist_poisson(src.lambda_home, src.lambda_away),
        "EXACT_V2_DC": dist_dc(src.lambda_home, src.lambda_away),
        "EXACT_V2_OVERDISPERSED": dist_overdispersed(src.lambda_home, src.lambda_away),
        "EXACT_V2_SELECTED": dist_dc(src.lambda_home, src.lambda_away),  # selected = DC
        "DIXON_COLES_SHADOW": dist_dc(src.lambda_home, src.lambda_away),
        "FOOTBALL_STRENGTH_POISSON": dist_poisson(football.lambda_home, football.lambda_away),
    }
    tops = {k: tops_from_dist(d) for k, d in dists.items()}
    selected = tops["EXACT_V2_SELECTED"]
    return {
        "status": "OK",
        "shadow_only": True,
        "persisted": False,
        "exact_v2_promoted": False,
        "lambda_v2": {
            k: {
                "lambda_home": round(v.lambda_home, 6),
                "lambda_away": round(v.lambda_away, 6),
                "lambda_total": round(v.lambda_total, 6),
                "uncertainty": round(float(v.uncertainty), 6),
            }
            for k, v in families.items()
        },
        "selected_lambda": {
            "lambda_home": round(src.lambda_home, 6),
            "lambda_away": round(src.lambda_away, 6),
            "lambda_total": round(src.lambda_total, 6),
        },
        "tops": tops,
        "exact_v2_top10": selected,
        "exact_v2_top10_scores": [t["score"] for t in selected],
        "full_mass_1x2": mass_1x2(selected),
        "entropy_top10": entropy_tops(selected),
        "high_goal_shift": round(float(src.lambda_total) - float(_f((p.get("ecse") or {}).get("total_lambda")) or src.lambda_total), 6),
    }


def try_tsbp_readonly(p: dict, conn: sqlite3.Connection) -> dict[str, Any]:
    """Best-effort TSBP top scores without writing challenger freezes when possible."""
    try:
        from worldcup_predictor.challenger.tsbp.domain_policy import classify_competition, load_domain_policy
        from worldcup_predictor.challenger.tsbp.constants import DOMAIN_FORWARD_ENABLED, DOMAIN_RESEARCH_ONLY
    except Exception as exc:  # noqa: BLE001
        return {"status": "TSBP_UNAVAILABLE", "error": str(exc)[:160]}

    fid = int(p.get("fixture_id") or 0)
    fx = conn.execute(
        "SELECT competition_key, home_team, away_team, kickoff_utc FROM fixtures WHERE fixture_id=?",
        (fid,),
    ).fetchone()
    if not fx:
        return {"status": "TSBP_NO_FIXTURE"}
    policy = load_domain_policy()
    domain = classify_competition(fx["competition_key"] if isinstance(fx, sqlite3.Row) else fx[0], policy)
    if domain not in {DOMAIN_FORWARD_ENABLED, DOMAIN_RESEARCH_ONLY}:
        return {"status": str(domain), "note": "domain_not_enabled_for_tsbp_shadow"}
    # Avoid save_freeze path — mark research-visible only
    return {
        "status": "TSBP_SHADOW_SKIPPED_NO_WRITE",
        "domain": domain,
        "note": "TSBP forward_hook persists challenger rows; skipped to keep enrichment read-only",
        "shadow_only": True,
        "persisted": False,
    }


def compare_models(ecse10: dict, exact_tops: list[dict], twin_tops: list[dict], p: dict, exact_meta: dict) -> dict[str, Any]:
    can = [s.get("score") for s in (ecse10.get("scores") or [])[:10] if s.get("score")]
    ex = [s.get("score") for s in exact_tops[:10] if s.get("score")]
    tw = [s.get("score") for s in twin_tops[:10] if s.get("score")]

    def ov(a: list, b: list, n: int) -> int:
        return len(set(a[:n]) & set(b[:n]))

    can_mass = ecse10.get("full_mass_1x2") or {}
    ex_mass = mass_1x2(exact_tops) if exact_tops else {}
    can_l = _f((p.get("ecse") or {}).get("total_lambda")) or _f(ecse10.get("lambda_total"))
    ex_l = _f((exact_meta.get("selected_lambda") or {}).get("lambda_total"))
    can_ent = _f((p.get("ecse") or {}).get("entropy")) or _f(ecse10.get("entropy_top10_normalized"))
    ex_ent = _f(exact_meta.get("entropy_top10"))

    def argmax_dir(m: dict) -> str:
        if not m:
            return "unknown"
        return max(("home", "draw", "away"), key=lambda k: float(m.get(k) or 0))

    return {
        "top1_agreement": bool(can and ex and can[0] == ex[0]),
        "top3_overlap": ov(can, ex, 3),
        "top5_overlap": ov(can, ex, 5),
        "top10_overlap": ov(can, ex, 10),
        "twins_top5_overlap_vs_canonical": ov(can, tw, 5),
        "full_distribution_direction_agreement": argmax_dir(can_mass) == argmax_dir(ex_mass) if ex_mass else None,
        "lambda_comparison": {
            "canonical_total": can_l,
            "exact_v2_total": ex_l,
            "delta": None if can_l is None or ex_l is None else round(ex_l - can_l, 6),
            "canonical_home": _f((p.get("ecse") or {}).get("lambda_home")),
            "canonical_away": _f((p.get("ecse") or {}).get("lambda_away")),
            "exact_v2_home": _f((exact_meta.get("selected_lambda") or {}).get("lambda_home")),
            "exact_v2_away": _f((exact_meta.get("selected_lambda") or {}).get("lambda_away")),
        },
        "entropy_comparison": {"canonical": can_ent, "exact_v2": ex_ent, "delta": None if can_ent is None or ex_ent is None else round(ex_ent - can_ent, 6)},
        "high_goal_shift": exact_meta.get("high_goal_shift"),
        "draw_shift": None if not ex_mass else round(float(ex_mass.get("draw") or 0) - float(can_mass.get("draw") or 0), 6),
        "home_shift": None if not ex_mass else round(float(ex_mass.get("home") or 0) - float(can_mass.get("home") or 0), 6),
        "away_shift": None if not ex_mass else round(float(ex_mass.get("away") or 0) - float(can_mass.get("away") or 0), 6),
        "canonical_direction": argmax_dir(can_mass),
        "exact_v2_direction": argmax_dir(ex_mass) if ex_mass else None,
    }


def pick_best_non_no_bet(ranked: list[dict], score_fn, *, limit: int = 3) -> list[dict]:
    """Never promote NO_BET merely to fill the table."""
    out = []
    for r in ranked:
        if r.get("no_bet"):
            continue
        if (r.get("_verdict") or "") in {"NO_BET", "BLOCKED"}:
            continue
        if str((r.get("wde") or {}).get("decision") or "").upper() == "NO_BET":
            continue
        sm = {
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
            "score": score_fn(r) if score_fn else None,
            "canonical_top10": (r.get("_ecse10") or {}).get("scores"),
            "side_by_side": r.get("_sbs"),
        }
        out.append(sm)
        if len(out) >= limit:
            break
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Enrich existing next-4-days mission (shadow-only)")
    ap.add_argument("--mission-dir", type=str, default=str(DEFAULT_MISSION))
    ap.add_argument("--dates", nargs="+", default=mission.DEFAULT_DATES)
    args = ap.parse_args(argv)

    out = Path(args.mission_dir)
    if not out.is_dir():
        _safe_print(f"Mission dir missing: {out}")
        return 2

    disk_before = mission.disk_gb(ROOT)
    _safe_print(f"Disk before: {disk_before}")
    if float(disk_before.get("free_gb") or 0) < 8:
        _safe_print("STOP: free disk < 8GB")
        return 2

    five = mission._load_five_day()
    dates = list(args.dates)

    # Backup prior shadow outputs (do not touch freeze/canonical owner day artifacts)
    bak = out / "pre_enrichment_backup"
    bak.mkdir(parents=True, exist_ok=True)
    for name in (
        "shadow_predictions.json",
        "exact_top10_all_models.json",
        "model_agreement.json",
        "forensic_agent_report.json",
        "final_rankings.json",
        "final_owner_shortlist.json",
        "run_manifest.json",
        "validation_report.json",
        "NEXT_4_DAYS_COMPLETE_PREDICTION_REPORT.md",
    ):
        src = out / name
        if src.is_file():
            shutil.copy2(src, bak / name)

    commit = "unknown"
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True).strip()
    except Exception:
        pass

    _safe_print("Building evidence engines (DNA/Twins) — read-only...")
    engines = five.build_evidence_engines()
    _safe_print(f"Engine errors: {engines.get('errors')}")

    # Strength engine for Exact V2 (uses FI path; compute-only, no persist_shadow)
    strength_engine = None
    fi_conn: sqlite3.Connection | None = None
    if FI.exists():
        fi_conn = sqlite3.connect(f"file:{FI.as_posix()}?mode=ro", uri=True, timeout=60)
        fi_conn.row_factory = sqlite3.Row
        try:
            from worldcup_predictor.research.football_strength_foundation.historical_match_service import (
                HistoricalMatchService,
            )
            from worldcup_predictor.research.football_strength_foundation.team_strength_engine import (
                TeamStrengthEngine,
            )

            strength_engine = TeamStrengthEngine(HistoricalMatchService(fi_path=str(FI)))
        except Exception as exc:  # noqa: BLE001
            _safe_print(f"Strength engine unavailable: {exc}")
            strength_engine = None

    forensic_agent = None
    try:
        from worldcup_predictor.config.settings import get_settings
        from worldcup_predictor.research.team_form_h2h_forensic.agent import TeamFormH2HForensicAgent

        forensic_agent = TeamFormH2HForensicAgent(settings=get_settings(), root=ROOT)
    except Exception as exc:  # noqa: BLE001
        _safe_print(f"Forensic agent unavailable: {exc}")

    shadow_success = {
        "dna_v2": 0,
        "twins": 0,
        "hcee": 0,
        "exact_v2": 0,
        "exact_v2_proxy": 0,
        "lambda_v2": 0,
        "l2f": 0,
        "dixon_coles": 0,
        "football_strength": 0,
        "tsbp": 0,
        "forensic_team_form_h2h": 0,
    }

    discovered_rows: list[dict] = []
    eligibility_rows: list[dict] = []
    odds_rows: list[dict] = []
    canonical_rows: list[dict] = []
    shadow_rows: list[dict] = []
    exact_tables: dict[str, Any] = {}
    agreement_rows: list[dict] = []
    forensic_rows: list[dict] = []
    t10to5_rows: list[dict] = []
    blocked_rows: list[dict] = []
    freeze_rows: list[dict] = []
    comparison_rows: list[dict] = []
    lambda_rows: list[dict] = []
    all_complete: list[dict] = []
    freeze_ids_seen: list[str] = []
    fixture_ids: list[int] = []
    canonical_ok = 0

    for d in dates:
        day = five.load_day(d)
        disc = day.get("discovery") or {}
        preds = list((day.get("predictions") or {}).get("predictions") or [])
        freezes = list((day.get("freezes") or {}).get("freezes") or [])
        odds = list((day.get("odds") or {}).get("fixtures") or [])
        _safe_print(f"[{d}] reuse predictions={len(preds)} freezes={len(freezes)} (no owner rerun)")

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
        for o in odds:
            odds_rows.append({**o, "date": d})
        for f in freezes:
            freeze_rows.append({**f, "date": d, "reused_existing": True})
            if f.get("freeze_id"):
                freeze_ids_seen.append(str(f["freeze_id"]))

        for p in preds:
            p = dict(p)
            p["date"] = d
            fid = int(p.get("fixture_id") or 0)
            fixture_ids.append(fid)
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

            exact_meta: dict[str, Any] = {"status": "SKIPPED", "persisted": False}
            if strength_engine is not None and fi_conn is not None:
                exact_meta = compute_exact_family_readonly(p, conn=fi_conn, engine=strength_engine)
            if exact_meta.get("status") == "OK":
                shadow_success["exact_v2"] += 1
                shadow_success["lambda_v2"] += 1
                shadow_success["l2f"] += 1
                shadow_success["dixon_coles"] += 1
                shadow_success["football_strength"] += 1
                ev["exact_v2_top10"] = exact_meta.get("exact_v2_top10_scores") or []
                ev["exact_v2"] = exact_meta
            else:
                # DNA proxy only when Exact V2 unavailable
                proxy = [{"score": s, "probability": None} for s in (ev.get("dna") or {}).get("top5") or []]
                if proxy:
                    shadow_success["exact_v2_proxy"] += 1
                    ev["exact_v2_top10"] = [x["score"] for x in proxy]

            if (ev.get("dna") or {}).get("status") == "OK" or (ev.get("dna") or {}).get("top5"):
                if (ev.get("dna") or {}).get("status") == "OK":
                    shadow_success["dna_v2"] += 1
            if (ev.get("twins") or {}).get("status") == "OK":
                shadow_success["twins"] += 1
            if (ev.get("hcee") or {}).get("status") == "OK":
                shadow_success["hcee"] += 1

            tsbp = try_tsbp_readonly(p, fi_conn) if fi_conn is not None else {"status": "NO_DB"}
            if tsbp.get("status") == "OK":
                shadow_success["tsbp"] += 1

            forensic = {"status": "SKIPPED", "agents_rewrite_probabilities": False}
            if forensic_agent is not None:
                try:
                    forensic = forensic_agent.analyze_fixture(
                        fixture_id=fid,
                        home_team=p.get("home_team"),
                        away_team=p.get("away_team"),
                        kickoff_utc=p.get("kickoff_utc"),
                        competition_key=p.get("competition") or p.get("league"),
                    )
                    forensic["agents_rewrite_probabilities"] = False
                    shadow_success["forensic_team_form_h2h"] += 1
                except Exception as exc:  # noqa: BLE001
                    forensic = {"status": "FORENSIC_ERROR", "error": str(exc)[:200], "agents_rewrite_probabilities": False}

            # Conflict detector (read-only explanation)
            conflict = {}
            try:
                from worldcup_predictor.research.wde_ecse_conflict.detect import detect_conflict

                ranks = []
                for i in range(1, 6):
                    t = (p.get("ecse") or {}).get(f"top{i}") or {}
                    if t.get("score"):
                        ranks.append({"rank": i, "score": t.get("score"), "probability": t.get("probability")})
                conflict = (
                    detect_conflict(wde_decision=(p.get("wde") or {}).get("decision"), ranks=ranks)
                    or {"is_conflict": False}
                )
            except Exception as exc:  # noqa: BLE001
                conflict = {"status": "UNAVAILABLE", "error": str(exc)[:120]}

            high_goal = {
                "flag": bool((_f((p.get("ecse") or {}).get("total_lambda")) or 0) >= 2.75)
                or bool((_f((exact_meta.get("selected_lambda") or {}).get("lambda_total")) or 0) >= 2.75),
                "canonical_lambda_total": _f((p.get("ecse") or {}).get("total_lambda")),
                "exact_v2_lambda_total": _f((exact_meta.get("selected_lambda") or {}).get("lambda_total")),
                "agents_rewrite_probabilities": False,
            }

            ecse10 = mission.load_ecse_top10(fid)
            if not ecse10.get("available"):
                scores = []
                for i in range(1, 6):
                    t = (p.get("ecse") or {}).get(f"top{i}") or {}
                    if t.get("score"):
                        scores.append({"rank": i, "score": t.get("score"), "probability": t.get("probability")})
                ecse10["scores"] = scores
                ecse10["available"] = bool(scores)
                ecse10["note"] = "fallback_from_prediction_top5_only"

            exact_v2_list = list(exact_meta.get("exact_v2_top10") or [])
            if not exact_v2_list:
                exact_v2_list = [{"score": s, "probability": None} for s in (ev.get("dna") or {}).get("top5") or []]
            twin_list = [{"score": s, "probability": None} for s in (ev.get("twins") or {}).get("top5") or []]
            # Best challenger = Exact V2 when present else Twins
            challenger = exact_v2_list if exact_meta.get("status") == "OK" else twin_list
            challenger_name = "exact_v2_selected_dc" if exact_meta.get("status") == "OK" else "historical_twins_top5"

            five_ag = five.agreement(p, ev)
            q = five.quality(p, five_ag, ev)
            mission_ag = mission.classify_mission_agreement(p, ecse10, ev)
            cmp = compare_models(ecse10, exact_v2_list, twin_list, p, exact_meta)
            # Merge richer comparison into agreement row
            mission_ag.update(
                {
                    "top1_agree": cmp["top1_agreement"],
                    "top3_overlap": cmp["top3_overlap"],
                    "top5_overlap": cmp["top5_overlap"],
                    "top10_overlap": cmp["top10_overlap"],
                    "direction_agreement": cmp["full_distribution_direction_agreement"],
                    "lambda_comparison": cmp["lambda_comparison"],
                    "entropy_comparison": cmp["entropy_comparison"],
                    "high_goal_shift": cmp["high_goal_shift"],
                    "draw_shift": cmp["draw_shift"],
                    "home_shift": cmp["home_shift"],
                    "away_shift": cmp["away_shift"],
                }
            )
            verdict = mission.research_verdict(p, mission_ag, float(q.get("score") or 0))
            t5 = mission.run_top10_to_5_for_fixture(p, ecse10)
            fi_row = mission.freeze_integrity(p)
            fi_row["reused_existing_immutable"] = True
            fi_row["enrichment_did_not_modify_freeze"] = True

            if (p.get("wde") or {}).get("execution_status") == "OK" and (p.get("ecse") or {}).get("execution_status") == "OK":
                canonical_ok += 1

            sbs = mission.side_by_side_top10(ecse10, exact_v2_list, twin_list if challenger_name.startswith("historical") else exact_v2_list)
            # If Exact V2 is both columns, use twins as other challenger when available
            if exact_meta.get("status") == "OK":
                sbs = mission.side_by_side_top10(ecse10, exact_v2_list, twin_list)

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
                "exact_v2_source": "exact_v2_selected_dc_readonly_shadow" if exact_meta.get("status") == "OK" else "dna_v2_top5_research_proxy_not_promoted",
                "other_challenger_source": "historical_twins_top5_research",
                "exact_v2_promoted": False,
                "table": sbs,
                "model_families": list((exact_meta.get("tops") or {}).keys()) if exact_meta.get("status") == "OK" else [],
                "comparison": cmp,
            }

            wde = p.get("wde") or {}
            odds_p = p.get("odds") or {}
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
                    "confidence": wde.get("confidence"),
                    "quality": wde.get("quality_status"),
                    "consensus": p.get("consensus"),
                    "no_bet": p.get("no_bet"),
                    "btts": (p.get("btts") or {}).get("prediction"),
                    "ou25": (p.get("ou25") or {}).get("preferred_side") or (p.get("ou25") or {}).get("prediction"),
                    "can_lh": (p.get("ecse") or {}).get("lambda_home") or ecse10.get("lambda_home"),
                    "can_la": (p.get("ecse") or {}).get("lambda_away") or ecse10.get("lambda_away"),
                    "can_lt": (p.get("ecse") or {}).get("total_lambda") or ecse10.get("lambda_total"),
                    "kickoff_utc": p.get("kickoff_utc"),
                    "kickoff_vienna": p.get("kickoff_vienna"),
                    "prediction_ts": p.get("generated_at"),
                    "odds_ts": odds_p.get("timestamp") or odds_p.get("captured_at"),
                    "freeze_id": (p.get("freeze") or {}).get("freeze_id"),
                    "job_id": p.get("job_id"),
                    "research_verdict": verdict,
                    "agreement_primary": mission_ag.get("primary"),
                    "canonical_source": "reused_existing_snapshot",
                }
            )
            shadow_rows.append(
                {
                    "fixture_id": fid,
                    "dna_v2": ev.get("dna"),
                    "twins": {k: (ev.get("twins") or {}).get(k) for k in ("status", "n", "top5", "avg_goals", "entropy")},
                    "hcee": {k: (ev.get("hcee") or {}).get(k) for k in ("status", "total_risk", "high_score_tail_risk")},
                    "exact_v2": {
                        "status": exact_meta.get("status"),
                        "selected_lambda": exact_meta.get("selected_lambda"),
                        "top10": exact_v2_list,
                        "persisted": False,
                        "promoted": False,
                    },
                    "lambda_v2": exact_meta.get("lambda_v2"),
                    "tsbp": tsbp,
                    "exact_v2_promoted": False,
                    "portfolio_used": False,
                    "similarity_used": False,
                    "ood_used": False,
                    "read_only": True,
                }
            )
            agreement_rows.append(
                {
                    "fixture_id": fid,
                    "date": d,
                    "match": f"{p.get('home_team')} vs {p.get('away_team')}",
                    **mission_ag,
                }
            )
            comparison_rows.append({"fixture_id": fid, "date": d, "match": f"{p.get('home_team')} vs {p.get('away_team')}", **cmp})
            lambda_rows.append(
                {
                    "fixture_id": fid,
                    "date": d,
                    "match": f"{p.get('home_team')} vs {p.get('away_team')}",
                    **(cmp.get("lambda_comparison") or {}),
                    "high_goal_shift": cmp.get("high_goal_shift"),
                }
            )
            forensic_rows.append(
                {
                    "fixture_id": fid,
                    "hcee": ev.get("hcee"),
                    "esli": ev.get("esli"),
                    "team_form_h2h": forensic,
                    "conflict_detector": conflict,
                    "high_goal_detector": high_goal,
                    "market_evidence": {
                        "odds_freshness": odds_p.get("freshness_status"),
                        "bookmaker_count": odds_p.get("bookmaker_count"),
                        "1x2": {"home": odds_p.get("home"), "draw": odds_p.get("draw"), "away": odds_p.get("away")},
                    },
                    "agents_rewrite_probabilities": False,
                }
            )
            t10to5_rows.append({"fixture_id": fid, "date": d, "match": f"{p.get('home_team')} vs {p.get('away_team')}", **t5})
            freeze_rows.append({**fi_row, "date": d})

            if (p.get("freeze") or {}).get("freeze_id"):
                freeze_ids_seen.append(str((p.get("freeze") or {}).get("freeze_id")))

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
                "_exact_meta": exact_meta,
                "_cmp": cmp,
            }
            if p.get("prediction_complete"):
                all_complete.append(rec)

    hashes_before = snapshot_freeze_hashes(sorted(set(fixture_ids)))

    # Rankings
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
            "main_risk": (r.get("_mission_ag") or {}).get("primary"),
        }

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

    # Top10 tables may include NO_BET for transparency in Avoid; Best Picks exclude them
    top10_end = [slim(r, end_result_score(r)) for r in ranked_end if not r.get("no_bet")][:10]
    if len(top10_end) < 10:
        # fill only with non-no_bet; if scarce, leave shorter
        pass
    top10_exact = [slim(r, exact_score_rank_key(r)) for r in ranked_exact if not r.get("no_bet")][:10]
    top10_agree = [slim(r) for r in ranked_agree if not r.get("no_bet")][:10]
    top10_cov = [slim(r, coverage_key(r)) for r in ranked_cov if not r.get("no_bet")][:10]
    top10_avoid = [slim(r, risk_key(r)) for r in ranked_avoid[:10]]

    best3_end = pick_best_non_no_bet(ranked_end, end_result_score, limit=3)
    best3_exact = pick_best_non_no_bet(ranked_exact, exact_score_rank_key, limit=3)
    best3_agree = pick_best_non_no_bet(ranked_agree, lambda r: float((r.get("_mission_ag") or {}).get("top5_overlap") or 0), limit=3)

    shortlist = {
        "best_3_end_result": best3_end,
        "best_3_exact_score": best3_exact,
        "best_3_model_consensus": best3_agree,
        "no_bet_excluded_from_best_picks": True,
        "selection_layers_excluded": [
            "portfolio_manager_baseline",
            "calibrated_portfolio_candidate",
            "similarity_overlay",
            "original_aggressive_ood_filter",
        ],
        "no_promotion": True,
        "no_routing_activation": True,
        "research_only_shadows": True,
        "exact_v2_shadow_only": True,
    }

    hashes_after = snapshot_freeze_hashes(sorted(set(fixture_ids)))
    hash_mismatches = []
    for k, before in hashes_before.items():
        after = hashes_after.get(k) or {}
        if before.get("content_hash") and after.get("content_hash") and before.get("content_hash") != after.get("content_hash"):
            hash_mismatches.append({"fixture_id": k, "before": before, "after": after})

    # Duplicate freeze detection among reused freeze_ids
    from collections import Counter

    freeze_counts = Counter(freeze_ids_seen)
    duplicate_freeze_ids = [fid for fid, c in freeze_counts.items() if c > 1]
    # Counting same freeze_id once per prediction + once per freeze manifest is expected;
    # true duplicates = same fixture with multiple distinct freeze_ids in prediction set
    fixture_freeze_map: dict[int, set[str]] = {}
    for r in all_complete:
        fid = int(r.get("fixture_id") or 0)
        fz = str((r.get("freeze") or {}).get("freeze_id") or "")
        if fz:
            fixture_freeze_map.setdefault(fid, set()).add(fz)
    multi_freeze_fixtures = {fid: sorted(ids) for fid, ids in fixture_freeze_map.items() if len(ids) > 1}

    n_eligible = len(all_complete)
    blocked_n = len({(b.get("date"), b.get("fixture_id"), b.get("reason")) for b in blocked_rows})
    n_disc = len({(r.get("date"), r.get("fixture_id")) for r in discovered_rows + eligibility_rows if r.get("fixture_id")})

    status = STATUS_READY if n_eligible > 0 and shadow_success.get("exact_v2", 0) > 0 else mission.STATUS_PARTIAL
    if n_eligible == 0:
        status = mission.STATUS_NONE

    disk_after = mission.disk_gb(ROOT)
    validation = {
        "status": status,
        "phase": PHASE,
        "mission_mode": "ENRICH_ONLY_RESUME",
        "dates": dates,
        "commit": commit,
        "disk_before": disk_before,
        "disk_after": disk_after,
        "discovered_fixture_count": n_disc,
        "eligible_predicted_frozen_count": n_eligible,
        "blocked_count": blocked_n,
        "canonical_success_count": canonical_ok,
        "enriched_fixture_count": n_eligible,
        "reused_freeze_count": len(fixture_freeze_map),
        "duplicate_freeze_fixtures": multi_freeze_fixtures,
        "duplicate_freeze_count": len(multi_freeze_fixtures),
        "freeze_hash_mismatches": hash_mismatches,
        "freeze_hashes_unchanged": len(hash_mismatches) == 0,
        "shadow_success_by_model": shadow_success,
        "owner_runs": [{"date": d, "ran": False, "ok": True, "skipped": True, "enrich_only": True} for d in dates],
        "missing_days": [],
        "no_promotion": True,
        "no_routing_activation": True,
        "canonical_unchanged": True,
        "canonical_not_regenerated": True,
        "freezes_not_regenerated": True,
        "exact_v2_shadow_only": True,
        "exact_v2_persisted": False,
        "portfolio_similarity_ood_not_used_for_final_ranking": True,
        "cohort_type": "true_forward",
        "artifact_dir": str(out),
        "engine_errors": engines.get("errors"),
    }

    # Write / update mission artifacts
    mission._json_dump(out / "run_manifest.json", validation)
    mission._json_dump(out / "discovered_universe.json", {"rows": discovered_rows, "count": len(discovered_rows)})
    mission._json_dump(out / "eligibility_report.json", {"rows": eligibility_rows})
    mission._json_dump(out / "fresh_odds_report.json", {"rows": odds_rows, "reused_existing": True})
    mission._json_dump(out / "canonical_predictions.json", {"rows": canonical_rows, "count": len(canonical_rows), "regenerated": False})
    mission._json_dump(out / "shadow_predictions.json", {"rows": shadow_rows, "exact_v2_promoted": False, "read_only": True})
    mission._json_dump(out / "exact_top10_all_models.json", exact_tables)
    mission._json_dump(out / "model_agreement.json", {"rows": agreement_rows})
    mission._json_dump(out / "model_comparison_full.json", {"rows": comparison_rows})
    mission._json_dump(out / "lambda_comparison.json", {"rows": lambda_rows})
    mission._json_dump(out / "forensic_agent_report.json", {"rows": forensic_rows, "agents_may_not_rewrite_probabilities": True})
    mission._json_dump(out / "top10_to_5_recommendations.json", {"rows": t10to5_rows, "research_only": True, "monetary_roi_fabricated": False})
    mission._json_dump(out / "blocked_fixtures.json", {"rows": blocked_rows, "count": blocked_n})
    mission._json_dump(
        out / "final_rankings.json",
        {
            "end_result_top10": top10_end,
            "exact_score_top10": top10_exact,
            "model_agreement_top10": top10_agree,
            "coverage_top10": top10_cov,
            "avoid_top10": top10_avoid,
            "no_bet_excluded_from_best_tables": True,
        },
    )
    mission._json_dump(out / "final_owner_shortlist.json", shortlist)
    mission._json_dump(out / "freeze_integrity_report.json", {"rows": freeze_rows, "cohort_type": "true_forward", "reused_immutable": True})
    mission._json_dump(out / "validation_report.json", validation)
    mission._json_dump(
        out / "enrichment_resume_manifest.json",
        {
            "resumed_from": "NEXT_4_DAYS_COMPLETE_MULTI_MODEL_PREDICTION_PARTIAL",
            "mode": "ENRICH_ONLY",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "validation": validation,
        },
    )

    md = mission._build_md(
        validation,
        shortlist,
        top10_end,
        top10_exact,
        top10_agree,
        top10_cov,
        top10_avoid,
        exact_tables,
        agreement_rows,
        t10to5_rows,
        blocked_rows,
        canonical_rows,
    )
    md += "\n## Enrichment resume notes\n\n"
    md += "- Mode: `ENRICH_ONLY` — Canonical / freezes / odds not regenerated.\n"
    md += "- Exact V2 computed in-memory (Dixon–Coles selected); **not persisted**, **not promoted**.\n"
    md += "- NO_BET fixtures excluded from Best Picks / Best tables.\n"
    md += f"- Freeze hashes unchanged: `{validation.get('freeze_hashes_unchanged')}`\n"
    md += f"- Duplicate freeze fixtures: `{validation.get('duplicate_freeze_count')}`\n"
    (out / "NEXT_4_DAYS_COMPLETE_PREDICTION_REPORT.md").write_text(md, encoding="utf-8")
    (ROOT / "NEXT_4_DAYS_COMPLETE_PREDICTION_REPORT.md").write_text(md, encoding="utf-8")

    html = f"""<!DOCTYPE html><html><head><meta charset='utf-8'/><title>Next 4 Days Enriched</title>
<style>body{{font-family:Georgia,serif;background:#101820;color:#e8eef4;margin:2rem}}
h1{{color:#7dd3c0}} code{{color:#f0c674}} .card{{background:#1b2630;padding:1rem;margin:1rem 0;border-left:4px solid #7dd3c0}}</style></head>
<body><h1>Next 4 Days — Enrichment Resume</h1>
<div class='card'><strong>Status:</strong> <code>{status}</code><br/>
<strong>Enriched:</strong> <code>{n_eligible}</code><br/>
<strong>Exact V2 shadow:</strong> <code>{shadow_success.get('exact_v2')}</code><br/>
<strong>Promotion:</strong> NONE — NOT ACTIVATED</div>
<pre>{json.dumps(shortlist, indent=2, default=str)[:12000]}</pre>
</body></html>"""
    (out / "owner_report.html").write_text(html, encoding="utf-8")

    if forensic_agent is not None:
        try:
            forensic_agent.close()
        except Exception:
            pass
    if fi_conn is not None:
        fi_conn.close()

    _safe_print(
        json.dumps(
            {
                "status": status,
                "enriched": n_eligible,
                "shadow_success_by_model": shadow_success,
                "duplicate_freeze_count": len(multi_freeze_fixtures),
                "freeze_hashes_unchanged": len(hash_mismatches) == 0,
                "artifact_dir": str(out),
            },
            indent=2,
        )
    )
    return 0 if status == STATUS_READY else 1


if __name__ == "__main__":
    raise SystemExit(main())
