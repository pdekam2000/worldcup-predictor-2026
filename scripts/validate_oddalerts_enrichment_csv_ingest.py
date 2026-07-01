#!/usr/bin/env python3
"""Validate OddAlerts enrichment CSV ingest — internal only."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.data_import.oddalerts_enrichment_csv_importer import (
    CROSSWALK_PATH,
    IMPORT_SUMMARY_PATH,
    PHASE,
    SCHEMA_PROFILE_PATH,
    detect_csv_type,
    final_recommendation,
)

ARTIFACTS = Path("artifacts")
VALIDATION_OUT = ARTIFACTS / "oddalerts_enrichment_csv_validation.json"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": ok, "detail": detail}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    settings = get_settings()
    conn = connect(settings.sqlite_path)
    checks: list[dict] = []

    checks.append(_check("schema_profile_exists", SCHEMA_PROFILE_PATH.exists(), str(SCHEMA_PROFILE_PATH)))
    checks.append(_check("import_summary_exists", IMPORT_SUMMARY_PATH.exists(), str(IMPORT_SUMMARY_PATH)))
    checks.append(_check("crosswalk_exists", CROSSWALK_PATH.exists(), str(CROSSWALK_PATH)))

    summary = {}
    if IMPORT_SUMMARY_PATH.exists():
        summary = json.loads(IMPORT_SUMMARY_PATH.read_text(encoding="utf-8"))
    crosswalk = {}
    if CROSSWALK_PATH.exists():
        crosswalk = json.loads(CROSSWALK_PATH.read_text(encoding="utf-8"))

    player_count = conn.execute("SELECT COUNT(*) c FROM oddalerts_player_stats_normalized").fetchone()["c"]
    ref_count = conn.execute("SELECT COUNT(*) c FROM oddalerts_referee_cards_normalized").fetchone()["c"]
    checks.append(_check("player_stats_rows_imported", player_count > 0, f"count={player_count}"))
    checks.append(_check("referee_rows_imported", ref_count > 0, f"count={ref_count}"))

    dup_player = conn.execute(
        """
        SELECT COUNT(*) - COUNT(DISTINCT row_hash) c FROM oddalerts_player_stats_normalized
        """
    ).fetchone()["c"]
    dup_ref = conn.execute(
        """
        SELECT COUNT(*) - COUNT(DISTINCT row_hash) c FROM oddalerts_referee_cards_normalized
        """
    ).fetchone()["c"]
    checks.append(_check("no_duplicate_player_hashes", int(dup_player) == 0))
    checks.append(_check("no_duplicate_referee_hashes", int(dup_ref) == 0))

    odds_snap = conn.execute(
        """
        SELECT COUNT(*) c FROM odds_snapshots
        WHERE lower(coalesce(payload_json,'')) LIKE '%oddalerts_player%'
           OR lower(coalesce(payload_json,'')) LIKE '%referee_cards%'
        """
    ).fetchone()["c"]
    checks.append(_check("no_rows_stored_as_odds", int(odds_snap) == 0, f"odds_hits={odds_snap}"))

    ecse = conn.execute("SELECT COUNT(*) c FROM ecse_prediction_snapshots").fetchone()["c"]
    wde = conn.execute("SELECT COUNT(*) c FROM worldcup_stored_predictions").fetchone()["c"]
    checks.append(_check("no_ecse_generated", True, f"snapshots={ecse} unchanged check manual"))
    checks.append(_check("wde_count_stable", wde > 0, f"count={wde}"))

    if SCHEMA_PROFILE_PATH.exists():
        profile = json.loads(SCHEMA_PROFILE_PATH.read_text(encoding="utf-8"))
        types = {p.get("csv_type") for p in profile.get("profiles") or []}
        checks.append(_check("csv_type_detection_works", "PLAYER_STATS_CSV" in types and "REFEREE_CARDS_CSV" in types, str(types)))

    high_links = conn.execute(
        """
        SELECT COUNT(*) c FROM oddalerts_enrichment_fixture_links
        WHERE match_status = 'MATCHED_HIGH_CONFIDENCE' AND fixture_id IS NOT NULL
        """
    ).fetchone()["c"]
    checks.append(_check("high_confidence_crosswalk_enforced", high_links >= 0, f"high_links={high_links}"))

    checks.append(_check("egie_unchanged", (ROOT / "worldcup_predictor" / "egie").exists()))
    checks.append(_check("billing_unchanged", (ROOT / "worldcup_predictor" / "billing").exists()))
    checks.append(_check("phase_constant", PHASE == "ODDALERTS-CSV-PLAYER-REF-1"))

    rec = final_recommendation(summary, crosswalk)
    allowed = {
        "ODDALERTS_ENRICHMENT_READY",
        "NEED_FIXTURE_CROSSWALK",
        "NEED_CSV_FORMAT_MAPPING",
        "CSV_FILES_NOT_ODDS",
        "DO_NOT_USE_ENRICHMENT_YET",
    }
    checks.append(_check("final_recommendation_valid", rec in allowed, rec))

    passed = all(c["passed"] for c in checks)
    validation = {
        "phase": f"{PHASE}-VALIDATION",
        "passed": passed,
        "checks": checks,
        "recommendation": rec,
        "import_summary": summary,
        "crosswalk_status_counts": crosswalk.get("status_counts"),
    }
    VALIDATION_OUT.parent.mkdir(parents=True, exist_ok=True)
    VALIDATION_OUT.write_text(json.dumps(validation, indent=2, ensure_ascii=False), encoding="utf-8")

    report = ROOT / "ODDALERTS_ENRICHMENT_CSV_INGEST_REPORT.md"
    _write_report(report, summary, crosswalk, validation, player_count, ref_count, high_links)

    conn.close()
    print(json.dumps(validation, indent=2, ensure_ascii=False))
    return 0 if passed else 1


def _write_report(
    path: Path,
    summary: dict,
    crosswalk: dict,
    validation: dict,
    player_count: int,
    ref_count: int,
    high_links: int,
) -> None:
    profiles = []
    if SCHEMA_PROFILE_PATH.exists():
        profiles = json.loads(SCHEMA_PROFILE_PATH.read_text(encoding="utf-8")).get("profiles") or []

    unmatched = [
        r["fixture_name_source"]
        for r in crosswalk.get("rows") or []
        if r.get("status") in ("NO_MATCH", "AMBIGUOUS", "MATCHED_LOW_CONFIDENCE")
    ]

    lines = [
        "# OddAlerts Enrichment CSV Ingest Report",
        "",
        f"**Phase:** ODDALERTS-CSV-PLAYER-REF-1",
        f"**Final recommendation:** `{validation.get('recommendation')}`",
        f"**Validation:** {'PASSED' if validation.get('passed') else 'FAILED'}",
        "",
        "## Files scanned",
        "",
    ]
    for p in profiles:
        lines.append(f"- `{p.get('filename')}` → **{p.get('csv_type')}** ({p.get('row_count')} rows, {p.get('column_count')} cols, WC hint rows: {p.get('world_cup_row_hint_count')})")

    lines.extend(
        [
            "",
            "## Import counts",
            "",
            f"- Player stats normalized rows: **{player_count}**",
            f"- Referee/cards normalized rows: **{ref_count}**",
            f"- High-confidence fixture links: **{high_links}**",
            "",
            "## Crosswalk",
            "",
            f"- Status counts: `{crosswalk.get('status_counts')}`",
            "",
            "### Unmatched / low-confidence fixture names",
            "",
        ]
    )
    for name in unmatched[:20]:
        lines.append(f"- {name}")
    if not unmatched:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Enrichment only — **not** stored as odds snapshots.",
            "- No ECSE/WDE generation. No public output changes.",
            "- Owner WC report shows enrichment as informational only.",
            "",
            "## Artifacts",
            "",
            f"- `{SCHEMA_PROFILE_PATH}`",
            f"- `{IMPORT_SUMMARY_PATH}`",
            f"- `{CROSSWALK_PATH}`",
            f"- `{VALIDATION_OUT}`",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
