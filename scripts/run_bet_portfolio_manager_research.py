"""Research runner for Bet Portfolio Manager.

Research-only. No freeze mutation. No production deploy.
Does not modify WDE/ECSE/Coverage/Insurance.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from worldcup_predictor.research.bet_portfolio_manager.pipeline import run_portfolio_manager


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Bet Portfolio Manager research runner")
    p.add_argument("--bankroll", type=float, default=500.0)
    p.add_argument(
        "--mode",
        choices=["equal", "score_weighted", "risk_weighted", "fractional_kelly"],
        default="score_weighted",
    )
    p.add_argument("--min-historical", type=int, default=600)
    p.add_argument("--max-historical", type=int, default=1200)
    p.add_argument("--output-dir", type=str, default="")
    args = p.parse_args(argv)

    result = run_portfolio_manager(
        bankroll=float(args.bankroll),
        mode=str(args.mode),
        min_historical=int(args.min_historical),
        max_historical=int(args.max_historical),
        output_dir=Path(args.output_dir) if args.output_dir else None,
    )
    imp = (result.get("historical") or {}).get("improvement") or {}
    print(
        json.dumps(
            {
                "status": result["status"],
                "output_dir": result["output_dir"],
                "n_fixtures": result["n_fixtures"],
                "roi_delta": imp.get("roi_delta"),
                "drawdown_delta": imp.get("drawdown_delta"),
                "skipped_days": imp.get("average_skipped_bad_days"),
                "sample_action": result["day_eval"]["decision"].get("action"),
                "deployment_status": "NOT_DEPLOYED",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
