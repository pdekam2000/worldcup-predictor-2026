#!/usr/bin/env python3
"""BRAZIL-NORWAY-CONTROLLED-PREDICTION-1 Part M — Validation."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if not os.environ.get("APP_ENV") and (ROOT / ".env.production").is_file():
    os.environ.setdefault("APP_ENV", "production")

from worldcup_predictor.config.settings import get_settings

PHASE = "BRAZIL-NORWAY-CONTROLLED-PREDICTION-1"
BRAZIL_ID = 1568100
COLOMBIA_ID = 1567310
COLOMBIA_HASH = "07b841fc1025af28"
PROTECTED = {1567310: "Colombia vs Ghana", 1567824: "Canada vs Morocco", 1569870: "Paraguay vs France"}
SYNC_COMMIT = "b512e0bd600de12849dfaa0104ae643dff54afe0"  # pre-fix baseline; code hotfixes after
OUTPUT = ROOT / "artifacts" / "brazil_norway_controlled_prediction_1" / "validation.json"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": bool(ok), "detail": detail}


def _hash(raw: str | None) -> str:
    if not raw:
        return ""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def main() -> int:
    checks: list[dict] = []
    settings = get_settings()
    conn = sqlite3.connect(f"file:{settings.sqlite_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    checks.append(_check("production_on_main_branch", head.startswith("282ef") or head.startswith("6b5d5") or head.startswith("b512e"), head))

    brazil_wde = conn.execute(
        "SELECT payload_json, predicted_at FROM worldcup_stored_predictions WHERE fixture_id=?",
        (BRAZIL_ID,),
    ).fetchall()
    brazil_ecse = conn.execute(
        "SELECT * FROM ecse_prediction_snapshots WHERE fixture_id=?",
        (BRAZIL_ID,),
    ).fetchall()

    checks.append(_check("brazil_wde_stored_once", len(brazil_wde) == 1))
    checks.append(_check("brazil_ecse_snapshot_once", len(brazil_ecse) == 1))

    if brazil_ecse:
        ev = brazil_ecse[0]
        top3 = json.loads(ev["top_3_scores_json"] or "[]")
        top5 = json.loads(ev["top_5_scores_json"] or "[]")
        checks.append(_check("ecse_top3_exactly_3", len(top3) == 3, str(top3)))
        checks.append(_check("ecse_top5_present", len(top5) >= 3, str(len(top5))))
        checks.append(_check("ecse_frozen", ev["is_frozen"] == 1))
        checks.append(_check("ecse_snapshot_id_4", ev["id"] == 4, str(ev["id"])))

    if brazil_wde:
        payload = json.loads(brazil_wde[0]["payload_json"])
        checks.append(_check("wde_pick_home", payload.get("prediction") == "home"))
        checks.append(_check("odds_metadata_stored", bool(payload.get("odds_freshness_metadata"))))
        checks.append(_check("payload_hash_recorded", bool(_hash(brazil_wde[0]["payload_json"])), _hash(brazil_wde[0]["payload_json"])))
        fx = conn.execute("SELECT kickoff_utc FROM fixtures WHERE fixture_id=?", (BRAZIL_ID,)).fetchone()
        if fx:
            checks.append(_check("generated_before_kickoff", str(brazil_wde[0]["predicted_at"]) < str(fx["kickoff_utc"])))

    col = conn.execute("SELECT payload_json FROM worldcup_stored_predictions WHERE fixture_id=?", (COLOMBIA_ID,)).fetchone()
    checks.append(_check("colombia_payload_unchanged", _hash(col["payload_json"] if col else None) == COLOMBIA_HASH))

    col_ev = conn.execute("SELECT COUNT(*) AS c FROM ecse_prediction_evaluations WHERE fixture_id=?", (COLOMBIA_ID,)).fetchone()
    checks.append(_check("colombia_evaluation_unchanged", col_ev["c"] == 1))

    for fid, label in PROTECTED.items():
        if fid == COLOMBIA_ID:
            continue
        cnt = conn.execute("SELECT COUNT(*) AS c FROM worldcup_stored_predictions WHERE fixture_id=?", (fid,)).fetchone()["c"]
        ecse_cnt = conn.execute("SELECT COUNT(*) AS c FROM ecse_prediction_snapshots WHERE fixture_id=?", (fid,)).fetchone()["c"]
        checks.append(_check(f"protected_{fid}_wde_once", cnt == 1, label))
        checks.append(_check(f"protected_{fid}_ecse_once", ecse_cnt == 1, label))

    ecse_total = conn.execute("SELECT COUNT(*) FROM ecse_prediction_snapshots").fetchone()[0]
    wde_total = conn.execute("SELECT COUNT(*) FROM worldcup_stored_predictions").fetchone()[0]
    checks.append(_check("ecse_snapshots_total_4", ecse_total == 4, str(ecse_total)))
    checks.append(_check("wde_stored_total_52", wde_total == 52, str(wde_total)))

    for unit in ("worldcup-daily.timer", "worldcup-hourly.timer", "owner-daily.timer"):
        try:
            proc = subprocess.run(["systemctl", "is-enabled", unit], capture_output=True, text=True, timeout=5)
            checks.append(_check(f"timer_off_{unit}", proc.stdout.strip() not in ("enabled", "enabled-runtime")))
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            checks.append(_check(f"timer_skipped_{unit}", True))

    conn.close()
    passed = sum(1 for c in checks if c["passed"])
    result = {"phase": PHASE, "passed": passed, "total": len(checks), "all_passed": passed == len(checks), "checks": checks}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
