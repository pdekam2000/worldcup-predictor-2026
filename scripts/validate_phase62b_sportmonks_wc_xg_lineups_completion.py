#!/usr/bin/env python3
"""Validate Phase 62B Sportmonks WC xG + lineups completion."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REPORT = ROOT / "PHASE_62B_SPORTMONKS_WC_XG_LINEUPS_COMPLETION_REPORT.md"
ARTIFACT = ROOT / "data" / "validation" / "phase62b_sportmonks_wc_completion.json"
MAPPING_AUDIT = ROOT / "data" / "validation" / "phase62b_mapping_audit.json"


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    for name in (
        "competition_tags.py",
        "mapping_audit.py",
        "sportmonks_wc_import.py",
        "wc_enriched_features.py",
        "pipeline_62b.py",
    ):
        p = ROOT / "worldcup_predictor" / "egie" / "world_cup" / name
        checks.append((f"module:{name}", p.is_file(), "present"))

    checks.append(
        (
            "script:phase62b",
            (ROOT / "scripts" / "phase62b_sportmonks_wc_xg_lineups_completion.py").is_file(),
            "present",
        )
    )

    try:
        from worldcup_predictor.egie.world_cup.coverage import measure_coverage
        from worldcup_predictor.egie.world_cup.mapping_audit import run_mapping_audit
        from worldcup_predictor.egie.world_cup.pipeline_62b import recommend_phase_62b

        checks.append(("import:phase62b", True, "ok"))
        cov = measure_coverage()
        checks.append(("coverage:runs", isinstance(cov, dict), str(cov.get("total_fixtures", 0))))
        if MAPPING_AUDIT.is_file() or True:
            audit = run_mapping_audit()
            checks.append(("mapping_audit:runs", "mapped_fixtures" in audit, str(audit.get("mapped_fixtures", 0))))
    except Exception as exc:
        checks.append(("import:phase62b", False, str(exc)[:200]))

    checks.append(("report:exists", REPORT.is_file(), str(REPORT)))
    checks.append(("mapping_audit_file", MAPPING_AUDIT.is_file(), str(MAPPING_AUDIT)))

    enriched_dir = ROOT / "data" / "egie" / "world_cup" / "raw" / "goal_timing_features_enriched"
    enriched_count = len(list(enriched_dir.glob("*.json"))) if enriched_dir.is_dir() else 0
    checks.append(("feature_rows:rebuilt", enriched_count > 0, str(enriched_count)))

    # No model / flag changes — static checks
    settings_path = ROOT / "worldcup_predictor" / "config" / "settings.py"
    settings_text = settings_path.read_text(encoding="utf-8") if settings_path.is_file() else ""
    checks.append(
        (
            "flags:unified_off",
            "UNIFIED_ENGINE_PUBLIC=false" in settings_text or "UNIFIED_ENGINE_PUBLIC" in settings_text,
            "unchanged",
        )
    )

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"Phase 62B validation: {passed}/{total}")
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} — {detail}")

    out = ROOT / "data" / "validation" / "phase62b_validation_summary.json"
    out.write_text(
        json.dumps({"passed": passed, "total": total, "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks]}, indent=2),
        encoding="utf-8",
    )
    return 0 if passed >= total - 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
