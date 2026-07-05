#!/usr/bin/env python3
"""EXACT-SCORE-FORENSIC — Phase 1-5 validation for 3 R16 fixtures (read-only + shadow)."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if not os.environ.get("APP_ENV") and (ROOT / ".env.production").is_file():
    os.environ.setdefault("APP_ENV", "production")

from worldcup_predictor.automation.worldcup_background.prediction_runner import build_api_payload
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.orchestration.predict_pipeline import PredictPipeline
from worldcup_predictor.research.ecse_live.prediction_builder import MODEL_VERSION, build_ecse_live_prediction
from worldcup_predictor.research.ecse_score_distribution import generate_score_distribution

PHASE = "EXACT-SCORE-FORENSIC-AND-CONTROLLED-MODEL-VALIDATION"
ARTIFACT = ROOT / "artifacts" / "exact_score_forensic" / "validation_report.json"
FIXTURES = [1569870, 1568100, 1570714]


def _pct(x: float | None) -> float | None:
    if x is None:
        return None
    v = float(x)
    return round(v * 100, 2) if v <= 1 else round(v, 2)


def _hash(raw: str | None) -> str:
    if not raw:
        return ""
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _aggregate_matrix(top10: list[dict]) -> dict[str, float]:
    home = draw = away = btts_yes = over25 = 0.0
    for e in top10:
        p = float(e.get("probability") or 0)
        h = int(e.get("home_goals", 0))
        a = int(e.get("away_goals", 0))
        if h > a:
            home += p
        elif h < a:
            away += p
        else:
            draw += p
        if h > 0 and a > 0:
            btts_yes += p
        if h + a > 2:
            over25 += p
    return {
        "home_win_pct": round(home * 100, 2),
        "draw_pct": round(draw * 100, 2),
        "away_win_pct": round(away * 100, 2),
        "btts_yes_pct": round(btts_yes * 100, 2),
        "over_2_5_pct": round(over25 * 100, 2),
    }


def _full_matrix_probs(lambda_home: float, lambda_away: float, limit: int = 10) -> list[dict]:
    dist = generate_score_distribution(lambda_home, lambda_away)
    return dist[:limit] if dist else []


def _forensic_snapshot(conn: sqlite3.Connection, fid: int) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT * FROM ecse_prediction_snapshots WHERE fixture_id=? ORDER BY id ASC",
        (fid,),
    ).fetchall()
    if not rows:
        return {"stored": False, "snapshot_count": 0}

    latest = dict(rows[-1])
    first = dict(rows[0])
    top10 = json.loads(latest.get("top_10_scorelines_json") or "[]")
    top3 = json.loads(latest.get("top_3_scores_json") or "[]")
    top5 = json.loads(latest.get("top_5_scores_json") or "[]")
    raw = {}
    if latest.get("raw_features_json"):
        try:
            raw = json.loads(latest["raw_features_json"])
        except json.JSONDecodeError:
            raw = {"parse_error": True}

    # ranking consistency: top3 must equal first 3 of sorted top10 by probability
    sorted10 = sorted(top10, key=lambda x: float(x.get("probability") or 0), reverse=True)
    top3_from_matrix = [e["scoreline"] for e in sorted10[:3]]
    top5_from_matrix = [e["scoreline"] for e in sorted10[:5]]
    ranking_ok = list(top3) == top3_from_matrix
    top5_ok = list(top5) == top5_from_matrix

    prob_map = {str(e["scoreline"]): float(e["probability"]) for e in top10 if e.get("scoreline")}
    top3_probs = [
        {"score": s, "prob_pct": round(prob_map.get(str(s), 0) * 100, 2)} for s in top3
    ]

    return {
        "stored": True,
        "snapshot_count": len(rows),
        "first_snapshot_id": first.get("id"),
        "latest_snapshot_id": latest.get("id"),
        "overwrite_detected": len(rows) > 1,
        "generated_at": latest.get("generated_at"),
        "first_generated_at": first.get("generated_at"),
        "model_version": latest.get("model_version"),
        "current_code_model_version": MODEL_VERSION,
        "model_version_match": latest.get("model_version") == MODEL_VERSION,
        "prediction_source": latest.get("prediction_source") or raw.get("source"),
        "lambda_home": latest.get("lambda_home"),
        "lambda_away": latest.get("lambda_away"),
        "is_frozen": latest.get("is_frozen"),
        "top1": latest.get("top_1_score"),
        "top3": top3,
        "top5": top5,
        "top3_with_probs": top3_probs,
        "top10": top10,
        "ranking_consistent_with_matrix": ranking_ok,
        "top5_consistent_with_matrix": top5_ok,
        "raw_features": raw,
        "fallback_path": _classify_fallback(raw, latest),
        "aggregated": _aggregate_matrix(top10),
    }


def _classify_fallback(raw: dict, snap: dict) -> str:
    src = str(snap.get("prediction_source") or raw.get("source") or "")
    if "manual" in src.lower() or "poisson_fallback" in json.dumps(raw).lower():
        return "manual_poisson_fallback"
    if src == "registry_precomputed":
        return "registry_precomputed"
    if src == "live_odds":
        return "live_odds_lambda_path"
    if src == "multi_provider_live":
        return "multi_provider_live"
    if raw.get("lambda_features"):
        return "live_odds_lambda_path"
    return src or "unknown"


def _forensic_wde(conn: sqlite3.Connection, fid: int) -> dict[str, Any]:
    row = conn.execute(
        "SELECT payload_json, predicted_at, source FROM worldcup_stored_predictions WHERE fixture_id=?",
        (fid,),
    ).fetchone()
    if not row:
        return {"stored": False}
    p = json.loads(row["payload_json"])
    pr = p.get("probabilities") or {}
    btts = pr.get("btts") or {}
    ou = pr.get("over_under_2_5") or {}
    odds = conn.execute(
        "SELECT snapshot_at, payload_json FROM odds_snapshots WHERE fixture_id=? ORDER BY id DESC LIMIT 1",
        (fid,),
    ).fetchone()
    odds_n = conn.execute("SELECT COUNT(*) FROM odds_snapshots WHERE fixture_id=?", (fid,)).fetchone()[0]
    return {
        "stored": True,
        "predicted_at": row["predicted_at"],
        "source": row["source"],
        "payload_hash": _hash(row["payload_json"]),
        "generated_by": p.get("generated_by"),
        "engine_version": p.get("prediction_engine_version"),
        "pick": p.get("prediction"),
        "H": pr.get("home_win"),
        "X": pr.get("draw"),
        "A": pr.get("away_win"),
        "confidence": p.get("confidence"),
        "btts_pick": btts.get("selection"),
        "btts_yes": (btts.get("probabilities") or {}).get("yes"),
        "ou_pick": ou.get("selection"),
        "ou_prob": (ou.get("probabilities") or {}).get(ou.get("selection")),
        "odds_freshness_status": p.get("odds_freshness_status"),
        "odds_snapshots_count": int(odds_n),
        "latest_odds_snapshot_at": odds["snapshot_at"] if odds else None,
        "trace": p.get("data_source_trace"),
    }


def _shadow_wde(settings, fid: int) -> dict[str, Any]:
    pipe = PredictPipeline(settings, competition_key="world_cup_2026", locale="en")
    result = pipe.run(fixture_id=fid, record_history=False)
    if not result.success or not result.prediction:
        return {"ok": False, "errors": [r.message for r in result.agent_results if not r.success]}
    pred = result.prediction
    payload = build_api_payload(result, intelligence_report=result.intelligence_report, specialist_report=result.specialist_report)
    pr = payload.get("probabilities") or {}
    btts = pr.get("btts") or {}
    ou = pr.get("over_under_2_5") or {}
    return {
        "ok": True,
        "pick": payload.get("prediction") or pred.one_x_two.selection,
        "H": pr.get("home_win"),
        "X": pr.get("draw"),
        "A": pr.get("away_win"),
        "confidence": payload.get("confidence") or pred.confidence_score,
        "btts_pick": btts.get("selection"),
        "btts_yes": (btts.get("probabilities") or {}).get("yes"),
        "ou_pick": ou.get("selection"),
        "ou_prob": (ou.get("probabilities") or {}).get(ou.get("selection")),
        "engine_version": payload.get("prediction_engine_version"),
        "run_mode": "shadow_no_db_write",
    }


def _shadow_ecse(conn, fid: int, fx: dict) -> dict[str, Any]:
    pred = build_ecse_live_prediction(conn, fid, fx)
    if not pred:
        return {"ok": False, "reason": "build_ecse_live_prediction returned None (likely missing odds/lambda inputs)"}
    top10 = pred.get("top_10_scorelines") or []
    return {
        "ok": True,
        "model_version": pred.get("model_version"),
        "prediction_source": pred.get("prediction_source"),
        "lambda_home": pred.get("lambda_home"),
        "lambda_away": pred.get("lambda_away"),
        "top1": pred.get("top_1_score"),
        "top3": pred.get("top_3_scores"),
        "top5": pred.get("top_5_scores"),
        "top10": top10,
        "top3_detail": [
            {
                "score": e["scoreline"],
                "prob_pct": round(float(e["probability"]) * 100, 2),
            }
            for e in top10[:3]
        ],
        "aggregated": _aggregate_matrix(top10),
        "raw_features_keys": list((pred.get("raw_features") or {}).keys()),
        "run_mode": "shadow_no_db_write",
    }


def _compare_top3(old: list, new: list | None) -> str:
    if not new:
        return "DIFFERENT_FROM_PRODUCTION"
    return "SAME_AS_PRODUCTION" if list(old) == list(new[:3]) else "DIFFERENT_FROM_PRODUCTION"


def _trust_status(forensic: dict, shadow_ecse: dict, shadow_wde: dict) -> str:
    if forensic.get("overwrite_detected"):
        return "PRODUCTION_OVERWRITE_DETECTED"
    if not shadow_ecse.get("ok"):
        if forensic.get("stored"):
            return "VERIFIED_BUT_STALE_SNAPSHOT"
        return "NEEDS_FURTHER_INVESTIGATION"
    fb = forensic.get("fallback_path", "")
    if "manual" in fb or "fallback" in fb:
        return "FALLBACK_GENERATED"
    if not forensic.get("model_version_match") and forensic.get("stored"):
        return "MODEL_VERSION_MISMATCH"
    old_t3 = forensic.get("top3") or []
    new_t3 = shadow_ecse.get("top3") or []
    if list(old_t3) != list(new_t3):
        if forensic.get("lambda_home") != shadow_ecse.get("lambda_home") or forensic.get("lambda_away") != shadow_ecse.get("lambda_away"):
            return "INPUT_DATA_MISMATCH"
        return "VERIFIED_BUT_STALE_SNAPSHOT"
    if forensic.get("ranking_consistent_with_matrix"):
        return "VERIFIED_CURRENT_MODEL"
    return "NEEDS_FURTHER_INVESTIGATION"


def _cross_consistency(wde_prod: dict, wde_shadow: dict, ecse_agg: dict, ecse_top1: str) -> dict:
    def wde_side(pick):
        if pick == "home":
            return "home"
        if pick == "away":
            return "away"
        return "draw"

    pick = wde_shadow.get("pick") or wde_prod.get("pick")
    side = wde_side(pick)
    ecse_side_probs = {
        "home": ecse_agg.get("home_win_pct", 0),
        "draw": ecse_agg.get("draw_pct", 0),
        "away": ecse_agg.get("away_win_pct", 0),
    }
    btts_pick = wde_shadow.get("btts_pick") or wde_prod.get("btts_pick")
    ou_pick = wde_shadow.get("ou_pick") or wde_prod.get("ou_pick")
    top1_side = "draw"
    if ecse_top1 and "-" in str(ecse_top1):
        h, a = map(int, str(ecse_top1).split("-", 1))
        top1_side = "home" if h > a else ("away" if a > h else "draw")
    return {
        "wde_pick_side": side,
        "ecse_mass_favored_side": max(ecse_side_probs, key=ecse_side_probs.get),
        "ecse_home_draw_away_pct": ecse_side_probs,
        "ecse_btts_yes_pct": ecse_agg.get("btts_yes_pct"),
        "wde_btts_pick": btts_pick,
        "ecse_over_2_5_pct": ecse_agg.get("over_2_5_pct"),
        "wde_ou_pick": ou_pick,
        "top1_vs_wde_pick_disagreement": side != top1_side,
        "note": "Consistency judged on full ECSE matrix mass, not Top1 alone",
    }


def main() -> int:
    settings = get_settings()
    conn = connect(settings.sqlite_path)
    results = []

    for fid in FIXTURES:
        fx = dict(conn.execute("SELECT * FROM fixtures WHERE fixture_id=?", (fid,)).fetchone() or {})
        forensic_ecse = _forensic_snapshot(conn, fid)
        forensic_wde = _forensic_wde(conn, fid)
        shadow_wde = _shadow_wde(settings, fid)
        shadow_ecse = _shadow_ecse(conn, fid, fx)

        old_top3 = forensic_ecse.get("top3") or []
        new_top3 = shadow_ecse.get("top3") if shadow_ecse.get("ok") else None
        cmp_status = _compare_top3(old_top3, new_top3)

        # Use shadow ECSE aggregated if available else production
        agg = shadow_ecse.get("aggregated") if shadow_ecse.get("ok") else forensic_ecse.get("aggregated", {})
        top1 = shadow_ecse.get("top1") if shadow_ecse.get("ok") else forensic_ecse.get("top1")
        consistency = _cross_consistency(
            forensic_wde, shadow_wde, agg, str(top1 or forensic_ecse.get("top1") or "")
        )

        trust = _trust_status(forensic_ecse, shadow_ecse, shadow_wde)

        # Paraguay specific answers
        paraguay_answers = {}
        if fid == 1569870:
            paraguay_answers = {
                "q1_0_4_genuine_ecse": "0-4" in (forensic_ecse.get("top3") or []) or "0-4" in (forensic_ecse.get("top5") or []),
                "q2_model_version": forensic_ecse.get("model_version"),
                "q3_lambdas": {
                    "lambda_home": forensic_ecse.get("lambda_home"),
                    "lambda_away": forensic_ecse.get("lambda_away"),
                    "input_source": forensic_ecse.get("fallback_path"),
                },
                "q4_same_run_as_0_2_0_3": forensic_ecse.get("ranking_consistent_with_matrix"),
                "q5_fallback_involved": forensic_ecse.get("fallback_path") not in ("live_odds_lambda_path", "registry_precomputed", "multi_provider_live"),
                "q6_ranking_mathematically_consistent": forensic_ecse.get("ranking_consistent_with_matrix"),
                "q7_overwrite_detected": forensic_ecse.get("overwrite_detected"),
            }

        results.append(
            {
                "fixture_id": fid,
                "match": f"{fx.get('home_team')} vs {fx.get('away_team')}",
                "fixture_status": fx.get("status"),
                "phase1_forensic": {
                    "wde": forensic_wde,
                    "ecse": forensic_ecse,
                    "paraguay_specific": paraguay_answers if fid == 1569870 else None,
                },
                "phase2_shadow": {"wde": shadow_wde, "ecse": shadow_ecse},
                "phase3_comparison": {
                    "old_production_top3": old_top3,
                    "new_controlled_top3": new_top3,
                    "status": cmp_status,
                    "why_different": (
                        None
                        if cmp_status == "SAME_AS_PRODUCTION"
                        else {
                            "prod_lambdas": [forensic_ecse.get("lambda_home"), forensic_ecse.get("lambda_away")],
                            "fresh_lambdas": [shadow_ecse.get("lambda_home"), shadow_ecse.get("lambda_away")],
                            "prod_source": forensic_ecse.get("fallback_path"),
                            "fresh_source": shadow_ecse.get("prediction_source"),
                            "shadow_ecse_failed": not shadow_ecse.get("ok"),
                        }
                    ),
                },
                "phase4_cross_model": consistency,
                "phase5_trust_status": trust,
                "recommendation": _recommendation(trust, cmp_status, shadow_ecse.get("ok")),
            }
        )

    conn.close()

    summary_table = []
    for r in results:
        sw = r["phase2_shadow"]["wde"]
        se = r["phase2_shadow"]["ecse"]
        old3 = r["phase3_comparison"]["old_production_top3"]
        summary_table.append(
            {
                "Match": r["match"],
                "Current WDE Pick": sw.get("pick") if sw.get("ok") else r["phase1_forensic"]["wde"].get("pick"),
                "Fresh ECSE Top1": se.get("top1") if se.get("ok") else r["phase1_forensic"]["ecse"].get("top1"),
                "Fresh ECSE Top2": (se.get("top3") or [None, None])[1] if se.get("ok") else (old3[1] if len(old3) > 1 else None),
                "Fresh ECSE Top3": (se.get("top3") or [None, None, None])[2] if se.get("ok") else (old3[2] if len(old3) > 2 else None),
                "Old Production Top3": " / ".join(old3),
                "Same/Different": r["phase3_comparison"]["status"],
                "Trust Status": r["phase5_trust_status"],
            }
        )

    out = {
        "phase": PHASE,
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "constraints": {
            "production_db_written": False,
            "models_retrained": False,
            "public_predictions_modified": False,
        },
        "fixtures": results,
        "summary_table": summary_table,
    }
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    return 0


def _recommendation(trust: str, cmp_status: str, shadow_ok: bool) -> str:
    if trust == "VERIFIED_CURRENT_MODEL":
        return "Trust production ECSE Top3; snapshot matches current model on same inputs."
    if trust == "VERIFIED_BUT_STALE_SNAPSHOT" and shadow_ok:
        return "Production snapshot is valid ECSE path but inputs/lambdas may have shifted; prefer fresh shadow Top3 for decision support only (do not promote)."
    if trust == "INPUT_DATA_MISMATCH":
        return "Re-run odds refresh then shadow ECSE; production snapshot used different lambda inputs."
    if not shadow_ok:
        return "Cannot re-validate live; trust production snapshot provenance only if ranking_consistent."
    return "Investigate before trusting exact-score Top3."


if __name__ == "__main__":
    raise SystemExit(main())
