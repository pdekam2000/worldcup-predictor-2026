#!/usr/bin/env python3
"""Read-only database truth audit — local or production."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

KEY_TABLES = [
    "users",
    "fixtures",
    "worldcup_stored_predictions",
    "worldcup_prediction_evaluations",
    "odds_snapshots",
    "fixture_goal_events",
    "fixture_results",
    "ecse_prediction_snapshots",
    "ecse_oddalerts_shadow_predictions",
    "ecse_oddalerts_shadow_monitor",
    "learning_records_v2",
    "prediction_history",
    "worldcup_prediction_history",
]

EGIE_TABLES = [
    "egie_goal_timing_snapshots",
    "egie_first_goal_team_v2_snapshots",
    "egie_goalscorer_availability_snapshots",
]

FINISHED = ("FT", "AET", "PEN", "AWD", "WO")


def audit_sqlite(path: Path, label: str) -> dict:
    out: dict = {
        "label": label,
        "path": str(path),
        "exists": path.exists(),
    }
    if not path.exists():
        return out
    st = path.stat()
    out["size_bytes"] = st.st_size
    out["size_gb"] = round(st.st_size / (1024**3), 3)
    out["modified_utc"] = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    cur = conn.cursor()
    try:
        cur.execute("SELECT value FROM schema_meta WHERE key='schema_version'")
        row = cur.fetchone()
        out["schema_version"] = row[0] if row else None
    except Exception as e:
        out["schema_version_error"] = str(e)
    tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    out["table_count"] = len(tables)
    counts = {}
    for t in KEY_TABLES + EGIE_TABLES:
        if t not in tables:
            counts[t] = "missing"
            continue
        try:
            cur.execute(f"SELECT COUNT(*) FROM {t}")
            counts[t] = cur.fetchone()[0]
        except Exception as e:
            counts[t] = f"error:{e}"
    out["row_counts"] = counts
    if "fixtures" in tables:
        cur.execute("SELECT COUNT(*) FROM fixtures WHERE status IN ('FT','AET','PEN','AWD','WO')")
        out["finished_fixtures"] = cur.fetchone()[0]
        cur.execute("SELECT MAX(updated_at) FROM fixtures")
        out["fixtures_max_updated_at"] = cur.fetchone()[0]
    if "worldcup_stored_predictions" in tables:
        for col in ("created_at", "generated_at", "stored_at", "updated_at"):
            try:
                cur.execute(f"SELECT MAX({col}) FROM worldcup_stored_predictions")
                out[f"predictions_max_{col}"] = cur.fetchone()[0]
                break
            except Exception:
                continue
    if "worldcup_prediction_evaluations" in tables:
        try:
            cur.execute("SELECT COUNT(*) FROM worldcup_prediction_evaluations")
            out["evaluations_total"] = cur.fetchone()[0]
            for col in ("evaluated_at", "created_at", "updated_at"):
                try:
                    cur.execute(f"SELECT MAX({col}) FROM worldcup_prediction_evaluations")
                    out[f"evaluations_max_{col}"] = cur.fetchone()[0]
                    break
                except Exception:
                    continue
        except Exception as e:
            out["evaluations_error"] = str(e)
    conn.close()
    return out


def audit_postgres() -> dict:
    out: dict = {"label": "postgresql", "configured": False}
    try:
        from sqlalchemy import text
        from worldcup_predictor.database.saas_factory import saas_uow

        pg_tables = ["users", "subscriptions", "user_settings", "user_prediction_history"]
        with saas_uow() as uow:
            out["configured"] = True
            counts = {}
            for t in pg_tables:
                try:
                    n = uow.session.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
                    counts[t] = int(n or 0)
                except Exception as e:
                    counts[t] = f"error:{e}"
            out["row_counts"] = counts
            try:
                rev = uow.session.execute(text("SELECT version_num FROM alembic_version")).scalar()
                out["alembic_version"] = rev
            except Exception as e:
                out["alembic_version_error"] = str(e)
    except Exception as e:
        out["error"] = str(e)
    return out


def main() -> int:
    env_label = os.environ.get("AUDIT_ENV", "local")
    results: dict = {"environment": env_label, "timestamp_utc": datetime.now(timezone.utc).isoformat(), "databases": []}

    primary = Path(os.environ.get("SQLITE_PATH", "data/football_intelligence.db"))
    if not primary.is_absolute():
        primary = ROOT / primary
    results["databases"].append(audit_sqlite(primary, "primary_sqlite"))

    for p in sorted((ROOT / "data" / "backups").glob("*.db"))[:8]:
        results["databases"].append(audit_sqlite(p, f"backup:{p.name}"))

    for extra in [ROOT / "data" / "dev" / "football_intelligence.db"]:
        if extra.exists() and extra != primary:
            results["databases"].append(audit_sqlite(extra, f"extra:{extra.name}"))

    results["postgresql"] = audit_postgres()
    print(json.dumps(results, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
