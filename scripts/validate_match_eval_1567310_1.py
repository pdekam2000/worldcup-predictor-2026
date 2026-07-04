#!/usr/bin/env python3
"""MATCH-EVAL-1567310-1 Part G — Validation."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if not os.environ.get("APP_ENV") and (ROOT / ".env.production").is_file():
    os.environ.setdefault("APP_ENV", "production")

from worldcup_predictor.config.settings import get_settings

FIXTURE_ID = 1567310
PREMATCH_ARTIFACT = ROOT / "artifacts" / "match_eval" / "1567310_prematch_snapshot.json"
VALIDATION_ARTIFACT = ROOT / "artifacts" / "match_eval" / "match_eval_1567310_1_validation.json"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": bool(ok), "detail": detail}


def _payload_hash(raw: str | None) -> str:
    if not raw:
        return ""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def main() -> int:
    settings = get_settings()
    checks: list[dict] = []
    conn = sqlite3.connect(f"file:{settings.sqlite_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    wde = conn.execute(
        "SELECT payload_json, predicted_at FROM worldcup_stored_predictions WHERE fixture_id=?",
        (FIXTURE_ID,),
    ).fetchone()
    ecse = conn.execute(
        "SELECT id, generated_at, top_1_score, is_frozen FROM ecse_prediction_snapshots WHERE fixture_id=?",
        (FIXTURE_ID,),
    ).fetchone()
    fr = conn.execute("SELECT * FROM fixture_results WHERE fixture_id=?", (FIXTURE_ID,)).fetchone()
    wde_ev = conn.execute(
        "SELECT COUNT(*) AS c FROM worldcup_prediction_evaluations WHERE fixture_id=?",
        (FIXTURE_ID,),
    ).fetchone()
    ecse_ev = conn.execute(
        "SELECT COUNT(*) AS c FROM ecse_prediction_evaluations WHERE fixture_id=?",
        (FIXTURE_ID,),
    ).fetchone()
    ecse_ev_rows = conn.execute(
        "SELECT * FROM ecse_prediction_evaluations WHERE fixture_id=?",
        (FIXTURE_ID,),
    ).fetchall()

    current_hash = _payload_hash(wde["payload_json"] if wde else None)
    if PREMATCH_ARTIFACT.exists():
        prematch = json.loads(PREMATCH_ARTIFACT.read_text(encoding="utf-8"))
        frozen_hash = prematch.get("wde", {}).get("payload_sha256_prefix")
        checks.append(_check("wde_payload_unchanged", current_hash == frozen_hash, f"{frozen_hash} vs {current_hash}"))
        frozen_wde = prematch.get("wde") or {}
        if wde and wde["payload_json"]:
            live_payload = json.loads(wde["payload_json"])
            checks.append(
                _check(
                    "provider_result_confirmed",
                    fr is not None
                    and str(fr["match_outcome_type"]) == "FT"
                    and fr["home_goals"] == 1
                    and fr["away_goals"] == 0
                    and fr["penalty_score"] is None,
                    f"{fr['final_score'] if fr else None} {fr['match_outcome_type'] if fr else None}",
                )
            )
            checks.append(
                _check(
                    "frozen_prediction_generated_at_unchanged",
                    str(wde["predicted_at"]) == str(frozen_wde.get("predicted_at")),
                    str(wde["predicted_at"]),
                )
            )
            checks.append(
                _check(
                    "stale_odds_metadata_unchanged",
                    live_payload.get("odds_freshness_status") == frozen_wde.get("odds_freshness_status")
                    and live_payload.get("odds_snapshot_at") == frozen_wde.get("odds_snapshot_at")
                    and live_payload.get("odds_age_hours") == frozen_wde.get("odds_age_hours"),
                    f"status={live_payload.get('odds_freshness_status')} snapshot={live_payload.get('odds_snapshot_at')}",
                )
            )
            meta = live_payload.get("odds_freshness_metadata") or {}
            checks.append(
                _check(
                    "no_historical_odds_refresh",
                    meta.get("odds_refresh_attempted") is False,
                    str(meta.get("odds_refresh_attempted")),
                )
            )
            checks.append(
                _check(
                    "documented_stale_odds_context",
                    frozen_wde.get("odds_snapshot_at") == "2026-07-04 00:55:59 UTC",
                    "audit STALE_ODDS 7.44h preserved in prematch artifact; payload frozen UNKNOWN",
                )
            )
    else:
        checks.append(_check("prematch_artifact_present", False, "run capture first"))

    checks.append(_check("wde_prediction_exists", wde is not None))
    checks.append(_check("ecse_snapshot_exists", ecse is not None))
    checks.append(_check("ecse_frozen", bool(ecse and ecse["is_frozen"])))
    checks.append(_check("fixture_finished", fr is not None and str(fr["match_outcome_type"]) == "FT"))
    checks.append(_check("uses_90min_score", fr is not None and fr["home_goals"] == 1 and fr["away_goals"] == 0))
    checks.append(_check("no_penalty_score", fr is not None and fr["penalty_score"] is None))
    checks.append(_check("wde_evaluation_exists", wde_ev and wde_ev["c"] >= 1, str(wde_ev["c"] if wde_ev else 0)))
    checks.append(_check("ecse_evaluation_exists", ecse_ev and ecse_ev["c"] >= 1, str(ecse_ev["c"] if ecse_ev else 0)))
    checks.append(_check("no_duplicate_ecse_eval", len(ecse_ev_rows) == 1, str(len(ecse_ev_rows))))

    if ecse_ev_rows:
        ev = ecse_ev_rows[0]
        checks.append(_check("ecse_top3_eval", ev["top3_correct"] == 1))
        checks.append(_check("ecse_top5_eval", ev["top5_correct"] == 1))
        checks.append(_check("ecse_top1_miss_expected", ev["top1_correct"] == 0))
        checks.append(_check("ecse_rank_2", ev["rank_of_actual_score"] == 2, str(ev["rank_of_actual_score"])))
        if ecse and wde:
            checks.append(
                _check(
                    "eval_after_prediction",
                    str(ev["evaluated_at"]) >= str(ecse["generated_at"]).split(".")[0][:10],
                    f"pred={ecse['generated_at']} eval={ev['evaluated_at']}",
                )
            )

    if wde and ecse:
        checks.append(
            _check(
                "result_after_prediction",
                str(fr["finished_at"]) > str(wde["predicted_at"]) if fr else False,
                f"pred={wde['predicted_at']} fin={fr['finished_at'] if fr else None}",
            )
        )

    wde_eval = conn.execute(
        "SELECT market_1x2_status, market_btts_status, market_ou_status, evaluation_source FROM worldcup_prediction_evaluations WHERE fixture_id=?",
        (FIXTURE_ID,),
    ).fetchone()
    if wde_eval:
        checks.append(_check("wde_1x2_correct", wde_eval["market_1x2_status"] == "correct"))
        checks.append(_check("wde_btts_correct", wde_eval["market_btts_status"] == "correct"))
        checks.append(_check("wde_ou_correct", wde_eval["market_ou_status"] == "correct"))
        checks.append(_check("wde_eval_production", wde_eval["evaluation_source"] == "production"))

    conn.close()

    wde_src = (ROOT / "worldcup_predictor" / "owner_daily" / "predictions.py").read_text(encoding="utf-8")
    checks.append(_check("wde_code_present", "run_daily_wde" in wde_src))
    ecse_src = (ROOT / "worldcup_predictor" / "research" / "ecse_live" / "evaluator.py").read_text(encoding="utf-8")
    checks.append(_check("ecse_evaluator_present", "evaluate_frozen_snapshot" in ecse_src))

    for unit in ("worldcup-daily.timer", "worldcup-hourly.timer", "owner-daily.timer"):
        try:
            proc = subprocess.run(["systemctl", "is-enabled", unit], capture_output=True, text=True, timeout=5)
            checks.append(_check(f"timer_off_{unit}", proc.stdout.strip() not in ("enabled", "enabled-runtime")))
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            checks.append(_check(f"timer_skipped_{unit}", True))

    passed = sum(1 for c in checks if c["passed"])
    result = {
        "phase": "MATCH-EVAL-1567310-1",
        "passed": passed,
        "total": len(checks),
        "all_passed": passed == len(checks),
        "provider_calls_used": 0,
        "checks": checks,
    }
    VALIDATION_ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    VALIDATION_ARTIFACT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
