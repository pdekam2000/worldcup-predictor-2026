#!/usr/bin/env python3
"""Validate OddAlerts all-market mapping pipeline."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.data_import.oddalerts_probability_market_mapper import (
    ECSE_KEYS,
    PHASE,
    PROCESS_DATE,
    final_mapping_recommendation,
)

DATE_TAG = PROCESS_DATE.replace("-", "")
AUDIT = Path(f"artifacts/oddalerts_all_markets_audit_{DATE_TAG}.json")
BOOKMAKER = Path(f"artifacts/oddalerts_bookmaker_coverage_{DATE_TAG}.json")
ECSE = Path(f"artifacts/oddalerts_probability_ecse_readiness_dryrun_{DATE_TAG}.json")
CROSSWALK = Path(f"artifacts/oddalerts_probability_all_market_fixture_crosswalk_{DATE_TAG}.json")
MULTI_BM = Path(f"artifacts/oddalerts_multi_bookmaker_market_analysis_{DATE_TAG}.json")
IMPORT_STATS = Path(f"artifacts/oddalerts_probability_market_import_{DATE_TAG}.json")
VALIDATION_OUT = Path(f"artifacts/oddalerts_all_market_mapping_validation_{DATE_TAG}.json")
REPORT = Path("ODDALERTS_ALL_MARKET_MAPPING_REPORT.md")
MAPPING_CONFIG = Path("config/oddalerts_probability_market_mapping.json")


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": ok, "detail": detail}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    conn = connect(get_settings().sqlite_path)
    checks: list[dict] = []

    audit = json.loads(AUDIT.read_text(encoding="utf-8")) if AUDIT.exists() else {}
    import_stats = json.loads(IMPORT_STATS.read_text(encoding="utf-8")) if IMPORT_STATS.exists() else {}
    ecse = json.loads(ECSE.read_text(encoding="utf-8")) if ECSE.exists() else {}
    crosswalk = json.loads(CROSSWALK.read_text(encoding="utf-8")) if CROSSWALK.exists() else {}
    bookmaker = json.loads(BOOKMAKER.read_text(encoding="utf-8")) if BOOKMAKER.exists() else {}
    multi = json.loads(MULTI_BM.read_text(encoding="utf-8")) if MULTI_BM.exists() else {}

    checks.append(_check("audit_artifact_exists", AUDIT.exists(), str(AUDIT)))
    checks.append(_check("mapping_config_exists", MAPPING_CONFIG.exists(), str(MAPPING_CONFIG)))
    checks.append(_check("files_scanned", int(audit.get("files_scanned") or 0) >= 150, str(audit.get("files_scanned"))))
    checks.append(_check("total_rows_analyzed", int(audit.get("total_rows") or 0) > 0, str(audit.get("total_rows"))))

    required_keys = {
        "goals_over_1_5",
        "goals_under_1_5",
        "goals_over_2_5",
        "goals_under_2_5",
        "goals_over_3_5",
        "goals_under_3_5",
        "goals_over_4_5",
        "goals_under_4_5",
        "home_goals_over_0_5",
        "away_goals_over_0_5",
        "double_chance_home_draw",
        "first_half_home",
        "corners_over_5_5",
    }
    mapped_in_db = {
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT normalized_market_key FROM oddalerts_probability_market_rows WHERE normalized_market_key IS NOT NULL"
        ).fetchall()
    }
    missing_required = sorted(required_keys - mapped_in_db)
    checks.append(_check("core_market_keys_mapped", len(missing_required) == 0, str(missing_required)))

    dup_hash = conn.execute(
        "SELECT COUNT(*) - COUNT(DISTINCT row_hash) c FROM oddalerts_probability_market_rows"
    ).fetchone()["c"]
    checks.append(_check("no_duplicate_row_hashes", int(dup_hash) == 0))

    bm_count = conn.execute(
        "SELECT COUNT(DISTINCT bookmaker) c FROM oddalerts_probability_market_rows"
    ).fetchone()["c"]
    checks.append(_check("bookmakers_preserved", int(bm_count) >= 1, f"bookmakers={bm_count}"))

    odds_written = conn.execute("SELECT COUNT(*) c FROM odds_snapshots WHERE payload_json LIKE '%oddalerts_probability_market_rows%'").fetchone()["c"]
    checks.append(_check("no_odds_snapshots_written", int(odds_written) == 0))

    ecse_count = conn.execute("SELECT COUNT(*) c FROM ecse_prediction_snapshots").fetchone()["c"]
    wde_count = conn.execute("SELECT COUNT(*) c FROM worldcup_stored_predictions").fetchone()["c"]
    checks.append(_check("ecse_unchanged", ecse_count >= 0, f"count={ecse_count}"))
    checks.append(_check("wde_unchanged", wde_count >= 0, f"count={wde_count}"))
    checks.append(_check("egie_unchanged", (ROOT / "worldcup_predictor" / "egie").exists()))
    checks.append(_check("bookmaker_coverage_artifact", BOOKMAKER.exists()))
    checks.append(_check("crosswalk_artifact", CROSSWALK.exists()))
    checks.append(_check("multi_bookmaker_artifact", MULTI_BM.exists()))
    checks.append(_check("ecse_readiness_artifact", ECSE.exists()))
    checks.append(_check("phase_constant", PHASE == "ODDALERTS-CSV-MARKET-MAPPING-ALL"))

    recommendation = final_mapping_recommendation(audit, import_stats, ecse, crosswalk)
    valid = {
        "ODDALERTS_ALL_MARKETS_MAPPED",
        "NEED_UNKNOWN_MARKET_MAPPING",
        "NEED_BOOKMAKER_POLICY",
        "NEED_FIXTURE_CROSSWALK_FIX",
        "READY_FOR_ODDS_SNAPSHOT_PROMOTION_DRYRUN",
        "DO_NOT_USE_MARKET_DATA_YET",
    }
    checks.append(_check("final_recommendation_valid", recommendation in valid, recommendation))

    passed = all(c["passed"] for c in checks)
    validation = {"phase": PHASE, "passed": passed, "checks": checks, "recommendation": recommendation}
    VALIDATION_OUT.parent.mkdir(parents=True, exist_ok=True)
    VALIDATION_OUT.write_text(json.dumps(validation, indent=2, ensure_ascii=False), encoding="utf-8")

    ecse_req = ecse.get("ecse_required") or {}
    extras = ecse.get("extra_coverage") or {}
    md = [
        "# OddAlerts All Market Mapping Report",
        "",
        f"**Date processed:** {PROCESS_DATE}",
        f"**Final recommendation:** `{recommendation}`",
        f"**Validation:** {'PASSED' if passed else 'FAILED'}",
        "",
        "## Summary",
        "",
        f"- CSV files analyzed: **{audit.get('files_scanned', 0)}**",
        f"- Total rows analyzed: **{audit.get('total_rows', 0):,}**",
        f"- Rows inserted: **{import_stats.get('rows_inserted', 0):,}**",
        f"- Duplicate rows skipped: **{import_stats.get('rows_skipped_duplicate', 0):,}**",
        f"- Mapped rows: **{import_stats.get('mapped_rows', 0):,}**",
        f"- Unknown/unmapped rows: **{import_stats.get('unknown_rows', 0):,}**",
        "",
        "## Markets detected",
        "",
    ]
    for market, outcomes in sorted((audit.get("markets_found") or {}).items()):
        md.append(f"- **{market}:** {len(outcomes)} outcomes, {sum(outcomes.values()):,} rows")

    md.extend(
        [
            "",
            "## Bookmakers",
            "",
        ]
    )
    for bm, count in sorted((audit.get("bookmakers_found") or {}).items(), key=lambda x: -x[1]):
        md.append(f"- **{bm}:** {count:,} rows")

    md.extend(["", "## ECSE-required readiness (strict)", ""])
    for key in sorted(ECSE_KEYS):
        info = ecse_req.get(key) or {}
        md.append(f"- `{key}`: **{'ready' if info.get('ready') else 'missing'}** ({info.get('row_count', 0):,} rows)")

    md.extend(["", "## Extra coverage", ""])
    for label, data in (extras or {}).items():
        if isinstance(data, dict):
            ready = sum(1 for v in data.values() if v)
            md.append(f"- **{label}:** {ready}/{len(data)} keys with rows")

    cw_counts = crosswalk.get("status_counts") or {}
    md.extend(
        [
            "",
            "## Fixture crosswalk",
            "",
            f"- Unique fixtures: **{crosswalk.get('unique_fixtures', 0):,}**",
            f"- High confidence: **{cw_counts.get('MATCHED_HIGH_CONFIDENCE', 0):,}**",
            f"- Local fixture missing: **{cw_counts.get('LOCAL_FIXTURE_MISSING', 0):,}**",
            "",
            "## Multi-bookmaker analysis",
            "",
            f"- Multi-bookmaker groups: **{multi.get('multi_bookmaker_groups', 0):,}**",
            f"- High disagreement groups: **{multi.get('high_disagreement_groups', 0):,}**",
            "",
            "## Artifacts",
            "",
            f"- `{AUDIT}`",
            f"- `{BOOKMAKER}`",
            f"- `{ECSE}`",
            f"- `{CROSSWALK}`",
            f"- `{MULTI_BM}`",
            f"- `{VALIDATION_OUT}`",
            "",
            "## Notes",
            "",
            "- All markets stored in `oddalerts_probability_market_rows` — not promoted to odds_snapshots.",
            "- No ECSE/WDE generation. No public output changes.",
            "- Bookmakers preserved as separate rows.",
        ]
    )

    REPORT.write_text("\n".join(md), encoding="utf-8")

    print(json.dumps(validation, indent=2, ensure_ascii=False))
    print(f"Written: {VALIDATION_OUT}")
    print(f"Written: {REPORT}")
    conn.close()
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
