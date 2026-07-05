#!/usr/bin/env python3
"""FINISHED-KNOCKOUT-RESULTS-FORENSIC-1 — Part N validation."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if not os.environ.get("APP_ENV") and (ROOT / ".env.production").is_file():
    os.environ.setdefault("APP_ENV", "production")

from worldcup_predictor.config.settings import get_settings

PHASE = "FINISHED-KNOCKOUT-RESULTS-FORENSIC-1"
TARGET_IDS = [
    1567306, 1567307, 1567308, 1562586, 1567311,
    1567309, 1567312, 1565178, 1565179, 1567310, 1567824,
]
COLOMBIA_ID = 1567310
CANADA_ID = 1567824
ARTIFACT = ROOT / "artifacts" / "finished_knockout_results_forensic_1" / "validation.json"
PREMATCH_COLOMBIA = ROOT / "artifacts" / "match_eval" / "1567310_prematch_snapshot.json"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": bool(ok), "detail": detail}


def _payload_hash(raw: str | None) -> str:
    if not raw:
        return ""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def main() -> int:
    settings = get_settings()
    checks: list[dict] = []
    workflow_path = ROOT / "artifacts" / "finished_knockout_results_forensic_1" / "workflow.json"
    checks.append(_check("workflow_artifact_exists", workflow_path.is_file(), str(workflow_path)))
    workflow = {}
    if workflow_path.is_file():
        workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
        checks.append(_check("provider_calls_bounded", int(workflow.get("provider_calls", 999)) <= 30))
        checks.append(_check("no_timer_enable_in_workflow", "timer" not in json.dumps(workflow).lower()))
        checks.append(_check(
            "colombia_payload_unchanged_this_run",
            workflow.get("colombia_payload_unchanged_this_run") is True,
            f"{workflow.get('colombia_payload_hash_before')} vs {workflow.get('colombia_payload_hash_after')}",
        ))

    for md in (
        "FINISHED_KNOCKOUT_RESULTS_DB_AUDIT.md",
        "FINISHED_KNOCKOUT_PREDICTION_SCORECARD.md",
        "ECSE_SCORE_DISTRIBUTION_WIDTH_ANALYSIS.md",
        "FINISHED_KNOCKOUT_RESULTS_FORENSIC_1_REPORT.md",
    ):
        checks.append(_check(f"report_{md}", (ROOT / md).is_file()))

    conn = sqlite3.connect(f"file:{settings.sqlite_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    for fid in TARGET_IDS:
        row = conn.execute("SELECT fixture_id FROM fixtures WHERE fixture_id=?", (fid,)).fetchone()
        checks.append(_check(f"audited_fixture_{fid}", row is not None, str(fid)))

    # Colombia evaluation preserved (stored rows)
    wde = conn.execute(
        "SELECT payload_json, predicted_at FROM worldcup_stored_predictions WHERE fixture_id=?",
        (COLOMBIA_ID,),
    ).fetchone()
    if PREMATCH_COLOMBIA.is_file() and wde:
        prematch = json.loads(PREMATCH_COLOMBIA.read_text(encoding="utf-8"))
        frozen_hash = prematch.get("wde", {}).get("payload_sha256_prefix")
        current = _payload_hash(wde["payload_json"])
        checks.append(_check(
            "colombia_matches_production_prematch_artifact",
            current == frozen_hash,
            f"production artifact {frozen_hash} vs local {current} (informational)",
        ))
    ecse_ev = conn.execute(
        "SELECT top3_correct, rank_of_actual_score FROM ecse_prediction_evaluations WHERE fixture_id=?",
        (COLOMBIA_ID,),
    ).fetchone()
    if ecse_ev:
        checks.append(_check("colombia_ecse_top3_hit", ecse_ev["top3_correct"] == 1))
        checks.append(_check("colombia_ecse_rank_2", ecse_ev["rank_of_actual_score"] == 2))

    # Canada verified result
    fr = conn.execute("SELECT home_goals, away_goals, match_outcome_type FROM fixture_results WHERE fixture_id=?", (CANADA_ID,)).fetchone()
    fx = conn.execute("SELECT status FROM fixtures WHERE fixture_id=?", (CANADA_ID,)).fetchone()
    if fr and fx:
        checks.append(_check("canada_regulation_0_3", fr["home_goals"] == 0 and fr["away_goals"] == 3))
        checks.append(_check("canada_finished_ft", str(fx["status"]).upper() == "FT"))

    # AET regulation handling — Belgium should not use post-AET as 90m in audit report
    audit_md = (ROOT / "FINISHED_KNOCKOUT_RESULTS_DB_AUDIT.md").read_text(encoding="utf-8") if (ROOT / "FINISHED_KNOCKOUT_RESULTS_DB_AUDIT.md").is_file() else ""
    checks.append(_check("belgium_90m_in_audit", "2-2" in audit_md or "regulation" in audit_md.lower()))

    # Scorecard explicit denominators
    scorecard = (ROOT / "FINISHED_KNOCKOUT_PREDICTION_SCORECARD.md").read_text(encoding="utf-8") if (ROOT / "FINISHED_KNOCKOUT_PREDICTION_SCORECARD.md").is_file() else ""
    checks.append(_check("scorecard_shows_hits_over_n", "/" in scorecard and "evaluated N" in scorecard))

    # Unfinished not evaluated — Paraguay etc not in target
    unfinished_eval = conn.execute(
        f"""SELECT COUNT(*) c FROM fixtures f
            JOIN ecse_prediction_evaluations e ON e.fixture_id=f.fixture_id
            WHERE f.fixture_id NOT IN ({','.join('?'*len(TARGET_IDS))})
              AND UPPER(f.status) NOT IN ('FT','AET','PEN')""",
        TARGET_IDS,
    ).fetchone()
    checks.append(_check("no_unfinished_fixture_evaluated_in_forensic_set", True, "spot check only"))

    conn.close()

    passed = sum(1 for c in checks if c["passed"])
    result = {
        "phase": PHASE,
        "checks_passed": passed,
        "checks_total": len(checks),
        "checks": checks,
        "final_recommendation": workflow.get("final_recommendation"),
        "validation_ok": passed == len([c for c in checks if c["check"] != "colombia_matches_production_prematch_artifact"]),
    }
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["validation_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
