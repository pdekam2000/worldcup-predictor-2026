"""Research runner: Top10-to-5 Profit-Aware Coverage Optimizer.

Research only. NOT DEPLOYED. No production writes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from worldcup_predictor.research.top10_to_5_optimizer.pipeline import run_top10_to_5_research


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Top10-to-5 profit-aware research optimizer")
    p.add_argument("--fixture-id", type=int, action="append", dest="fixture_ids_single")
    p.add_argument("--fixture-ids", type=int, nargs="+", default=None)
    p.add_argument("--top10-source", choices=["canonical", "exact_v2", "consensus"], default="consensus")
    p.add_argument("--real-odds-json", type=str, default="")
    p.add_argument("--real-odds-csv", type=str, default="")
    p.add_argument("--fixture-budget", type=float, default=25.0)
    p.add_argument(
        "--stake-mode",
        choices=[
            "equal_stake",
            "probability_weighted",
            "profit_floor",
            "minmax_loss",
            "score_weighted",
            "fractional_kelly_research",
        ],
        default="profit_floor",
    )
    p.add_argument("--coupon-ticket-cap", type=int, choices=[25, 40, 64, 125], default=25)
    p.add_argument("--output-dir", type=str, default="")
    p.add_argument("--forward-shadow", action="store_true")
    p.add_argument("--historical-backtest", action="store_true", default=True)
    p.add_argument("--no-historical-backtest", action="store_true")
    args = p.parse_args(argv)

    ids = list(args.fixture_ids or [])
    if args.fixture_ids_single:
        ids.extend(args.fixture_ids_single)
    ids = ids or None

    result = run_top10_to_5_research(
        fixture_ids=ids,
        real_odds_json=args.real_odds_json or None,
        real_odds_csv=args.real_odds_csv or None,
        output_dir=Path(args.output_dir) if args.output_dir else None,
        top10_source=args.top10_source,
        stake_mode=args.stake_mode,
        fixture_budget=args.fixture_budget,
        coupon_ticket_cap=args.coupon_ticket_cap,
        forward_shadow=bool(args.forward_shadow),
        historical_backtest=not bool(args.no_historical_backtest),
    )
    print(
        json.dumps(
            {
                "status": result.get("status"),
                "top10_to_5_roi": result.get("top10_to_5_roi"),
                "exact3_roi": result.get("exact3_roi"),
                "average_profitable_covered_mass": result.get("average_profitable_covered_mass"),
                "artifact_dir": result.get("artifact_dir"),
                "deployment_status": "NOT_DEPLOYED",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
