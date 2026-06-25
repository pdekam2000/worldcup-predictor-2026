#!/usr/bin/env python3
"""Run EGIE paid-provider strategy backtest (A–F)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT = ROOT / "artifacts" / "egie_paid_provider_backtest.json"


def main() -> int:
    from worldcup_predictor.egie.backtest.paid_provider_runner import PaidProviderEgieBacktestRunner

    runner = PaidProviderEgieBacktestRunner()
    result = runner.run(competition_key="premier_league", limit=200)
    slim = {k: v for k, v in result.items() if k != "per_strategy_results"}
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(slim, indent=2, default=str), encoding="utf-8")
    (ARTIFACT.parent / "egie_paid_provider_backtest_full.json").write_text(
        json.dumps(result, indent=2, default=str),
        encoding="utf-8",
    )
    print(json.dumps(slim, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
