"""Phase 4 research runner: forensic audit + historical replay + forward shadow.

Research-only. No freeze mutation. No production deploy.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from worldcup_predictor.research.bet_coverage_optimizer.phase4.pipeline import run_phase4


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="BCO Phase 4 Forward Shadow Audit research runner")
    p.add_argument("--top-n", type=int, choices=[8, 10, 12], default=8)
    p.add_argument(
        "--real-odds-json",
        type=str,
        default="worldcup_predictor/research/bet_coverage_optimizer/fixtures/interwetten_three_fixture_markets.json",
    )
    p.add_argument("--total-budget", type=float, default=400.0)
    p.add_argument("--main-budget-ratio", type=float, default=0.80)
    p.add_argument("--max-insurance-tickets", type=int, default=15)
    p.add_argument("--stake-mode", choices=["equal", "score_weighted", "kelly_research"], default="score_weighted")
    p.add_argument("--historical-n", type=int, default=120)
    p.add_argument("--output-dir", type=str, default="")
    args = p.parse_args(argv)

    result = run_phase4(
        top_n=int(args.top_n),
        real_odds_json=args.real_odds_json,
        total_budget=float(args.total_budget),
        main_budget_ratio=float(args.main_budget_ratio),
        max_insurance_tickets=int(args.max_insurance_tickets),
        stake_mode=str(args.stake_mode),
        historical_n=int(args.historical_n),
        output_dir=Path(args.output_dir) if args.output_dir else None,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "output_dir": result["output_dir"],
                "success_criteria": result["validation"]["success_criteria"],
                "n_insurance_tickets": result["validation"]["n_insurance_tickets"],
                "deployment_status": "NOT_DEPLOYED",
            },
            indent=2,
        )
    )
    return 0 if result["status"].endswith("READY") and "BLOCKED" not in result["status"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
