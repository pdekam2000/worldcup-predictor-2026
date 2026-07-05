#!/usr/bin/env python3
"""Import canonical fixture/result/ECSE rows (surgical parity repair)."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.research.ecse_live.store import ensure_ecse_live_tables, insert_evaluation, has_snapshot
from worldcup_predictor.research.ecse_live.evaluator import run_ecse_evaluations, evaluate_frozen_snapshot
from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcomeResolver
from worldcup_predictor.config.settings import get_settings


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "artifacts/ecse_evaluation_parity_and_reliability_gate_1/parity_repair_export.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    settings = get_settings()
    conn = sqlite3.connect(settings.sqlite_path)
    conn.row_factory = sqlite3.Row
    ensure_ecse_live_tables(conn)
    applied = {"fixtures": 0, "results": 0, "ecse": 0, "evaluations": 0, "skipped": []}

    fx_cols = [r[1] for r in conn.execute("PRAGMA table_info(fixtures)").fetchall()]
    fr_cols = [r[1] for r in conn.execute("PRAGMA table_info(fixture_results)").fetchall()]

    for upd in data.get("fixture_updates") or []:
        conn.execute(
            "UPDATE fixtures SET status=?, kickoff_utc=COALESCE(kickoff_utc, ?) WHERE fixture_id=?",
            (upd["status"], upd.get("kickoff_utc"), int(upd["fixture_id"])),
        )
        applied["fixtures"] = applied.get("fixtures", 0) + 1

    for fx in data.get("fixtures") or []:
        fid = int(fx["fixture_id"])
        if conn.execute("SELECT 1 FROM fixtures WHERE fixture_id=?", (fid,)).fetchone():
            applied["skipped"].append(f"fixture_{fid}_exists")
            continue
        cols = [k for k in fx.keys() if k in fx_cols]
        vals = [fx[k] for k in cols]
        conn.execute(
            f"INSERT INTO fixtures ({','.join(cols)}) VALUES ({','.join('?'*len(cols))})",
            vals,
        )
        applied["fixtures"] += 1

    for fr in data.get("fixture_results") or []:
        fid = int(fr["fixture_id"])
        if conn.execute("SELECT 1 FROM fixture_results WHERE fixture_id=?", (fid,)).fetchone():
            applied["skipped"].append(f"result_{fid}_exists")
            continue
        cols = [k for k in fr.keys() if k in fr_cols]
        vals = [fr[k] for k in cols]
        conn.execute(
            f"INSERT INTO fixture_results ({','.join(cols)}) VALUES ({','.join('?'*len(cols))})",
            vals,
        )
        applied["results"] += 1

    snap_cols = [r[1] for r in conn.execute("PRAGMA table_info(ecse_prediction_snapshots)").fetchall()]
    for snap in data.get("ecse_snapshots") or []:
        fid = int(snap["fixture_id"])
        if has_snapshot(conn, fid):
            applied["skipped"].append(f"ecse_{fid}_exists")
            continue
        cols = [k for k in snap.keys() if k in snap_cols and k != "id"]
        vals = [snap[k] for k in cols]
        conn.execute(
            f"INSERT INTO ecse_prediction_snapshots ({','.join(cols)}) VALUES ({','.join('?'*len(cols))})",
            vals,
        )
        applied["ecse"] += 1

    conn.commit()

    eval_result = run_ecse_evaluations(conn, settings=settings, limit=100, eval_minutes_after_ft=0)
    applied["evaluations"] = eval_result.evaluated
    applied["eval_details"] = eval_result.details[:20]
    conn.close()
    out = Path("artifacts/ecse_evaluation_parity_and_reliability_gate_1/parity_repairs_applied.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(applied, indent=2, default=str), encoding="utf-8")
    print(json.dumps(applied, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
