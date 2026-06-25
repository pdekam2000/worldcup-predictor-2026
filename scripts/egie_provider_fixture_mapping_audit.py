#!/usr/bin/env python3
"""Phase API-F — fixture identity mapping audit for EGIE PL backtest cohort."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT = ROOT / "artifacts" / "egie_provider_fixture_mapping_audit.json"


def main() -> int:
    from worldcup_predictor.egie.backfill.fixture_mapping_audit import audit_pl_fixture_mapping

    report = audit_pl_fixture_mapping(limit=400)
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    summary = {
        "fixture_count": report.get("fixture_count"),
        "mapping_success_rate_pct": report.get("mapping_success_rate_pct"),
        "pl_odds_aligned_count": report.get("pl_odds_aligned_count"),
        "mapping_status_counts": report.get("mapping_status_counts"),
        "artifact": str(ARTIFACT),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
