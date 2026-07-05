#!/usr/bin/env python3
"""ECSE-MARKET-PRIOR-SHADOW-1 runner — research only."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.research.ecse_market_prior.runner import finalize_report, run_shadow_research
import sqlite3


def main() -> int:
    settings = get_settings()
    conn = sqlite3.connect(f"file:{settings.sqlite_path}?mode=ro", uri=True)
    payload = run_shadow_research(conn, max_eval_per_split=1200)
    conn.close()

    # validation hook
    from worldcup_predictor.research.ecse_market_prior.validation import validate_shadow_payload

    validation = validate_shadow_payload(payload, settings.sqlite_path)
    payload["validation"] = validation
    artifact = ROOT / "artifacts" / "ecse_market_prior_shadow_1" / "shadow_research_payload.json"
    artifact.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    rec = finalize_report(payload, report_path=ROOT / "ECSE_MARKET_PRIOR_SHADOW_1_REPORT.md")
    print(json.dumps({"recommendation": rec, "validation_pass": validation.get("passed")}, indent=2))
    print("ECSE_MARKET_PRIOR_SHADOW_1_COMPLETE")
    return 0 if validation.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
