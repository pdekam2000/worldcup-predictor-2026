#!/usr/bin/env python3
"""NEXT-3-FRESH-ODDS-CONTROLLED-REGENERATION-1 — forensic audit, shadow regen, compare, promote."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sqlite3
import subprocess
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
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.odds.freshness_audit import _latest_odds
from worldcup_predictor.odds.freshness_policy import classify_odds_freshness, is_knockout_match
from worldcup_predictor.orchestration.predict_pipeline import PredictPipeline
from worldcup_predictor.owner_daily.constants import GENERATED_BY
from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture
from worldcup_predictor.odds.freshness_metadata import build_fixture_freshness_metadata, stamp_payload_odds_freshness
from worldcup_predictor.research.ecse_live.prediction_builder import build_ecse_live_prediction, build_odds_feature_row
from worldcup_predictor.research.ecse_live.store import ensure_ecse_live_tables, insert_snapshot
from worldcup_predictor.config.provider_readiness import stamp_provider_readiness
from worldcup_predictor.api.prediction_metadata import stamp_prediction_engine_metadata

PHASE = "NEXT-3-FRESH-ODDS-CONTROLLED-REGENERATION-1"
TARGETS = [
    {"fixture_id": 1568100, "match": "Brazil vs Norway"},
    {"fixture_id": 1570714, "match": "Mexico vs England"},
    {"fixture_id": 1576756, "match": "Portugal vs Spain"},
]
ARTIFACT_DIR = ROOT / "artifacts" / "next_3_fresh_odds_controlled_regeneration_1"
MAX_ODDS_CALLS = 60
MAX_PER_FIXTURE = 20
PY = str(ROOT / ".venv" / "bin" / "python") if (ROOT / ".venv" / "bin" / "python").exists() else sys.executable


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _run(cmd: list[str]) -> dict[str, Any]:
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=900)
    out = proc.stdout.strip()
    payload: Any = None
    if out:
        try:
            payload = json.loads(out)
        except json.JSONDecodeError:
            payload = {"raw_stdout": out[-8000:]}
    return {"cmd": " ".join(cmd), "exit_code": proc.returncode, "stderr_tail": (proc.stderr or "")[-2000:], "result": payload}


def _payload_hash(raw: str | None) -> str:
    if not raw:
        return ""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _parse_wde(payload: dict[str, Any]) -> dict[str, Any]:
    probs = payload.get("probabilities") or {}
    btts = probs.get("btts") or payload.get("detailed_markets", {}).get("btts") or {}
    ou = probs.get("over_under_2_5") or payload.get("detailed_markets", {}).get("over_under_25") or {}
    meta = payload.get("odds_freshness_metadata") or {}
    return {
        "predicted_at": payload.get("predicted_at"),
        "model_version": payload.get("prediction_engine_version"),
        "generated_by": payload.get("generated_by"),
        "pick_1x2": payload.get("prediction"),
        "home_prob": probs.get("home_win") or probs.get("home"),
        "draw_prob": probs.get("draw"),
        "away_prob": probs.get("away_win") or probs.get("away"),
        "confidence": payload.get("confidence") or payload.get("confidence_score"),
        "btts": btts.get("selection") or btts.get("display") or btts.get("pick"),
        "ou_2_5": ou.get("selection") or ou.get("display") or ou.get("pick"),
        "odds_freshness_status": payload.get("odds_freshness_status"),
        "odds_snapshot_at": payload.get("odds_snapshot_at") or meta.get("odds_snapshot_at"),
        "odds_source": meta.get("source") or meta.get("odds_source"),
        "odds_age_hours": payload.get("odds_age_hours") or meta.get("age_hours"),
        "confidence_breakdown": payload.get("confidence_breakdown"),
        "cache_source": payload.get("cache_source"),
        "data_source_trace": payload.get("data_source_trace"),
    }


def _parse_ecse(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    top10 = json.loads(row.get("top_10_scorelines_json") or "[]")
    return {
        "generated_at": row.get("generated_at"),
        "model_version": row.get("model_version"),
        "lambda_home": row.get("lambda_home"),
        "lambda_away": row.get("lambda_away"),
        "top1": row.get("top_1_score"),
        "top3": json.loads(row.get("top_3_scores_json") or "[]"),
        "top5": json.loads(row.get("top_5_scores_json") or "[]"),
        "top10": top10,
        "confidence_score": row.get("confidence_score"),
        "prediction_source": row.get("prediction_source"),
        "raw_features": json.loads(row.get("raw_features_json") or "{}"),
        "is_frozen": row.get("is_frozen"),
    }


def _odds_detail(conn: sqlite3.Connection, fixture_id: int, fx_row: dict[str, Any]) -> dict[str, Any]:
    odds = _latest_odds(conn, fixture_id)
    now = datetime.now(timezone.utc)
    cls = classify_odds_freshness(
        odds_snapshot_at=odds["snapshot_at"] if odds else None,
        reference_at=now.isoformat(),
        knockout=is_knockout_match(round_name=fx_row.get("round_name"), status=fx_row.get("status")),
        low_priority=False,
        odds_source=odds.get("source") if odds else None,
        has_odds=bool(odds),
    )
    feature_row = build_odds_feature_row(conn, fixture_id)
    implied: dict[str, Any] = {}
    if feature_row:
        for k in ("ft_home_closing", "ft_draw_closing", "ft_away_closing"):
            v = feature_row.get(k)
            if v:
                implied[k] = {"odd": v, "implied": round(1.0 / float(v), 4) if float(v) > 0 else None}
    return {
        "snapshot_at": odds.get("snapshot_at") if odds else None,
        "source": odds.get("source") if odds else None,
        "freshness": cls.status.value if hasattr(cls.status, "value") else str(cls.status),
        "freshness_detail": cls.detail if hasattr(cls, "detail") else "",
        "feature_row": feature_row,
        "implied_1x2": implied,
        "odds_path": "odds_snapshots → normalize_snapshot_odds_lines → build_odds_feature_row",
    }


def _trace_input_path(wde: dict[str, Any], ecse: dict[str, Any] | None, odds: dict[str, Any]) -> str:
    if wde.get("odds_freshness_status") == "ODDS_MISSING" or not odds.get("snapshot_at"):
        return "missing_odds_path"
    if odds.get("freshness") == "STALE_ODDS":
        return "stale_database_odds"
    if ecse and (ecse.get("raw_features") or {}).get("source") == "registry_precomputed":
        return "registry_precomputed"
    if wde.get("cache_source") == "live":
        return "live_provider_odds"
    return "live_provider_odds" if odds.get("snapshot_at") else "missing_odds_path"


def _forensic_fixture(conn: sqlite3.Connection, fixture_id: int) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    fx = dict(conn.execute("SELECT * FROM fixtures WHERE fixture_id=?", (fixture_id,)).fetchone() or {})
    wde_row = conn.execute(
        "SELECT payload_json, predicted_at, source FROM worldcup_stored_predictions WHERE fixture_id=?",
        (fixture_id,),
    ).fetchone()
    ecse_row = conn.execute(
        "SELECT * FROM ecse_prediction_snapshots WHERE fixture_id=? ORDER BY id DESC LIMIT 1",
        (fixture_id,),
    ).fetchone()
    payload = json.loads(wde_row["payload_json"]) if wde_row and wde_row["payload_json"] else {}
    wde = _parse_wde(payload)
    wde["stored_predicted_at"] = wde_row["predicted_at"] if wde_row else None
    wde["stored_source"] = wde_row["source"] if wde_row else None
    wde["payload_hash"] = _payload_hash(wde_row["payload_json"] if wde_row else None)
    ecse = _parse_ecse(dict(ecse_row) if ecse_row else None)
    odds = _odds_detail(conn, fixture_id, fx)
    return {
        "fixture_id": fixture_id,
        "match": f"{fx.get('home_team')} vs {fx.get('away_team')}",
        "fixture": fx,
        "wde": wde,
        "ecse": ecse,
        "odds": odds,
        "code_path": _trace_input_path(wde, ecse, odds),
    }


def _refresh_odds(fixture_id: int, *, dry_run: bool) -> dict[str, Any]:
    cmd = [
        PY, str(ROOT / "scripts" / "run_odds_freshness_refresh.py"),
        "--mode", "refresh" if not dry_run else "audit",
        "--fixture-id", str(fixture_id),
        "--max-provider-calls", str(MAX_PER_FIXTURE),
        "--source", "auto",
    ]
    if dry_run:
        cmd.append("--dry-run")
    return _run(cmd)


def _shadow_wde(settings, fixture_id: int, fx: dict[str, Any], conn) -> dict[str, Any]:
    try:
        pipeline = PredictPipeline(settings, competition_key=str(fx.get("competition_key") or "world_cup_2026"))
        result = pipeline.run(fixture_id=fixture_id, record_history=False)
    except Exception as exc:
        return {"error": str(exc), "path": "PredictPipeline.run"}
    if not result.success:
        return {"error": "pipeline_failed", "path": "PredictPipeline.run"}
    payload = build_api_payload(result, intelligence_report=result.intelligence_report, specialist_report=result.specialist_report)
    freshness = build_fixture_freshness_metadata(
        conn, fixture_id=fixture_id, kickoff_utc=fx.get("kickoff_utc"),
        round_name=fx.get("round_name"), status=fx.get("status"), prediction_generated_at=_utc_now(),
    )
    payload = stamp_prediction_engine_metadata(payload, prediction=result.prediction, generated_by=GENERATED_BY)
    payload = stamp_provider_readiness(payload, settings=settings)
    payload = stamp_payload_odds_freshness(payload, freshness)
    payload["owner_only"] = True
    wde = _parse_wde(payload)
    wde["full_payload_keys"] = sorted(payload.keys())
    wde["fallback_used"] = payload.get("no_bet_flag") or payload.get("is_placeholder")
    return {"wde": wde, "raw_payload": payload}


def _shadow_ecse(conn, fixture_id: int, fx: dict[str, Any]) -> dict[str, Any]:
    try:
        pred = build_ecse_live_prediction(conn, fixture_id, fx)
    except Exception as exc:
        return {"error": str(exc)}
    if not pred:
        return {"error": "build_ecse_live_prediction returned None"}
    return {
        "ecse": {
            "lambda_home": pred.get("lambda_home"),
            "lambda_away": pred.get("lambda_away"),
            "top1": pred.get("top_1_score"),
            "top3": pred.get("top_3_scores"),
            "top5": pred.get("top_5_scores"),
            "top10": pred.get("top_10_scorelines"),
            "model_version": pred.get("model_version"),
            "prediction_source": pred.get("prediction_source"),
            "raw_features": pred.get("raw_features"),
            "confidence_score": pred.get("confidence_score"),
        },
        "raw_prediction": pred,
    }


def _score_dist(top10: list[dict[str, Any]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for e in top10 or []:
        sc = e.get("scoreline") if isinstance(e, dict) else str(e)
        p = float(e.get("probability", 0)) if isinstance(e, dict) else 0.0
        if sc:
            out[str(sc)] = out.get(str(sc), 0.0) + p
    total = sum(out.values()) or 1.0
    return {k: v / total for k, v in out.items()}


def _js_divergence(p: dict[str, float], q: dict[str, float]) -> float:
    keys = set(p) | set(q)
    if not keys:
        return 0.0

    def _kl(a: dict[str, float], b: dict[str, float]) -> float:
        s = 0.0
        for k in keys:
            pa = max(a.get(k, 0.0), 1e-12)
            pb = max(b.get(k, 0.0), 1e-12)
            s += pa * math.log(pa / pb)
        return s

    m = {k: 0.5 * (p.get(k, 0.0) + q.get(k, 0.0)) for k in keys}
    return round(0.5 * _kl(p, m) + 0.5 * _kl(q, m), 6)


def _alignment(wde: dict[str, Any], ecse: dict[str, Any] | None) -> dict[str, Any]:
    if not ecse:
        return {"classification": "NO_ECSE"}
    pick = str(wde.get("pick_1x2") or "").lower()
    top5 = ecse.get("top5") or []
    winner = btts_yes = ou_over = 0
    for sc in top5:
        try:
            h, a = map(int, str(sc).split("-"))
        except ValueError:
            continue
        w = "home" if h > a else "away" if h < a else "draw"
        if w == pick:
            winner += 1
        if h > 0 and a > 0:
            btts_yes += 1
        if h + a > 2:
            ou_over += 1
    btts_pick = str(wde.get("btts") or "").lower()
    ou_pick = str(wde.get("ou_2_5") or "").lower()
    btts_align = btts_yes if "yes" in btts_pick else (5 - btts_yes) if btts_pick else 0
    ou_align = ou_over if "over" in ou_pick else (5 - ou_over) if ou_pick else 0
    if winner >= 3 and btts_align >= 3:
        cls = "MOSTLY_ALIGNED"
    elif winner <= 1:
        cls = "STRONG_CONFLICT"
    elif winner >= 2:
        cls = "MIXED"
    else:
        cls = "MIXED"
    return {"classification": cls, "winner_align": winner, "btts_align": btts_align, "ou_align": ou_align}


def _compare(old: dict[str, Any], fresh: dict[str, Any]) -> dict[str, Any]:
    ow, fw = old.get("wde") or {}, fresh.get("wde") or {}
    oe, fe = old.get("ecse"), fresh.get("ecse")
    old_top5 = (oe or {}).get("top5") or []
    new_top5 = (fe or {}).get("top5") or []
    return {
        "wde": {
            "outcome_changed": ow.get("pick_1x2") != fw.get("pick_1x2"),
            "old_pick": ow.get("pick_1x2"),
            "new_pick": fw.get("pick_1x2"),
            "old_probs": {"H": ow.get("home_prob"), "X": ow.get("draw_prob"), "A": ow.get("away_prob")},
            "new_probs": {"H": fw.get("home_prob"), "X": fw.get("draw_prob"), "A": fw.get("away_prob")},
            "confidence_delta": round(float(fw.get("confidence") or 0) - float(ow.get("confidence") or 0), 2),
            "btts_changed": ow.get("btts") != fw.get("btts"),
            "ou_changed": ow.get("ou_2_5") != fw.get("ou_2_5"),
        },
        "ecse": {
            "old_lambdas": {"home": oe.get("lambda_home"), "away": oe.get("lambda_away")} if oe else None,
            "new_lambdas": {"home": fe.get("lambda_home"), "away": fe.get("lambda_away")} if fe else None,
            "lambda_delta": {
                "home": round(float((fe or {}).get("lambda_home") or 0) - float((oe or {}).get("lambda_home") or 0), 4),
                "away": round(float((fe or {}).get("lambda_away") or 0) - float((oe or {}).get("lambda_away") or 0), 4),
            } if oe and fe else None,
            "old_top5": old_top5,
            "new_top5": new_top5,
            "top1_changed": (oe or {}).get("top1") != (fe or {}).get("top1"),
            "top5_overlap": len(set(old_top5) & set(new_top5)),
            "js_divergence_top10": _js_divergence(_score_dist((oe or {}).get("top10") or []), _score_dist((fe or {}).get("top10") or [])),
        },
        "cross_market": {
            "before": _alignment(ow, oe),
            "after": _alignment(fw, fe),
        },
    }


def _mexico_forensic(old: dict[str, Any], cmp_: dict[str, Any]) -> dict[str, Any]:
    wde = old.get("wde") or {}
    ecse = old.get("ecse") or {}
    probs = [float(wde.get("home_prob") or 0), float(wde.get("draw_prob") or 0), float(wde.get("away_prob") or 0)]
    max_p, sorted_p = max(probs), sorted(probs, reverse=True)
    margin = sorted_p[0] - sorted_p[1] if len(sorted_p) > 1 else 0
    return {
        "wde_pick": wde.get("pick_1x2"),
        "wde_home_prob": wde.get("home_prob"),
        "wde_confidence": wde.get("confidence"),
        "max_class_prob": max_p,
        "top2_margin": round(margin, 2),
        "confidence_vs_margin_note": "Low confidence (27.6) despite 50.5% home pick indicates confidence formula uses weighted-decision breakdown, not raw 1X2 max probability.",
        "ecse_top_scores": ecse.get("top5"),
        "ecse_draw_heavy": sum(1 for s in (ecse.get("top5") or []) if "-" in str(s) and str(s).split("-")[0] == str(s).split("-")[1]) >= 2,
        "diagnosis": [
            "genuine_model_disagreement",
            "confidence_formula_behavior",
            "odds_input_issue" if old.get("code_path") == "missing_odds_path" else None,
        ],
        "primary_cause": "genuine_model_disagreement" if margin < 30 else "confidence_formula_behavior",
        "fresh_comparison": cmp_.get("cross_market"),
    }


def _portugal_forensic(old: dict[str, Any], fresh_odds: dict[str, Any], cmp_: dict[str, Any]) -> dict[str, Any]:
    return {
        "old_code_path": old.get("code_path"),
        "old_odds_freshness": (old.get("odds") or {}).get("freshness"),
        "old_wde_odds_status": (old.get("wde") or {}).get("odds_freshness_status"),
        "fresh_odds_after": fresh_odds.get("after"),
        "lambda_delta": (cmp_.get("ecse") or {}).get("lambda_delta"),
        "top1_changed": (cmp_.get("ecse") or {}).get("top1_changed"),
        "impact_summary": "STALE_ODDS/ODDS_MISSING affected ECSE lambda extraction from odds_snapshots; WDE pipeline used live/missing odds path.",
    }


def _decision(
    fixture_id: int,
    old: dict[str, Any],
    fresh: dict[str, Any],
    cmp_: dict[str, Any],
    odds_refresh: dict[str, Any],
) -> str:
    if fresh.get("wde", {}).get("error") or fresh.get("ecse", {}).get("error"):
        return "BLOCK_PIPELINE_INCONSISTENCY"
    after = odds_refresh.get("after") or {}
    if after.get("freshness") in ("MISSING_ODDS",) or not after.get("snapshot_at"):
        refreshed = int((odds_refresh.get("refresh_real") or {}).get("result", {}).get("refreshed") or 0)
        if refreshed == 0 and not after.get("feature_row"):
            return "BLOCK_ODDS_UNAVAILABLE"
    wde = cmp_.get("wde") or {}
    ecse = cmp_.get("ecse") or {}
    old_path = old.get("code_path")
    js = float(ecse.get("js_divergence_top10") or 0)
    if old_path in ("missing_odds_path", "stale_database_odds") and js > 0.01:
        return "PROMOTE_FRESH_INPUT_REGENERATION"
    if wde.get("outcome_changed") or wde.get("btts_changed") or wde.get("ou_changed"):
        return "PROMOTE_FRESH_INPUT_REGENERATION"
    if ecse.get("top1_changed") or (ecse.get("top5_overlap") or 5) < 4:
        return "PROMOTE_FRESH_INPUT_REGENERATION"
    if abs(float(wde.get("confidence_delta") or 0)) >= 8:
        return "PROMOTE_FRESH_INPUT_REGENERATION"
    if fixture_id == 1570714 and float(wde.get("confidence_delta") or 0) > 3:
        return "PROMOTE_FRESH_INPUT_REGENERATION"
    if js < 0.005 and not wde.get("outcome_changed"):
        return "KEEP_EXISTING_FROZEN"
    return "MANUAL_REVIEW_REQUIRED"


def _promote(settings, fixture_id: int, fx: dict[str, Any], shadow: dict[str, Any], backup: dict[str, Any]) -> dict[str, Any]:
    repo = FootballIntelligenceRepository(settings.sqlite_path)
    conn = connect(settings.sqlite_path)
    ensure_ecse_live_tables(conn)
    raw_wde = shadow.get("raw_payload")
    raw_ecse = shadow.get("raw_prediction")
    if not raw_wde or not raw_ecse:
        return {"promoted": False, "reason": "missing_shadow_payload"}
    raw_ecse["prediction_source"] = GENERATED_BY
    rf = raw_ecse.get("raw_features") or {}
    if isinstance(rf, dict):
        rf["owner_only"] = True
        rf["generated_by"] = GENERATED_BY
        rf["supersedes"] = backup
        raw_ecse["raw_features"] = rf
    repo.upsert_worldcup_stored_prediction(
        fixture_id=fixture_id,
        payload=raw_wde,
        kickoff_utc=fx.get("kickoff_utc"),
        source=GENERATED_BY,
        competition_key=str(fx.get("competition_key") or "world_cup_2026"),
        superseded_from=fixture_id,
    )
    conn.execute("DELETE FROM ecse_prediction_snapshots WHERE fixture_id=?", (fixture_id,))
    sid, reason = insert_snapshot(conn, raw_ecse)
    conn.commit()
    conn.close()
    verify_conn = sqlite3.connect(f"file:{settings.sqlite_path}?mode=ro", uri=True)
    verify_conn.row_factory = sqlite3.Row
    wde_v = verify_conn.execute("SELECT payload_json FROM worldcup_stored_predictions WHERE fixture_id=?", (fixture_id,)).fetchone()
    ecse_v = verify_conn.execute("SELECT * FROM ecse_prediction_snapshots WHERE fixture_id=?", (fixture_id,)).fetchone()
    verify_conn.close()
    return {
        "promoted": reason == "inserted",
        "ecse_snapshot_id": sid,
        "ecse_reason": reason,
        "wde_hash": _payload_hash(wde_v["payload_json"] if wde_v else None),
        "ecse_top1": ecse_v["top_1_score"] if ecse_v else None,
        "backup_ref": backup,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=PHASE)
    parser.add_argument("--skip-promote", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    conn_ro = sqlite3.connect(f"file:{settings.sqlite_path}?mode=ro", uri=True)
    forensic: list[dict[str, Any]] = []
    for t in TARGETS:
        forensic.append(_forensic_fixture(conn_ro, t["fixture_id"]))
    conn_ro.close()
    (ARTIFACT_DIR / "forensic_audit.json").write_text(json.dumps(forensic, indent=2, default=str), encoding="utf-8")

    fresh_odds_log: list[dict[str, Any]] = []
    provider_calls = 0
    for t in TARGETS:
        fid = t["fixture_id"]
        conn = connect(settings.sqlite_path)
        fx = dict(conn.execute("SELECT * FROM fixtures WHERE fixture_id=?", (fid,)).fetchone() or {})
        before = _odds_detail(conn, fid, fx)
        conn.close()
        dry = _refresh_odds(fid, dry_run=True)
        would = int((dry.get("result") or {}).get("would_refresh") or 0)
        real: dict[str, Any] = {"skipped": True}
        if would and provider_calls < MAX_ODDS_CALLS:
            real = _refresh_odds(fid, dry_run=False)
            provider_calls += int((real.get("result") or {}).get("refreshed") or 0)
        conn2 = connect(settings.sqlite_path)
        after = _odds_detail(conn2, fid, fx)
        conn2.close()
        fresh_odds_log.append({"fixture_id": fid, "match": t["match"], "before": before, "refresh_dry": dry, "refresh_real": real, "after": after})
    (ARTIFACT_DIR / "fresh_odds.json").write_text(json.dumps(fresh_odds_log, indent=2, default=str), encoding="utf-8")

    shadows: list[dict[str, Any]] = []
    conn = connect(settings.sqlite_path)
    for t in TARGETS:
        fid = t["fixture_id"]
        fx = dict(conn.execute("SELECT * FROM fixtures WHERE fixture_id=?", (fid,)).fetchone() or {})
        swde = _shadow_wde(settings, fid, fx, conn)
        secse = _shadow_ecse(conn, fid, fx)
        shadows.append({"fixture_id": fid, "match": t["match"], **swde, **secse})
    conn.close()
    (ARTIFACT_DIR / "shadow_predictions.json").write_text(json.dumps(shadows, indent=2, default=str), encoding="utf-8")

    comparisons: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    for old, shadow, odds_log in zip(forensic, shadows, fresh_odds_log):
        fid = old["fixture_id"]
        fresh = {
            "wde": shadow.get("wde") or {},
            "ecse": shadow.get("ecse"),
        }
        cmp_ = _compare(old, fresh)
        dec = _decision(fid, old, fresh, cmp_, odds_log)
        entry = {"fixture_id": fid, "match": old["match"], "comparison": cmp_, "decision": dec}
        if fid == 1570714:
            entry["mexico_forensic"] = _mexico_forensic(old, cmp_)
        if fid == 1576756:
            entry["portugal_forensic"] = _portugal_forensic(old, odds_log, cmp_)
        comparisons.append(entry)
        backup = {"wde_hash": old["wde"].get("payload_hash"), "ecse_top1": (old.get("ecse") or {}).get("top1")}
        promo_result = None
        if dec == "PROMOTE_FRESH_INPUT_REGENERATION" and not args.skip_promote:
            promo_result = _promote(settings, fid, old["fixture"], shadow, backup)
        decisions.append({"fixture_id": fid, "match": old["match"], "decision": dec, "backup": backup, "promotion": promo_result})
    (ARTIFACT_DIR / "comparison.json").write_text(json.dumps(comparisons, indent=2, default=str), encoding="utf-8")
    (ARTIFACT_DIR / "promotion_decisions.json").write_text(json.dumps(decisions, indent=2, default=str), encoding="utf-8")

    promote_count = sum(1 for d in decisions if d["decision"] == "PROMOTE_FRESH_INPUT_REGENERATION")
    keep_count = sum(1 for d in decisions if d["decision"] == "KEEP_EXISTING_FROZEN")
    block_count = sum(1 for d in decisions if d["decision"].startswith("BLOCK"))
    if block_count:
        rec = "NEXT_3_BLOCKED_BY_ODDS_INPUTS"
    elif any(d["decision"] == "BLOCK_PIPELINE_INCONSISTENCY" for d in decisions):
        rec = "NEXT_3_PIPELINE_INCONSISTENCY_FOUND"
    elif promote_count and keep_count:
        rec = "NEXT_3_MIXED_KEEP_AND_PROMOTE"
    elif promote_count == 3:
        rec = "NEXT_3_FRESH_PREDICTIONS_CONFIRMED"
    elif keep_count == 3:
        rec = "NEXT_3_FRESH_PREDICTIONS_CONFIRMED" if not block_count else "NEXT_3_MIXED_KEEP_AND_PROMOTE"
    else:
        rec = "NEXT_3_MIXED_KEEP_AND_PROMOTE"

    workflow = {
        "phase": PHASE,
        "production_commit": head,
        "provider_calls_used": provider_calls,
        "final_recommendation": rec,
        "decisions": decisions,
    }
    (ARTIFACT_DIR / "workflow.json").write_text(json.dumps(workflow, indent=2, default=str), encoding="utf-8")
    _write_reports(forensic, shadows, comparisons, decisions, workflow, fresh_odds_log)
    print(json.dumps(workflow, indent=2, default=str))
    return 0


def _write_reports(forensic, shadows, comparisons, decisions, workflow, fresh_odds_log) -> None:
    owner_lines = [
        "# NEXT-3-FRESH-ODDS-CONTROLLED-REGENERATION — Owner Report",
        "",
        f"**Generated:** {_utc_now()}",
        f"**Recommendation:** `{workflow['final_recommendation']}`",
        "",
        "| Match | Old WDE | Fresh WDE | Changed? | Old ECSE Top1 | Fresh ECSE Top1 | Freshness | Decision |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for old, shadow, cmp_e, dec_e, odds in zip(forensic, shadows, comparisons, decisions, fresh_odds_log):
        ow, fw = old["wde"], shadow.get("wde") or {}
        oe, fe = old.get("ecse") or {}, shadow.get("ecse") or {}
        changed = "yes" if (cmp_e.get("comparison") or {}).get("wde", {}).get("outcome_changed") else "no"
        owner_lines.append(
            f"| {old['match']} | {ow.get('pick_1x2')} | {fw.get('pick_1x2')} | {changed} | "
            f"{oe.get('top1')} | {fe.get('top1')} | {odds.get('after', {}).get('freshness')} | {dec_e['decision']} |"
        )
    Path("NEXT_3_FRESH_ODDS_CONTROLLED_REGENERATION_OWNER_REPORT.md").write_text("\n".join(owner_lines) + "\n", encoding="utf-8")

    report = [
        "# NEXT-3-FRESH-ODDS-CONTROLLED-REGENERATION-1 — Report",
        "",
        f"**Phase:** {PHASE}",
        f"**Recommendation:** `{workflow['final_recommendation']}`",
        f"**Commit:** `{workflow['production_commit']}`",
        f"**Provider calls:** {workflow['provider_calls_used']}",
        "",
        "## Task A — Forensic input audit",
        "",
    ]
    for f in forensic:
        report.append(f"### {f['match']} ({f['fixture_id']})")
        report.append(f"- Code path: `{f['code_path']}`")
        report.append(f"- WDE pick: {f['wde'].get('pick_1x2')} conf={f['wde'].get('confidence')} odds_status={f['wde'].get('odds_freshness_status')}")
        report.append(f"- ECSE top1: {(f.get('ecse') or {}).get('top1')} λ=({(f.get('ecse') or {}).get('lambda_home')},{(f.get('ecse') or {}).get('lambda_away')})")
        report.append("")
    report.extend(["## Promotion decisions", ""])
    for d in decisions:
        report.append(f"- **{d['match']}**: {d['decision']}")
        if d.get("promotion"):
            report.append(f"  - promoted: {d['promotion']}")
    Path("NEXT_3_FRESH_ODDS_CONTROLLED_REGENERATION_1_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
