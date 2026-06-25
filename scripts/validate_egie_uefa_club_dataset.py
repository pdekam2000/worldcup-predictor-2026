#!/usr/bin/env python3
"""Validate Phase API-H UEFA club EGIE dataset."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    checks = []
    mapping = json.loads((ROOT / "artifacts" / "uefa_fixture_mapping.json").read_text(encoding="utf-8"))
    checks.append(("fixture_mapping", mapping.get("fixture_count", 0) > 0))
    survival = ROOT / "data" / "egie" / "uefa_club" / "uefa_survival_dataset.parquet"
    checks.append(("survival_parquet", survival.is_file()))
    backtest = json.loads((ROOT / "artifacts" / "uefa_club_backtest.json").read_text(encoding="utf-8"))
    checks.append(("backtest_completed", backtest.get("status") == "completed"))
    checks.append(("no_wc_pl_fixtures", all(
        f.get("league_id") not in (732, 8) for f in (mapping.get("fixtures") or [])
    )))
    passed = sum(1 for _, ok in checks if ok)
    print(f"VALIDATION: {passed}/{len(checks)} PASS")
    for name, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
