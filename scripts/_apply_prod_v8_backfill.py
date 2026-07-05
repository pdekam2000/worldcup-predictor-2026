#!/usr/bin/env python3
"""Apply schema v8 columns, regulation backfill, and ECSE re-evaluation on production."""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.migrations import apply_migrations

V8_COLS = [
    ("regulation_home_goals", "INTEGER"),
    ("regulation_away_goals", "INTEGER"),
    ("extra_time_home_goals", "INTEGER"),
    ("extra_time_away_goals", "INTEGER"),
    ("penalties_home_goals", "INTEGER"),
    ("penalties_away_goals", "INTEGER"),
    ("final_stage", "TEXT"),
    ("qualified_team", "TEXT"),
    ("result_synced_at", "TEXT"),
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _ensure_v8_columns(conn: sqlite3.Connection) -> None:
    existing = {r[1] for r in conn.execute("PRAGMA table_info(fixture_results)").fetchall()}
    for col, typ in V8_COLS:
        if col not in existing:
            conn.execute(f"ALTER TABLE fixture_results ADD COLUMN {col} {typ}")
    conn.execute(
        "INSERT OR REPLACE INTO schema_meta(key, value) VALUES ('schema_version', '8')"
    )
    conn.commit()


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "artifacts/result_truth_schema_v8_and_ecse_reevaluation_1/prod_backfill_export.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    settings = get_settings()
    conn = sqlite3.connect(settings.sqlite_path)
    conn.row_factory = sqlite3.Row
    try:
        apply_migrations(conn)
    except Exception:
        _ensure_v8_columns(conn)

    applied = {"migration": True, "backfill": 0, "reevaluated": 0}
    for row in data.get("rows", []):
        fid = int(row["fixture_id"])
        sets = {k: v for k, v in row.items() if k != "fixture_id" and v is not None}
        if not sets:
            continue
        sql = ", ".join(f"{k}=?" for k in sets)
        conn.execute(
            f"UPDATE fixture_results SET {sql}, result_synced_at=? WHERE fixture_id=?",
            (*sets.values(), _utc_now(), fid),
        )
        applied["backfill"] += 1
    conn.commit()

    # Re-evaluate using regulation-aware resolver if available, else inline fallback
    try:
        from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcomeResolver
        from worldcup_predictor.research.ecse_live.evaluator import evaluate_frozen_snapshot
        from worldcup_predictor.research.ecse_live.store import _hydrate_snapshot, upsert_evaluation

        resolver = FixtureOutcomeResolver(settings)
        for row in data.get("rows", []):
            fid = int(row["fixture_id"])
            snap = conn.execute(
                "SELECT * FROM ecse_prediction_snapshots WHERE fixture_id=? AND is_frozen=1 ORDER BY id ASC LIMIT 1",
                (fid,),
            ).fetchone()
            if not snap:
                continue
            payload = evaluate_frozen_snapshot(_hydrate_snapshot(dict(snap)), resolver.resolve(fid))
            if not payload:
                continue
            upsert_evaluation(conn, payload)
            applied["reevaluated"] += 1
    except ImportError:
        from worldcup_predictor.research.ecse_live.evaluator import evaluate_frozen_snapshot, rank_from_frozen_snapshot
        from worldcup_predictor.research.ecse_live.store import _hydrate_snapshot
        from worldcup_predictor.outcomes.market_result_resolver import regulation_fixture_outcome_fields

        for row in data.get("rows", []):
            fid = int(row["fixture_id"])
            snap = conn.execute(
                "SELECT * FROM ecse_prediction_snapshots WHERE fixture_id=? AND is_frozen=1 ORDER BY id ASC LIMIT 1",
                (fid,),
            ).fetchone()
            fr = conn.execute("SELECT * FROM fixture_results WHERE fixture_id=?", (fid,)).fetchone()
            fx = conn.execute("SELECT * FROM fixtures WHERE fixture_id=?", (fid,)).fetchone()
            if not snap or not fr:
                continue
            reg_h, reg_a, reg_score, _ = regulation_fixture_outcome_fields(dict(fr), dict(fx) if fx else None)
            if reg_h is None or reg_a is None:
                continue
            snap_d = _hydrate_snapshot(dict(snap))
            scoreline = f"{reg_h}-{reg_a}"
            top5 = list(snap_d.get("top_5_scores") or [])
            top3 = list(snap_d.get("top_3_scores") or [])
            top1 = str(snap_d.get("top_1_score") or "")
            rank = rank_from_frozen_snapshot(snap_d, int(reg_h), int(reg_a))
            existing = conn.execute(
                "SELECT id FROM ecse_prediction_evaluations WHERE snapshot_id=?", (snap["id"],)
            ).fetchone()
            vals = (
                scoreline,
                1 if scoreline == top1 else 0,
                1 if scoreline in top3 else 0,
                1 if scoreline in top5 else 0,
                0,
                rank,
                int(reg_h),
                int(reg_a),
                _utc_now(),
                int(snap["id"]),
            )
            if existing:
                conn.execute(
                    """UPDATE ecse_prediction_evaluations SET final_score=?, top1_correct=?, top3_correct=?,
                    top5_correct=?, top10_correct=?, rank_of_actual_score=?, actual_home_goals=?, actual_away_goals=?,
                    evaluated_at=? WHERE snapshot_id=?""",
                    vals,
                )
            else:
                conn.execute(
                    """INSERT INTO ecse_prediction_evaluations (snapshot_id, fixture_id, final_score, top1_correct,
                    top3_correct, top5_correct, top10_correct, rank_of_actual_score, actual_home_goals, actual_away_goals,
                    status, evaluated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (snap["id"], fid, *vals[:9], "evaluated", vals[9]),
                )
            applied["reevaluated"] += 1
        conn.commit()

    conn.close()
    print(json.dumps(applied))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
