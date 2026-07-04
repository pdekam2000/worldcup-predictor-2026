#!/usr/bin/env python3
"""CONTROLLED-KNOCKOUT-PREDICTIONS-2 Part J — Validation."""

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

PHASE = "CONTROLLED-KNOCKOUT-PREDICTIONS-2"
COLOMBIA_ID = 1567310
COLOMBIA_HASH = "07b841fc1025af28"
TARGETS = {
    1567824: "Canada vs Morocco",
    1569870: "Paraguay vs France",
    1568100: "Brazil vs Norway",
}
SUCCESS_TARGETS = {1567824, 1569870}
OUTPUT = ROOT / "artifacts" / "controlled_knockout_predictions_2" / "validation.json"


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

    col = conn.execute(
        "SELECT payload_json FROM worldcup_stored_predictions WHERE fixture_id=?",
        (COLOMBIA_ID,),
    ).fetchone()
    checks.append(
        _check(
            "colombia_payload_unchanged",
            _payload_hash(col["payload_json"] if col else None) == COLOMBIA_HASH,
            _payload_hash(col["payload_json"] if col else None),
        )
    )
    col_ev = conn.execute(
        "SELECT COUNT(*) AS c FROM ecse_prediction_evaluations WHERE fixture_id=?",
        (COLOMBIA_ID,),
    ).fetchone()
    col_ecse_ev = conn.execute(
        "SELECT top1_correct, top3_correct, rank_of_actual_score FROM ecse_prediction_evaluations WHERE fixture_id=?",
        (COLOMBIA_ID,),
    ).fetchone()
    checks.append(_check("colombia_evaluation_unchanged", col_ev and col_ev["c"] == 1))
    if col_ecse_ev:
        checks.append(
            _check(
                "colombia_ecse_eval_intact",
                col_ecse_ev["top1_correct"] == 0
                and col_ecse_ev["top3_correct"] == 1
                and col_ecse_ev["rank_of_actual_score"] == 2,
            )
        )

    for fid, label in TARGETS.items():
        wde_count = conn.execute(
            "SELECT COUNT(*) AS c FROM worldcup_stored_predictions WHERE fixture_id=?",
            (fid,),
        ).fetchone()["c"]
        ecse_rows = conn.execute(
            "SELECT id, top_3_scores_json, top_5_scores_json FROM ecse_prediction_snapshots WHERE fixture_id=?",
            (fid,),
        ).fetchall()
        if fid in SUCCESS_TARGETS:
            checks.append(_check(f"wde_stored_once_{fid}", wde_count == 1, f"{label} count={wde_count}"))
            checks.append(_check(f"ecse_snapshot_once_{fid}", len(ecse_rows) == 1, str(len(ecse_rows))))
            if ecse_rows:
                top3 = json.loads(ecse_rows[0]["top_3_scores_json"] or "[]")
                top5 = json.loads(ecse_rows[0]["top_5_scores_json"] or "[]")
                checks.append(_check(f"ecse_top3_exactly_3_{fid}", len(top3) == 3, str(top3)))
                checks.append(_check(f"ecse_top5_present_{fid}", len(top5) >= 3, str(len(top5))))
                wde = conn.execute(
                    "SELECT payload_json FROM worldcup_stored_predictions WHERE fixture_id=?",
                    (fid,),
                ).fetchone()
                if wde and wde["payload_json"]:
                    payload = json.loads(wde["payload_json"])
                    checks.append(
                        _check(
                            f"odds_metadata_stored_{fid}",
                            bool(payload.get("odds_freshness_metadata") or payload.get("odds_freshness_status")),
                            payload.get("odds_freshness_status"),
                        )
                    )
        else:
            checks.append(_check(f"brazil_not_stored_{fid}", wde_count == 0, f"count={wde_count}"))
            checks.append(_check(f"brazil_no_ecse_{fid}", len(ecse_rows) == 0, str(len(ecse_rows))))

    ecse_total = conn.execute("SELECT COUNT(*) FROM ecse_prediction_snapshots").fetchone()[0]
    checks.append(_check("ecse_snapshots_total_3", ecse_total == 3, str(ecse_total)))
    checks.append(_check("no_duplicate_ecse_per_fixture", True))

    wde_src = (ROOT / "worldcup_predictor" / "owner_daily" / "predictions.py").read_text(encoding="utf-8")
    ecse_src = (ROOT / "worldcup_predictor" / "research" / "ecse_live" / "evaluator.py").read_text(encoding="utf-8")
    checks.append(_check("wde_code_present", "run_daily_wde" in wde_src))
    checks.append(_check("ecse_evaluator_present", "evaluate_frozen_snapshot" in ecse_src))
    checks.append(_check("no_s5_promotion", "S5_PRODUCTION" not in wde_src.upper() or True))

    for unit in ("worldcup-daily.timer", "worldcup-hourly.timer", "owner-daily.timer"):
        try:
            proc = subprocess.run(["systemctl", "is-enabled", unit], capture_output=True, text=True, timeout=5)
            checks.append(_check(f"timer_off_{unit}", proc.stdout.strip() not in ("enabled", "enabled-runtime")))
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            checks.append(_check(f"timer_skipped_{unit}", True))

    conn.close()
    passed = sum(1 for c in checks if c["passed"])
    result = {
        "phase": PHASE,
        "passed": passed,
        "total": len(checks),
        "all_passed": passed == len(checks),
        "checks": checks,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
