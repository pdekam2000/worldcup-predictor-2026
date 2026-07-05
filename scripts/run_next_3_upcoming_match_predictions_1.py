#!/usr/bin/env python3
"""NEXT-3-UPCOMING-MATCH-PREDICTIONS-1 — Controlled WDE + ECSE Top5 for next 3 WC fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if not os.environ.get("APP_ENV") and (ROOT / ".env.production").is_file():
    os.environ.setdefault("APP_ENV", "production")

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository

PHASE = "NEXT-3-UPCOMING-MATCH-PREDICTIONS-1"
ARTIFACT_DIR = ROOT / "artifacts" / "next_3_upcoming_match_predictions_1"
WORKFLOW_JSON = ARTIFACT_DIR / "workflow.json"
BASELINE_MD = ROOT / "NEXT_3_UPCOMING_MATCHES_BASELINE.md"
OWNER_MD = ROOT / "NEXT_3_UPCOMING_MATCH_PREDICTIONS_OWNER_REPORT.md"
REPORT_MD = ROOT / "NEXT_3_UPCOMING_MATCH_PREDICTIONS_1_REPORT.md"

MAX_FIXTURES = 3
MAX_ODDS_CALLS = 60
MAX_ODDS_PER_FIXTURE = 20
MAX_PREDICT_ODDS_CALLS = 20
NOT_STARTED = {"NS", "TBD", "SCHEDULED", "TIMED", "NOT_STARTED", "NOT STARTED"}
LIVE = {"1H", "2H", "HT", "ET", "P", "LIVE", "BT", "INT"}
FINISHED = {"FT", "AET", "PEN", "AWD", "WO", "CANC", "ABD", "PST"}
PY = str(ROOT / ".venv" / "bin" / "python")
if sys.platform == "win32":
    PY = sys.executable


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _vienna(kickoff_utc: str | None) -> str:
    if not kickoff_utc:
        return ""
    try:
        dt = datetime.fromisoformat(str(kickoff_utc).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo("Europe/Vienna")).strftime("%Y-%m-%d %H:%M %Z")
    except (ValueError, TypeError):
        return str(kickoff_utc)


def _run(cmd: list[str]) -> dict[str, Any]:
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=900)
    out = proc.stdout.strip()
    payload: Any = None
    if out:
        try:
            payload = json.loads(out)
        except json.JSONDecodeError:
            payload = {"raw_stdout": out[-12000:]}
    return {
        "cmd": " ".join(cmd),
        "exit_code": proc.returncode,
        "stderr_tail": (proc.stderr or "")[-3000:],
        "result": payload,
    }


def _discover_next_fixtures(limit: int = MAX_FIXTURES) -> list[dict[str, Any]]:
    settings = get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path)
    candidates = repo.list_upcoming_fixtures("world_cup_2026", season=2026, limit=50)
    selected: list[dict[str, Any]] = []
    for fx in candidates:
        status = str(fx.get("status") or "").upper()
        if status in LIVE or status in FINISHED:
            continue
        if status not in NOT_STARTED:
            continue
        selected.append(fx)
        if len(selected) >= limit:
            break
    return selected


def _prediction_state(conn: sqlite3.Connection, fixture_id: int) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    wde = conn.execute(
        "SELECT payload_json, predicted_at FROM worldcup_stored_predictions WHERE fixture_id=?",
        (fixture_id,),
    ).fetchone()
    ecse = conn.execute(
        "SELECT * FROM ecse_prediction_snapshots WHERE fixture_id=? ORDER BY id DESC LIMIT 1",
        (fixture_id,),
    ).fetchone()
    wde_hash = ""
    if wde and wde["payload_json"]:
        wde_hash = hashlib.sha256(wde["payload_json"].encode("utf-8")).hexdigest()[:16]
    state = "NONE"
    if wde and ecse:
        state = "EXISTING_FROZEN_PREDICTION_REUSED"
    elif wde or ecse:
        state = "PARTIAL_PREDICTION_STATE"
    return {
        "has_wde": wde is not None,
        "has_ecse": ecse is not None,
        "wde_predicted_at": wde["predicted_at"] if wde else None,
        "ecse_generated_at": ecse["generated_at"] if ecse else None,
        "ecse_frozen": bool(ecse and ecse["is_frozen"]) if ecse else False,
        "payload_hash": wde_hash,
        "state": state,
        "needs_generation": not (wde and ecse),
    }


def _odds_step(fixture_id: int, mode: str, *, dry_run: bool = False, max_calls: int = 0) -> dict[str, Any]:
    cmd = [
        PY,
        str(ROOT / "scripts" / "run_odds_freshness_refresh.py"),
        "--mode",
        mode,
        "--fixture-id",
        str(fixture_id),
        "--max-provider-calls",
        str(max_calls),
        "--source",
        "auto",
    ]
    if dry_run or mode == "audit":
        cmd.append("--dry-run")
    return _run(cmd)


def _predict(fixture_id: int, *, dry_run: bool) -> dict[str, Any]:
    cmd = [
        PY,
        str(ROOT / "scripts" / "run_production_prediction_pipeline.py"),
        "--mode",
        "predictions-only",
        "--fixture-id",
        str(fixture_id),
        "--refresh-stale-odds",
        "--max-odds-provider-calls",
        str(MAX_PREDICT_ODDS_CALLS),
    ]
    if dry_run:
        cmd.append("--dry-run")
    return _run(cmd)


def _classify_odds(audit_result: dict[str, Any] | None) -> str:
    if not audit_result or audit_result.get("exit_code") != 0:
        return "UNKNOWN_ODDS"
    payload = audit_result.get("result") or {}
    fixtures = payload.get("fixtures") or payload.get("fixture_results") or []
    if isinstance(payload, dict) and payload.get("fixtures_scanned") == 0:
        return "MISSING_ODDS"
    for row in fixtures if isinstance(fixtures, list) else []:
        status = str(row.get("freshness_status") or row.get("status") or "").upper()
        if status in ("FRESH", "FRESH_ODDS"):
            return "FRESH_ODDS"
        if status in ("STALE", "STALE_ODDS"):
            return "STALE_ODDS"
    refreshed = (payload.get("refreshed") or 0) if isinstance(payload, dict) else 0
    would = (payload.get("would_refresh") or 0) if isinstance(payload, dict) else 0
    if refreshed or would:
        return "STALE_ODDS"
    return "FRESH_ODDS"


def _inspect_fixture(conn: sqlite3.Connection, fx: dict[str, Any]) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    fid = int(fx["fixture_id"])
    wde = conn.execute(
        "SELECT payload_json, predicted_at FROM worldcup_stored_predictions WHERE fixture_id=?",
        (fid,),
    ).fetchone()
    ecse = conn.execute(
        "SELECT * FROM ecse_prediction_snapshots WHERE fixture_id=? ORDER BY id DESC LIMIT 1",
        (fid,),
    ).fetchone()
    payload: dict[str, Any] = {}
    if wde and wde["payload_json"]:
        payload = json.loads(wde["payload_json"])
    probs = payload.get("probabilities") or {}
    h = probs.get("home_win") or probs.get("home")
    x = probs.get("draw")
    a = probs.get("away_win") or probs.get("away")
    btts = probs.get("btts") or payload.get("detailed_markets", {}).get("btts") or {}
    ou = probs.get("over_under_2_5") or payload.get("detailed_markets", {}).get("over_under_25") or {}
    top3 = top5 = []
    if ecse:
        top3 = json.loads(ecse["top_3_scores_json"] or "[]")
        top5 = json.loads(ecse["top_5_scores_json"] or "[]")
    phash = ""
    if wde and wde["payload_json"]:
        phash = hashlib.sha256(wde["payload_json"].encode("utf-8")).hexdigest()[:16]
    return {
        "fixture_id": fid,
        "match": f"{fx.get('home_team')} vs {fx.get('away_team')}",
        "home_team": fx.get("home_team"),
        "away_team": fx.get("away_team"),
        "kickoff_utc": fx.get("kickoff_utc"),
        "kickoff_vienna": _vienna(fx.get("kickoff_utc")),
        "stage": fx.get("round_name"),
        "round": fx.get("round_name"),
        "status": fx.get("status"),
        "wde": {
            "pick_1x2": payload.get("prediction"),
            "home_prob": h,
            "draw_prob": x,
            "away_prob": a,
            "confidence": payload.get("confidence"),
            "btts": btts.get("selection") or btts.get("display") or btts.get("pick"),
            "ou_2_5": ou.get("selection") or ou.get("display") or ou.get("pick"),
            "predicted_at": wde["predicted_at"] if wde else None,
            "payload_hash": phash,
            "engine_version": payload.get("prediction_engine_version"),
            "odds_freshness_status": payload.get("odds_freshness_status"),
            "odds_snapshot_at": payload.get("odds_snapshot_at"),
            "odds_source": (payload.get("odds_freshness_metadata") or {}).get("source"),
        },
        "ecse": {
            "top1": ecse["top_1_score"] if ecse else None,
            "top3": top3,
            "top5": top5,
            "generated_at": ecse["generated_at"] if ecse else None,
            "model_version": ecse["model_version"] if ecse else None,
            "is_frozen": ecse["is_frozen"] if ecse else None,
        },
    }


def _top5_integrity(ecse: dict[str, Any]) -> dict[str, Any]:
    top1 = ecse.get("top1")
    top3 = list(ecse.get("top3") or [])
    top5 = list(ecse.get("top5") or [])
    issues: list[str] = []
    if len(top5) != 5:
        issues.append(f"top5_count={len(top5)}")
    if len(set(top5)) != len(top5):
        issues.append("duplicate_scores_in_top5")
    if top3 and set(top3) - set(top5):
        issues.append("top3_not_subset_of_top5")
    if top1 and top5 and top5[0] != top1:
        issues.append("top1_mismatch_rank1")
    if len(top3) != 3:
        issues.append(f"top3_count={len(top3)}")
    return {"ok": not issues, "issues": issues}


def _cross_market_review(wde: dict[str, Any], ecse: dict[str, Any]) -> dict[str, Any]:
    top5 = ecse.get("top5") or []
    pick = str(wde.get("pick_1x2") or "").lower()
    btts_pick = str(wde.get("btts") or "").lower()
    ou_pick = str(wde.get("ou_2_5") or "").lower()

    def _parse_score(s: str) -> tuple[int, int] | None:
        try:
            h, a = s.split("-")
            return int(h), int(a)
        except (ValueError, AttributeError):
            return None

    winner_align = draw_count = btts_yes = ou_over = 0
    clean_sheet = tail_3plus = 0
    for sc in top5:
        parsed = _parse_score(sc)
        if not parsed:
            continue
        hg, ag = parsed
        if hg > ag:
            winner = "home"
        elif hg < ag:
            winner = "away"
        else:
            winner = "draw"
            draw_count += 1
        if pick and winner == pick:
            winner_align += 1
        if hg > 0 and ag > 0:
            btts_yes += 1
        if hg + ag > 2:
            ou_over += 1
        if hg == 0 or ag == 0:
            clean_sheet += 1
        if hg + ag >= 3:
            tail_3plus += 1

    btts_align = btts_yes if "yes" in btts_pick else (5 - btts_yes) if btts_pick else 0
    ou_align = ou_over if "over" in ou_pick else (5 - ou_over) if ou_pick else 0

    if winner_align >= 4 and btts_align >= 4 and ou_align >= 4:
        classification = "FULLY_ALIGNED"
    elif winner_align >= 3 and (btts_align >= 3 or ou_align >= 3):
        classification = "MOSTLY_ALIGNED"
    elif winner_align <= 1 and btts_align <= 1:
        classification = "STRONG_CONFLICT"
    else:
        classification = "MIXED"

    return {
        "classification": classification,
        "winner_direction_alignment_count": winner_align,
        "btts_alignment_count": btts_align,
        "ou_alignment_count": ou_align,
        "draw_coverage_in_top5": draw_count,
        "clean_sheet_coverage": clean_sheet,
        "three_plus_goal_tail_coverage": tail_3plus,
    }


def _render_baseline(fixtures: list[dict[str, Any]], states: list[dict[str, Any]]) -> str:
    lines = [
        "# NEXT-3-UPCOMING-MATCH-PREDICTIONS-1 — Baseline",
        "",
        f"**Generated:** {_utc_now_iso()} UTC",
        "",
        "| # | Fixture ID | Match | Kickoff UTC | Kickoff Vienna | Stage | Round | Status | WDE | ECSE | State |",
        "|---|------------|-------|-------------|----------------|-------|-------|--------|-----|------|-------|",
    ]
    for i, (fx, st) in enumerate(zip(fixtures, states), 1):
        lines.append(
            f"| {i} | {fx['fixture_id']} | {fx.get('home_team')} vs {fx.get('away_team')} | "
            f"{fx.get('kickoff_utc')} | {_vienna(fx.get('kickoff_utc'))} | {fx.get('stage') or ''} | "
            f"{fx.get('round_name') or ''} | {fx.get('status')} | "
            f"{'yes' if st['has_wde'] else 'no'} | {'yes' if st['has_ecse'] else 'no'} | {st['state']} |"
        )
    lines.append("")
    return "\n".join(lines)


def _render_owner(matches: list[dict[str, Any]]) -> str:
    lines = [
        "# NEXT-3-UPCOMING-MATCH-PREDICTIONS — Owner Report",
        "",
        f"**Generated:** {_utc_now_iso()} UTC",
        "",
        "## Summary",
        "",
        "| Match | 1X2 | Confidence | BTTS | O/U | Top5 | Odds |",
        "| ----- | --- | ---------: | ---- | --- | ---- | ---- |",
    ]
    for m in matches:
        wde = m["wde"]
        ecse = m["ecse"]
        top5_str = " / ".join(ecse.get("top5") or [])
        lines.append(
            f"| {m['match']} | {wde.get('pick_1x2')} | {wde.get('confidence')} | "
            f"{wde.get('btts')} | {wde.get('ou_2_5')} | {top5_str} | {m.get('odds_status')} |"
        )
    lines.append("")

    for idx, m in enumerate(matches, 1):
        wde = m["wde"]
        ecse = m["ecse"]
        cm = m.get("cross_market") or {}
        lines.extend([
            f"## MATCH {idx}",
            f"**{m['match']}**",
            f"Kickoff Vienna: {m['kickoff_vienna']}",
            f"Fixture ID: {m['fixture_id']}",
            "",
            "**WDE:**",
            f"- 1X2: {wde.get('pick_1x2')}",
            f"- H: {wde.get('home_prob')}",
            f"- X: {wde.get('draw_prob')}",
            f"- A: {wde.get('away_prob')}",
            f"- Confidence: {wde.get('confidence')}",
            f"- BTTS: {wde.get('btts')}",
            f"- O/U: {wde.get('ou_2_5')}",
            "",
            "**ECSE TOP 5:**",
        ])
        for rank, sc in enumerate(ecse.get("top5") or [], 1):
            lines.append(f"{rank}. {sc}")
        lines.extend([
            "",
            f"**Odds:** {m.get('odds_status')}",
            f"- Source: {wde.get('odds_source') or 'n/a'}",
            f"- Snapshot: {wde.get('odds_snapshot_at') or 'n/a'}",
            "",
            f"**Consistency:** {cm.get('classification', 'n/a')}",
            "",
            f"**Status:** {m.get('match_status', 'FROZEN_PENDING_EVALUATION')}",
            "",
        ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=PHASE)
    parser.add_argument("--dry-run-only", action="store_true", help="Discovery + odds audit only, no writes")
    args = parser.parse_args()

    settings = get_settings()
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()

    workflow: dict[str, Any] = {
        "phase": PHASE,
        "started_at_utc": _utc_now_iso(),
        "production_commit": head,
        "provider_calls_used": 0,
        "fixtures": [],
        "final_recommendation": None,
    }

    fixtures = _discover_next_fixtures(MAX_FIXTURES)
    if len(fixtures) < MAX_FIXTURES:
        workflow["final_recommendation"] = "UPCOMING_FIXTURE_DISCOVERY_FAILED"
        workflow["error"] = f"Only {len(fixtures)} upcoming fixtures found"
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        WORKFLOW_JSON.write_text(json.dumps(workflow, indent=2, default=str), encoding="utf-8")
        BASELINE_MD.write_text(_render_baseline(fixtures, []), encoding="utf-8")
        print(json.dumps(workflow, indent=2))
        return 1

    conn = sqlite3.connect(f"file:{settings.sqlite_path}?mode=ro", uri=True)
    states = [_prediction_state(conn, int(fx["fixture_id"])) for fx in fixtures]
    conn.close()
    BASELINE_MD.write_text(_render_baseline(fixtures, states), encoding="utf-8")

    provider_calls = 0
    matches_out: list[dict[str, Any]] = []

    for fx, pred_state in zip(fixtures, states):
        fid = int(fx["fixture_id"])
        fx_work: dict[str, Any] = {
            "fixture_id": fid,
            "match": f"{fx.get('home_team')} vs {fx.get('away_team')}",
            "prediction_state": pred_state,
            "odds": {},
            "prediction": {},
        }

        audit_before = _odds_step(fid, "audit", max_calls=0)
        fx_work["odds"]["audit_before"] = audit_before
        odds_before = _classify_odds(audit_before)

        if pred_state["needs_generation"] and not args.dry_run_only:
            refresh_dry = _odds_step(fid, "refresh", dry_run=True, max_calls=MAX_ODDS_PER_FIXTURE)
            fx_work["odds"]["refresh_dry_run"] = refresh_dry
            would = 0
            if isinstance(refresh_dry.get("result"), dict):
                would = int(refresh_dry["result"].get("would_refresh") or 0)
            if would and refresh_dry["exit_code"] == 0 and provider_calls < MAX_ODDS_CALLS:
                calls = min(MAX_ODDS_PER_FIXTURE, MAX_ODDS_CALLS - provider_calls)
                real = _odds_step(fid, "refresh", max_calls=calls)
                fx_work["odds"]["refresh_real"] = real
                if isinstance(real.get("result"), dict):
                    provider_calls += int(real["result"].get("refreshed") or 0)
            else:
                fx_work["odds"]["refresh_real"] = {"skipped": True, "reason": "would_refresh=0 or cap reached"}

            audit_after = _odds_step(fid, "audit", max_calls=0)
            fx_work["odds"]["audit_after"] = audit_after
            odds_status = _classify_odds(audit_after)
        else:
            fx_work["odds"]["refresh_skipped"] = pred_state["state"]
            odds_status = odds_before

        fx_work["odds"]["before_status"] = odds_before
        fx_work["odds"]["after_status"] = odds_status

        if pred_state["state"] == "EXISTING_FROZEN_PREDICTION_REUSED":
            fx_work["prediction"]["action"] = "EXISTING_FROZEN_PREDICTION_REUSED"
        elif pred_state["state"] == "PARTIAL_PREDICTION_STATE":
            fx_work["prediction"]["action"] = "PARTIAL_PREDICTION_STATE"
            if not args.dry_run_only:
                dry = _predict(fid, dry_run=True)
                fx_work["prediction"]["dry_run"] = dry
                if dry["exit_code"] == 0:
                    real = _predict(fid, dry_run=False)
                    fx_work["prediction"]["real"] = real
                    if real["exit_code"] != 0:
                        fx_work["prediction"]["error"] = "PREDICTION_RUN_FAILED"
        elif not args.dry_run_only:
            dry = _predict(fid, dry_run=True)
            fx_work["prediction"]["dry_run"] = dry
            if dry["exit_code"] != 0:
                fx_work["prediction"]["error"] = "PREDICTION_DRY_RUN_UNSAFE"
            else:
                real = _predict(fid, dry_run=False)
                fx_work["prediction"]["real"] = real
                if real["exit_code"] != 0:
                    fx_work["prediction"]["error"] = "PREDICTION_RUN_FAILED"
        else:
            fx_work["prediction"]["action"] = "dry_run_only_mode"

        conn = sqlite3.connect(f"file:{settings.sqlite_path}?mode=ro", uri=True)
        inspected = _inspect_fixture(conn, fx)
        conn.close()
        inspected["odds_status"] = odds_status
        inspected["cross_market"] = _cross_market_review(inspected["wde"], inspected["ecse"])
        inspected["top5_integrity"] = _top5_integrity(inspected["ecse"])
        inspected["match_status"] = (
            "EXISTING_FROZEN_PREDICTION_REUSED"
            if pred_state["state"] == "EXISTING_FROZEN_PREDICTION_REUSED"
            else "FROZEN_PENDING_EVALUATION"
        )
        fx_work["stored"] = inspected
        matches_out.append(inspected)
        workflow["fixtures"].append(fx_work)

    workflow["provider_calls_used"] = provider_calls
    workflow["matches"] = matches_out

    all_complete = all(
        m["wde"].get("pick_1x2") and len(m["ecse"].get("top5") or []) == 5 for m in matches_out
    )
    all_reused = all(f["prediction_state"]["state"] == "EXISTING_FROZEN_PREDICTION_REUSED" for f in workflow["fixtures"])
    any_odds_warn = any(m.get("odds_status") in ("STALE_ODDS", "UNKNOWN_ODDS", "MISSING_ODDS") for m in matches_out)
    any_fail = any(f.get("prediction", {}).get("error") for f in workflow["fixtures"])

    if any_fail and not all_complete:
        workflow["final_recommendation"] = "PREDICTION_RUN_FAILED"
    elif not all_complete:
        workflow["final_recommendation"] = "PARTIAL_PREDICTION_SUCCESS"
    elif all_reused:
        workflow["final_recommendation"] = "NEXT_3_EXISTING_PREDICTIONS_REUSED"
    elif any_odds_warn:
        workflow["final_recommendation"] = "NEXT_3_PREDICTIONS_COMPLETE_WITH_ODDS_WARNINGS"
    else:
        workflow["final_recommendation"] = "NEXT_3_PREDICTIONS_FROZEN"

    OWNER_MD.write_text(_render_owner(matches_out), encoding="utf-8")
    REPORT_MD.write_text(_render_final_report(workflow, matches_out, head), encoding="utf-8")

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    WORKFLOW_JSON.write_text(json.dumps(workflow, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"final_recommendation": workflow["final_recommendation"], "matches": matches_out}, indent=2, default=str))
    return 0 if all_complete and not any_fail else 1


def _render_final_report(workflow: dict[str, Any], matches: list[dict[str, Any]], head: str) -> str:
    lines = [
        "# NEXT-3-UPCOMING-MATCH-PREDICTIONS-1 — Final Report",
        "",
        f"**Phase:** {PHASE}",
        f"**Final recommendation:** `{workflow.get('final_recommendation')}`",
        f"**Production commit:** `{head}`",
        f"**Provider calls used:** {workflow.get('provider_calls_used', 0)}",
        "",
        "## Discovered fixtures (chronological)",
        "",
    ]
    for i, m in enumerate(matches, 1):
        lines.append(
            f"{i}. **{m['match']}** — fixture `{m['fixture_id']}` — kickoff Vienna `{m['kickoff_vienna']}` — status `{m['status']}`"
        )
    lines.extend(["", "## WDE / ECSE outputs", ""])
    for m in matches:
        wde, ecse = m["wde"], m["ecse"]
        lines.append(f"### {m['match']}")
        lines.append(f"- WDE 1X2: {wde.get('pick_1x2')} (H={wde.get('home_prob')} X={wde.get('draw_prob')} A={wde.get('away_prob')})")
        lines.append(f"- BTTS: {wde.get('btts')} | O/U: {wde.get('ou_2_5')} | Confidence: {wde.get('confidence')}")
        lines.append(f"- ECSE Top1: {ecse.get('top1')}")
        lines.append(f"- ECSE Top3: {' / '.join(ecse.get('top3') or [])}")
        lines.append(f"- ECSE Top5: {' / '.join(ecse.get('top5') or [])}")
        lines.append(f"- Payload hash: {wde.get('payload_hash')}")
        lines.append(f"- Cross-market: {(m.get('cross_market') or {}).get('classification')}")
        lines.append("")
    lines.extend([
        f"**Owner report:** `{OWNER_MD.name}`",
        f"**Baseline:** `{BASELINE_MD.name}`",
        f"**Workflow artifact:** `{WORKFLOW_JSON}`",
        "",
    ])
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
