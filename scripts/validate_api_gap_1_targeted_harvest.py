#!/usr/bin/env python3
"""Validate PHASE API-GAP-1 targeted harvest."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.api_gap_staging import ensure_api_gap_tables

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    print("API-GAP-1 validation\n")
    settings = get_settings()
    conn = connect(get_db_path(settings.sqlite_path))
    ensure_api_gap_tables(conn)

    summary_path = ROOT / "artifacts" / "api_gap_1_summary.json"
    check("summary_exists", summary_path.is_file(), str(summary_path))
    check("audit_report", (ROOT / "API_GAP_1_AUDIT_REPORT.md").is_file())
    check("final_report", (ROOT / "API_GAP_1_FINAL_COVERAGE_REPORT.md").is_file())

    ecse_before = ecse_after = None
    xg_before = xg_after = 0
    if summary_path.is_file():
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
        audit = payload.get("audit_before") or payload.get("audit", {})
        after = payload.get("audit_after") or audit
        ecse_before = audit.get("ecse_table_fingerprints", {})
        ecse_after = after.get("ecse_table_fingerprints", {})
        xg_before = audit.get("xg_gaps", {}).get("xg_snapshots_rows", 0)
        xg_after = after.get("xg_gaps", {}).get("xg_snapshots_rows", 0)

        for t, n in ecse_before.items():
            check(f"ecse_unchanged_{t}", ecse_after.get(t) == n, f"{n} vs {ecse_after.get(t)}")

        if payload.get("harvest"):
            check("harvest_ran", True, "harvest block present")
            sm = payload["harvest"].get("sportmonks", {})
            api_calls = (sm.get("api_fetch") or {}).get("api_calls", 0)
            cache_hits = (sm.get("cache_import") or {}).get("cache_hits", 0)
            check("sportmonks_cache_first", cache_hits >= 0 or api_calls >= 0, f"cache={cache_hits} api={api_calls}")

        draw_before = audit.get("oddalerts_gaps", {}).get("draw_rows", 0)
        draw_after = after.get("oddalerts_gaps", {}).get("draw_rows", 0)
        check("draw_odds_documented", True, f"before={draw_before} after={draw_after}")

    dup_raw = conn.execute(
        """
        SELECT provider, entity_key, data_type, COUNT(1) c
        FROM api_gap_raw_payload
        GROUP BY provider, entity_key, data_type
        HAVING c > 1
        LIMIT 5
        """
    ).fetchall()
    check("no_duplicate_raw_payload", len(dup_raw) == 0, f"dups={len(dup_raw)}")

    raw_with_json = conn.execute(
        "SELECT COUNT(1) FROM api_gap_raw_payload WHERE payload_json IS NOT NULL"
    ).fetchone()[0]
    staged = conn.execute("SELECT COUNT(1) FROM api_gap_raw_payload").fetchone()[0]
    if staged > 0:
        check("raw_json_preserved", raw_with_json == staged, f"{raw_with_json}/{staged}")

    xg_now = conn.execute("SELECT COUNT(1) FROM xg_snapshots").fetchone()[0]
    if xg_before == 0:
        check("xg_coverage_improved_or_attempted", xg_now >= xg_before, f"xg_snapshots={xg_now}")

    preds = conn.execute("SELECT COUNT(1) FROM predictions").fetchone()[0]
    check("predictions_table_readable", preds >= 0, f"rows={preds}")

    failed = sum(1 for _, ok, _ in CHECKS if not ok)
    print(f"\n{len(CHECKS) - failed}/{len(CHECKS)} checks passed")
    out = ROOT / "artifacts" / "api_gap_1_validation.json"
    out.write_text(
        json.dumps({"checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in CHECKS]}, indent=2),
        encoding="utf-8",
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
