#!/usr/bin/env python3
"""Validation for ECSE-MARKET-PRIOR-SHADOW-1 shadow research."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.research.ecse_market_prior.validation import validate_shadow_payload


def main() -> int:
    payload_path = ROOT / "artifacts" / "ecse_market_prior_shadow_1" / "shadow_research_payload.json"
    if not payload_path.exists():
        print(json.dumps({"passed": False, "error": "payload missing — run run_ecse_market_prior_shadow_1.py first"}))
        return 1
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    result = validate_shadow_payload(payload, get_settings().sqlite_path)
    out = ROOT / "artifacts" / "ecse_market_prior_shadow_1" / "validation_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"artifact": str(out), "passed": result["passed"]}, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
