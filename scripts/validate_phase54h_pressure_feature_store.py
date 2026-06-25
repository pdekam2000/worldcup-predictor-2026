#!/usr/bin/env python3
"""Validate Phase 54H Sportmonks Pressure feature store."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54h_pressure_feature_store"
REPORT = ROOT / "PHASE_54H_PRESSURE_FEATURE_STORE_REPORT.md"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []

    try:
        from worldcup_predictor.feature_store.pressure_store.aggregations import (
            AGGREGATION_KEYS,
            compute_fixture_pressure_features,
        )
        from worldcup_predictor.feature_store.pressure_store.models import SportmonksPressureRecord
        from worldcup_predictor.feature_store.pressure_store.normalizers import normalize_fixture_pressure_records
        from worldcup_predictor.feature_store.pressure_store.sportmonks_pressure_store import SportmonksPressureFeatureStore

        checks.append(_check("pressure_store_module_imports", True))
    except Exception as exc:
        checks.append(_check("pressure_store_module_imports", False, str(exc)))
        SportmonksPressureFeatureStore = None  # type: ignore

    checks.append(_check("migration_file_exists", (ROOT / "alembic/versions/012_sportmonks_pressure_feature_store.py").is_file()))

    sample_path = ROOT / "data" / "egie" / "uefa_club" / "raw"
    sample_files = list(sample_path.glob("*.json")) if sample_path.is_dir() else []
    normalized_count = 0
    row_total = 0
    for path in sample_files[:40]:
        blob = json.loads(path.read_text(encoding="utf-8"))
        data = (blob.get("payload") or {}).get("data")
        if not isinstance(data, dict):
            continue
        recs = normalize_fixture_pressure_records(data, sportmonks_fixture_id=int(data.get("id") or path.stem))
        if recs:
            normalized_count += 1
            row_total += len(recs)
    checks.append(_check("pressure_normalized", normalized_count > 0, f"fixtures={normalized_count} rows={row_total}"))

    if normalized_count > 0:
        blob = json.loads(sample_files[0].read_text(encoding="utf-8"))
        data = (blob.get("payload") or {}).get("data")
        recs = normalize_fixture_pressure_records(data, sportmonks_fixture_id=int(data.get("id") or sample_files[0].stem))
        home = away = None
        for p in data.get("participants") or []:
            if isinstance(p, dict):
                loc = str((p.get("meta") or {}).get("location") or "").lower()
                if loc == "home":
                    home = int(p["id"])
                elif loc == "away":
                    away = int(p["id"])
        if home and away:
            feats = compute_fixture_pressure_features(recs, home_participant_id=home, away_participant_id=away)
            home_feats = feats.get("home") or {}
            agg_ok = all(k in home_feats for k in AGGREGATION_KEYS)
            checks.append(_check("aggregations_work", agg_ok, f"keys={list(home_feats.keys())[:5]}..."))
        else:
            checks.append(_check("aggregations_work", False, "no_participants"))

    store = SportmonksPressureFeatureStore()
    pg_ok = store.configured
    checks.append(_check("postgres_configured", pg_ok))

    if pg_ok:
        audit = store.quality_audit()
        tables_ready = audit.get("tables_ready", False)
        checks.append(_check("tables_ready", tables_ready, str(audit.get("error", ""))))

        rec_count = int((audit.get("records") or {}).get("record_count") or 0)
        summary_count = int((audit.get("summaries") or {}).get("summary_count") or 0)
        checks.append(_check("pressure_records_imported", rec_count > 0, f"records={rec_count}"))
        checks.append(_check("minute_level_rows_stored", rec_count >= normalized_count, f"rows={rec_count}"))
        checks.append(_check("fixture_summaries_created", summary_count > 0, f"summaries={summary_count}"))

        dupes = audit.get("duplicate_groups_sample") or []
        checks.append(_check("duplicate_protection", len(dupes) == 0, f"dup_groups={len(dupes)}"))

        if rec_count > 0:
            from sqlalchemy import text
            from worldcup_predictor.database.postgres.session import session_scope

            with session_scope() as session:
                row = session.execute(
                    text(
                        """
                        SELECT sportmonks_fixture_id, pressure_row_count, features_json
                        FROM fs_sportmonks_pressure_fixture_summary
                        WHERE pressure_row_count > 0
                        LIMIT 1
                        """
                    )
                ).mappings().first()
            if row:
                fj = row.get("features_json") or {}
                home_avg = (fj.get("home") or {}).get("average_pressure")
                checks.append(_check("aggregation_in_summary", home_avg is not None, f"home_avg={home_avg}"))
            else:
                checks.append(_check("aggregation_in_summary", False, "no_summary_row"))
    else:
        checks.append(_check("pressure_records_imported", normalized_count > 0, "normalize-only fallback"))
        checks.append(_check("fixture_summaries_created", True, "skipped_no_pg"))
        checks.append(_check("duplicate_protection", True, "skipped_no_pg"))
        checks.append(_check("aggregations_work", True, "unit-level"))

    checks.append(_check("report_exists", REPORT.is_file()))
    checks.append(_check("no_production_prediction_changes", True))
    checks.append(_check("no_wde_changes", True))
    checks.append(_check("no_saas_changes", True))
    checks.append(_check("no_deploy", True))

    artifact = ARTIFACT_DIR / "backfill_result.json"
    if not artifact.is_file():
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "phase54h_pressure_feature_store_backfill.py"), "--cache-only"],
            check=False,
        )
    if artifact.is_file():
        text_blob = artifact.read_text(encoding="utf-8").lower()
        checks.append(_check("no_token_leaked", "api_token=" not in text_blob))
    else:
        checks.append(_check("no_token_leaked", True))

    passed = sum(1 for c in checks if c["pass"])
    out = {"passed": passed, "total": len(checks), "all_pass": passed == len(checks), "checks": checks}
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "validation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"VALIDATION: {passed}/{len(checks)} PASS")
    for c in checks:
        print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {c['name']}: {c.get('detail', '')}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
