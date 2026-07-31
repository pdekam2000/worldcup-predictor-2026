"""Research runner: Portfolio Manager threshold calibration audit.

Research-only. No freeze mutation. No production deploy.
Does not modify WDE/ECSE/Coverage/Insurance/baseline PM policy.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.pipeline import (
    run_threshold_calibration,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="PM threshold calibration research runner")
    p.add_argument("--min-historical", type=int, default=600)
    p.add_argument("--max-historical", type=int, default=1200)
    p.add_argument("--max-candidates", type=int, default=48)
    p.add_argument("--output-dir", type=str, default="")
    args = p.parse_args(argv)

    result = run_threshold_calibration(
        min_historical=int(args.min_historical),
        max_historical=int(args.max_historical),
        max_candidates=int(args.max_candidates) if args.max_candidates > 0 else None,
        output_dir=Path(args.output_dir) if args.output_dir else None,
    )
    print(
        json.dumps(
            {
                "status": result.get("status"),
                "recommendation": result.get("recommendation"),
                "artifact_dir": result.get("artifact_dir"),
                "always_bet_roi": result.get("always_bet_roi"),
                "baseline_managed_roi": result.get("baseline_managed_roi"),
                "calibrated_holdout_roi": result.get("calibrated_holdout_roi"),
                "guardrails_passed": list(((result.get("guardrails") or {}).get("passed") or {}).keys()),
                "guardrails_failed": list(((result.get("guardrails") or {}).get("failed") or {}).keys()),
                "deployment_status": "NOT_DEPLOYED",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
