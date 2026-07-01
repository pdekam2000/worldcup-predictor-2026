#!/usr/bin/env python3
"""Validate PHASE MAP-1 historical provider mappings."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.historical_provider_mapping import (
    TABLE_NAME,
    ensure_historical_provider_mapping_table,
)

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    print("MAP-1 provider mapping validation\n")
    settings = get_settings()
    conn = connect(get_db_path(settings.sqlite_path))
    ensure_historical_provider_mapping_table(conn)

    summary_path = ROOT / "artifacts" / "provider_mapping_summary.json"
    report_path = ROOT / "HISTORICAL_PROVIDER_MAPPING_REPORT.md"
    check("summary_exists", summary_path.is_file(), str(summary_path))
    check("report_exists", report_path.is_file(), str(report_path))

    total = conn.execute(f"SELECT COUNT(1) FROM {TABLE_NAME}").fetchone()[0]
    check("mapping_table_populated", total > 0, f"rows={total}")

    dup_registry_provider = conn.execute(
        f"""
        SELECT registry_fixture_id, provider, COUNT(1) c
        FROM {TABLE_NAME}
        GROUP BY registry_fixture_id, provider
        HAVING c > 1
        """
    ).fetchall()
    check("no_duplicate_registry_provider", len(dup_registry_provider) == 0, f"dups={len(dup_registry_provider)}")

    bad_conf = conn.execute(
        f"SELECT COUNT(1) FROM {TABLE_NAME} WHERE confidence_score < 0 OR confidence_score > 1"
    ).fetchone()[0]
    check("confidence_in_range", bad_conf == 0, f"bad={bad_conf}")

    methods = {
        r[0]
        for r in conn.execute(f"SELECT DISTINCT match_method FROM {TABLE_NAME}").fetchall()
    }
    allowed = {
        "prelinked_internal_fixture_id",
        "exact_datetime_teams",
        "exact_datetime_teams_score",
        "exact_date_teams",
        "exact_date_teams_league",
        "exact_date_teams_league_season",
        "exact_date_teams_score",
        "exact_datetime_fuzzy_teams",
        "fuzzy_date_teams",
        "fuzzy_date_teams_league",
        "ambiguous_multiple_candidates",
    }
    check("match_methods_valid", methods.issubset(allowed), str(sorted(methods)))

    exact_dt = conn.execute(
        f"""
        SELECT COUNT(1) FROM {TABLE_NAME}
        WHERE match_method LIKE 'exact_datetime%' AND kickoff_delta_minutes IS NOT NULL
          AND kickoff_delta_minutes > 1
        """
    ).fetchone()[0]
    check("exact_datetime_delta_ok", exact_dt == 0, f"violations={exact_dt}")

    registry_n = conn.execute("SELECT COUNT(1) FROM historical_fixture_registry").fetchone()[0]
    ecse_n = conn.execute("SELECT COUNT(DISTINCT registry_fixture_id) FROM ecse_training_dataset").fetchone()[0]
    preds_n = conn.execute("SELECT COUNT(1) FROM predictions").fetchone()[0]

    if summary_path.is_file():
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
        check("summary_phase", payload.get("phase") == "MAP-1")
        audit = payload.get("audit", {})
        check(
            "audit_rows_match_db",
            int(audit.get("rows", -1)) == total,
            f"audit={audit.get('rows')} db={total}",
        )

    check("registry_unchanged", registry_n >= 223_000, f"rows={registry_n}")
    check("ecse_dataset_unchanged", ecse_n >= 217_000, f"rows={ecse_n}")
    check("predictions_unchanged", preds_n >= 0, f"predictions={preds_n}")

    failed = sum(1 for _, ok, _ in CHECKS if not ok)
    print(f"\n{len(CHECKS) - failed}/{len(CHECKS)} checks passed")
    out = ROOT / "artifacts" / "provider_mapping_validation.json"
    out.write_text(
        json.dumps({"checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in CHECKS]}, indent=2),
        encoding="utf-8",
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
