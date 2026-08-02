"""Read-only forensic inventory of project data stores."""
from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]

# Prefer live DBs; skip huge duplicate backups for primary inventory (still list them).
PRIMARY_DBS = [
    ROOT / "data" / "football_intelligence.db",
    ROOT / "data" / "evaluation" / "forward_prediction_tracking.db",
    ROOT / "data" / "worldcup_predictor.db",
    ROOT / "data" / "research" / "ecse_timing_experiment.db",
]

INTERESTING_TABLE_KEYS = (
    "fixture",
    "result",
    "odds",
    "predict",
    "freeze",
    "ecse",
    "wde",
    "shadow",
    "lambda",
    "dna",
    "twin",
    "hcee",
    "exact",
    "eval",
    "owner",
    "forward",
)


def _open_ro(path: Path) -> sqlite3.Connection | None:
    if not path.exists():
        return None
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_count(conn: sqlite3.Connection, table: str) -> int | None:
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0])
    except Exception:
        return None


def _safe_distinct(conn: sqlite3.Connection, table: str, col: str) -> int | None:
    try:
        return int(conn.execute(f"SELECT COUNT(DISTINCT [{col}]) FROM [{table}] WHERE [{col}] IS NOT NULL").fetchone()[0])
    except Exception:
        return None


def inventory_sqlite(path: Path, *, deep: bool = True) -> dict[str, Any]:
    out: dict[str, Any] = {
        "path": str(path.relative_to(ROOT)).replace("\\", "/") if path.is_relative_to(ROOT) else str(path),
        "exists": path.exists(),
        "size_mb": round(path.stat().st_size / 1e6, 2) if path.exists() else None,
        "tables": [],
        "safe_to_use": True,
        "notes": [],
    }
    if "backup" in str(path).lower():
        out["safe_to_use"] = False
        out["notes"].append("backup_duplicate_skip_for_primary_corpus")
        out["cohort_hint"] = "BACKUP_ONLY"
        return out
    conn = _open_ro(path)
    if conn is None:
        return out
    try:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY 1")]
        interesting = [t for t in tables if any(k in t.lower() for k in INTERESTING_TABLE_KEYS)]
        for t in interesting if deep else interesting[:40]:
            n = _table_count(conn, t)
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info([{t}])")]
            fid_col = next((c for c in cols if c.lower() in {"fixture_id", "registry_fixture_id"}), None)
            entry: dict[str, Any] = {"table": t, "rows": n, "fixture_id_col": fid_col, "columns_n": len(cols)}
            if fid_col and n is not None and n < 5_000_000:
                entry["unique_fixtures"] = _safe_distinct(conn, t, fid_col)
            out["tables"].append(entry)
        # key aggregates on football_intelligence
        names = {t.lower() for t in tables}
        if "fixture_results" in names:
            out["fixture_results_n"] = _table_count(conn, "fixture_results")
            out["fixture_results_finished"] = conn.execute(
                "SELECT COUNT(*) FROM fixture_results WHERE home_goals IS NOT NULL"
            ).fetchone()[0]
        if "fixtures" in names:
            out["fixtures_n"] = _table_count(conn, "fixtures")
            try:
                dr = conn.execute(
                    "SELECT MIN(kickoff_utc), MAX(kickoff_utc) FROM fixtures WHERE kickoff_utc IS NOT NULL"
                ).fetchone()
                out["fixtures_date_range"] = {"min": dr[0], "max": dr[1]}
            except Exception:
                pass
        if "worldcup_stored_predictions" in names:
            out["stored_predictions_n"] = _table_count(conn, "worldcup_stored_predictions")
            out["stored_with_results"] = conn.execute(
                """
                SELECT COUNT(DISTINCT sp.fixture_id)
                FROM worldcup_stored_predictions sp
                JOIN fixture_results fr ON fr.fixture_id = sp.fixture_id
                WHERE fr.home_goals IS NOT NULL AND COALESCE(sp.is_active,1)=1
                """
            ).fetchone()[0]
        if "odds_snapshots" in names:
            out["odds_snapshots_n"] = _table_count(conn, "odds_snapshots")
            out["odds_with_results"] = conn.execute(
                """
                SELECT COUNT(DISTINCT o.fixture_id)
                FROM odds_snapshots o
                JOIN fixture_results fr ON fr.fixture_id = o.fixture_id
                WHERE fr.home_goals IS NOT NULL
                """
            ).fetchone()[0]
        if "ecse_prediction_snapshots" in names:
            out["ecse_snapshots_n"] = _table_count(conn, "ecse_prediction_snapshots")
            out["ecse_frozen_with_results"] = conn.execute(
                """
                SELECT COUNT(DISTINCT e.fixture_id)
                FROM ecse_prediction_snapshots e
                JOIN fixture_results fr ON fr.fixture_id = e.fixture_id
                WHERE COALESCE(e.is_frozen,0)=1 AND fr.home_goals IS NOT NULL
                """
            ).fetchone()[0]
        if "lambda_v2_shadow_outputs" in names:
            out["lambda_v2_n"] = _table_count(conn, "lambda_v2_shadow_outputs")
        if "historical_fixture_results" in names:
            out["historical_fixture_results_n"] = _table_count(conn, "historical_fixture_results")
        if "historical_csv_odds_prematch_clean" in names:
            out["historical_csv_odds_prematch_clean_n"] = _table_count(conn, "historical_csv_odds_prematch_clean")
    finally:
        conn.close()
    return out


def inventory_artifacts() -> list[dict[str, Any]]:
    globs = [
        "artifacts/finished_match_evaluation/**/complete_fixture_evaluations.json",
        "artifacts/prediction_engine_75_phase2/**/feature_store_v2.parquet",
        "artifacts/prediction_engine_75_phase3/**/validation_report.json",
        "artifacts/prediction_engine_75_phase4/**/validation_report.json",
        "artifacts/**/selected_matches.json",
        "artifacts/coverage_optimizer/**/forward_shadow.db",
    ]
    rows = []
    for g in globs:
        for p in ROOT.glob(g):
            if not p.is_file():
                continue
            entry: dict[str, Any] = {
                "path": str(p.relative_to(ROOT)).replace("\\", "/"),
                "size_mb": round(p.stat().st_size / 1e6, 4),
                "kind": "artifact",
            }
            if p.suffix == ".json" and "complete_fixture" in p.name:
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    if isinstance(data, list):
                        entry["rows"] = len(data)
                        entry["unique_fixtures"] = len({int(x.get("fixture_id") or 0) for x in data if x.get("fixture_id")})
                except Exception:
                    pass
            rows.append(entry)
    return rows


def run_inventory() -> dict[str, Any]:
    db_rows = []
    for p in PRIMARY_DBS:
        db_rows.append(inventory_sqlite(p, deep=True))
    # list backups without deep scan
    for p in sorted((ROOT / "data" / "backups").glob("*.db"))[:8] if (ROOT / "data" / "backups").exists() else []:
        db_rows.append(inventory_sqlite(p, deep=False))

    # forward tracking if present
    arts = inventory_artifacts()
    fi = next((d for d in db_rows if d.get("path", "").endswith("football_intelligence.db")), {})
    reconciliation = {
        "fixtures_n": fi.get("fixtures_n"),
        "fixture_results_finished": fi.get("fixture_results_finished"),
        "stored_with_results": fi.get("stored_with_results"),
        "odds_with_results": fi.get("odds_with_results"),
        "ecse_frozen_with_results": fi.get("ecse_frozen_with_results"),
        "note": "Valid immutable prematch corpus requires prediction/freeze before kickoff + regulation result; market-only rows are separate cohort",
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "databases": db_rows,
        "artifacts": arts,
        "reconciliation": reconciliation,
        "primary_db": "data/football_intelligence.db",
    }


def inventory_to_csv_rows(inv: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for db in inv.get("databases") or []:
        for t in db.get("tables") or []:
            rows.append(
                {
                    "source": db.get("path"),
                    "table": t.get("table"),
                    "rows": t.get("rows"),
                    "unique_fixtures": t.get("unique_fixtures"),
                    "safe_to_use": db.get("safe_to_use"),
                    "size_mb": db.get("size_mb"),
                }
            )
        if not db.get("tables"):
            rows.append(
                {
                    "source": db.get("path"),
                    "table": "",
                    "rows": None,
                    "unique_fixtures": None,
                    "safe_to_use": db.get("safe_to_use"),
                    "size_mb": db.get("size_mb"),
                }
            )
    return rows
