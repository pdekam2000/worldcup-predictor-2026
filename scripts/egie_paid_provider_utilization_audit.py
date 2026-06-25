#!/usr/bin/env python3
"""Audit paid API utilization for EGIE."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT = ROOT / "artifacts" / "egie_paid_provider_audit.json"


def main() -> int:
    from worldcup_predictor.egie.provider_features.audit import audit_egie_paid_provider_utilization

    report = audit_egie_paid_provider_utilization(competition_key="premier_league", limit=400)
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
