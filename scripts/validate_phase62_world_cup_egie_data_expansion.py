#!/usr/bin/env python3
"""Validate Phase 62 World Cup EGIE data expansion artifacts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REPORT = ROOT / "PHASE_62_WORLD_CUP_EGIE_DATA_EXPANSION_REPORT.md"
ARTIFACT = ROOT / "data" / "validation" / "phase62_world_cup_egie_expansion.json"


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    pkg = ROOT / "worldcup_predictor" / "egie" / "world_cup"
    for name in (
        "config.py",
        "sqlite_loader.py",
        "api_football_ingest.py",
        "sportmonks_ingest.py",
        "sportmonks_fixture_list.py",
        "coverage.py",
        "wc_feature_builder.py",
        "wc_survival_builder.py",
        "egie_feature_rows.py",
        "survival_rebuild.py",
        "pipeline.py",
    ):
        checks.append((f"module:{name}", (pkg / name).is_file(), "present"))

    script = ROOT / "scripts" / "phase62_world_cup_egie_data_expansion.py"
    checks.append(("script:phase62", script.is_file(), "present"))

    try:
        from worldcup_predictor.egie.world_cup.coverage import measure_coverage, recommend_phase
        from worldcup_predictor.egie.world_cup.wc_feature_builder import build_wc_timing_features
        from worldcup_predictor.egie.world_cup.wc_survival_builder import build_wc_survival_rows

        checks.append(("import:coverage", True, "ok"))
        checks.append(("import:wc_builders", True, "ok"))
        cov = measure_coverage()
        checks.append(("coverage:runs", isinstance(cov, dict), str(cov.get("total_fixtures", 0))))
        rec = recommend_phase(cov)
        checks.append(
            (
                "recommend:runs",
                rec in {"BLOCKED", "READY_FOR_PHASE_61B_RERUN", "NEED_MORE_IMPORTS", "PROVIDER_LIMITED"},
                rec,
            )
        )
    except Exception as exc:
        checks.append(("coverage:runs", False, str(exc)[:200]))

    checks.append(("report:exists", REPORT.is_file(), str(REPORT)))

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"Phase 62 validation: {passed}/{total}")
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} — {detail}")

    summary = {"passed": passed, "total": total, "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks]}
    out = ROOT / "data" / "validation" / "phase62_validation_summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
