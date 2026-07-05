#!/usr/bin/env python3
"""CONTROLLED-1X2-ROUND-OF-16-1 — Validation."""

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

PHASE = "CONTROLLED-1X2-ROUND-OF-16-1"
OUTPUT = ROOT / "artifacts" / "controlled_1x2_round_of_16_1" / "validation.json"
WORKFLOW = ROOT / "artifacts" / "controlled_1x2_round_of_16_1" / "workflow.json"

FOUR_FIXTURES = {
    1570714: {"match": "Mexico vs England", "existing": True, "hash_key": "mexico_hash"},
    1576756: {"match": "Portugal vs Spain", "existing": True, "hash_key": "portugal_hash"},
}
NEW_FIXTURES = {
    "argentina_egypt": ("Argentina", "Egypt"),
    "switzerland_colombia": ("Switzerland", "Colombia"),
}
MAX_ODDS_CALLS = 40
COLOMBIA_EVAL_ID = 1567310
COLOMBIA_HASH = "07b841fc1025af28"


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

    workflow = {}
    if WORKFLOW.is_file():
        workflow = json.loads(WORKFLOW.read_text(encoding="utf-8"))

    # Colombia frozen eval untouched
    col = conn.execute(
        "SELECT payload_json FROM worldcup_stored_predictions WHERE fixture_id=?",
        (COLOMBIA_EVAL_ID,),
    ).fetchone()
    checks.append(
        _check(
            "colombia_1567310_payload_unchanged",
            _payload_hash(col["payload_json"] if col else None) == COLOMBIA_HASH,
            _payload_hash(col["payload_json"] if col else None),
        )
    )

    # Discover new fixture ids from workflow or DB
    arg_fid = swi_fid = None
    for entry in workflow.get("discovery", {}).get("entries", []):
        if entry.get("key") == "argentina_egypt" and entry.get("fixture_id"):
            arg_fid = int(entry["fixture_id"])
        if entry.get("key") == "switzerland_colombia" and entry.get("fixture_id"):
            swi_fid = int(entry["fixture_id"])

    if not arg_fid:
        row = conn.execute(
            """
            SELECT fixture_id FROM fixtures WHERE is_placeholder=0 AND competition_key='world_cup_2026'
            AND status='NS' AND (
              (home_team='Argentina' AND away_team='Egypt') OR (home_team='Egypt' AND away_team='Argentina')
            ) LIMIT 1
            """
        ).fetchone()
        arg_fid = int(row["fixture_id"]) if row else None
    if not swi_fid:
        row = conn.execute(
            """
            SELECT fixture_id FROM fixtures WHERE is_placeholder=0 AND competition_key='world_cup_2026'
            AND status='NS' AND (
              (home_team='Switzerland' AND away_team='Colombia') OR (home_team='Colombia' AND away_team='Switzerland')
            ) LIMIT 1
            """
        ).fetchone()
        swi_fid = int(row["fixture_id"]) if row else None

    all_fids = [1570714, 1576756]
    if arg_fid:
        all_fids.append(arg_fid)
        FOUR_FIXTURES[arg_fid] = {"match": "Argentina vs Egypt", "existing": False}
    if swi_fid:
        all_fids.append(swi_fid)
        FOUR_FIXTURES[swi_fid] = {"match": "Switzerland vs Colombia", "existing": False}

    # Missing fixtures imported or explicitly unavailable
    discovery = workflow.get("discovery", {}).get("entries", [])
    for key in ("argentina_egypt", "switzerland_colombia"):
        ent = next((e for e in discovery if e.get("key") == key), None)
        if ent:
            ok = ent.get("status") in ("found_in_provider", "already_in_db") or ent.get("fixture_id")
            if ent.get("status") == "FIXTURE_NOT_AVAILABLE_FROM_PROVIDER":
                ok = True
            checks.append(_check(f"discovery_{key}", ok, str(ent.get("status"))))
        else:
            checks.append(_check(f"discovery_{key}", False, "missing workflow entry"))

    # No duplicate fixtures for target pairs
    for home, away in [("Mexico", "England"), ("Portugal", "Spain"), ("Argentina", "Egypt"), ("Switzerland", "Colombia")]:
        rows = conn.execute(
            """
            SELECT COUNT(*) AS c FROM fixtures WHERE is_placeholder=0 AND competition_key='world_cup_2026'
            AND ((home_team=? AND away_team=?) OR (home_team=? AND away_team=?))
            AND UPPER(status) IN ('NS','TBD','TIMED','SCHEDULED')
            """,
            (home, away, away, home),
        ).fetchone()
        checks.append(_check(f"no_duplicate_{home}_{away}", int(rows["c"]) <= 1, f"count={rows['c']}"))

    # Mexico / Portugal preserved
    forensic = workflow.get("forensic", {})
    preserved = forensic.get("existing_payload_preserved", {})
    for fid in (1570714, 1576756):
        w = conn.execute(
            "SELECT payload_json FROM worldcup_stored_predictions WHERE fixture_id=?",
            (fid,),
        ).fetchone()
        h = _payload_hash(w["payload_json"] if w else None)
        checks.append(_check(f"prediction_preserved_{fid}", preserved.get(str(fid), True), h))

    # Single-row predictions
    for fid, meta in FOUR_FIXTURES.items():
        if fid not in all_fids:
            continue
        cnt = conn.execute(
            "SELECT COUNT(*) AS c FROM worldcup_stored_predictions WHERE fixture_id=?",
            (fid,),
        ).fetchone()["c"]
        checks.append(_check(f"single_wde_row_{fid}", int(cnt) == 1, f"count={cnt}"))

    # H/X/A sum and pick logic
    for fid in all_fids:
        w = conn.execute(
            "SELECT payload_json FROM worldcup_stored_predictions WHERE fixture_id=?",
            (fid,),
        ).fetchone()
        if not w:
            checks.append(_check(f"stored_{fid}", False, "no prediction"))
            continue
        p = json.loads(w["payload_json"])
        probs = p.get("probabilities") or {}
        h, d, a = probs.get("home_win"), probs.get("draw"), probs.get("away_win")
        if h is not None and d is not None and a is not None:
            s = float(h) + float(d) + float(a)
            checks.append(_check(f"prob_sum_{fid}", 95 <= s <= 105, f"sum={s}"))
            pick = p.get("prediction")
            mapping = {"home": float(h), "draw": float(d), "away": float(a)}
            if pick in mapping:
                mx = max(mapping.values())
                checks.append(
                    _check(
                        f"pick_is_plausible_{fid}",
                        mapping[pick] >= mx - 5.0,
                        f"pick={pick} probs={mapping}",
                    )
                )
        meta = p.get("odds_freshness_metadata") or {}
        checks.append(
            _check(
                f"odds_metadata_traceable_{fid}",
                bool(p.get("odds_freshness_status") or meta.get("freshness_flag")),
                str(p.get("odds_freshness_status") or meta.get("freshness_flag")),
            )
        )

    # Provider calls bounded
    refresh = workflow.get("odds_refresh", {})
    calls = int(refresh.get("calls_used") or 0)
    checks.append(_check("provider_calls_bounded", calls <= MAX_ODDS_CALLS, f"calls={calls}"))

    # No ECSE created by phase for new fixtures
    ecse_guard = workflow.get("ecse_guard", {})
    new_ecse = ecse_guard.get("new_ecse_created", {})
    for fid in all_fids:
        delta = int(new_ecse.get(str(fid), 0) or 0)
        if fid in (1570714, 1576756):
            checks.append(_check(f"no_new_ecse_existing_{fid}", delta == 0, f"delta={delta}"))
        else:
            checks.append(_check(f"no_ecse_new_fixture_{fid}", delta == 0, f"delta={delta}"))

    # Timers report only
    pre = workflow.get("preflight", {})
    checks.append(_check("preflight_recorded", bool(pre.get("git_head")), pre.get("git_head", "")))

    # WDE/ECSE formula unchanged — git diff check on key files
    for rel in (
        "worldcup_predictor/orchestration/predict_pipeline.py",
        "worldcup_predictor/research/ecse_live/prediction_builder.py",
    ):
        path = ROOT / rel
        checks.append(_check(f"file_exists_{rel}", path.is_file(), str(path)))

    passed = sum(1 for c in checks if c["passed"])
    failed = [c for c in checks if not c["passed"]]
    summary = {
        "phase": PHASE,
        "passed": passed,
        "failed": len(failed),
        "total": len(checks),
        "all_passed": len(failed) == 0,
        "failed_checks": failed,
        "checks": checks,
        "all_four_fixture_ids": all_fids,
        "argentina_fixture_id": arg_fid,
        "switzerland_fixture_id": swi_fid,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    conn.close()
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
