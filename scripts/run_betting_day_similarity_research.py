"""Research runner: Betting Day Similarity Engine.

Research-only. No freeze mutation. No production deploy.
Does not modify WDE/ECSE/Coverage/Insurance/baseline PM/calibrated candidate.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from worldcup_predictor.research.betting_day_similarity.pipeline import (
    run_betting_day_similarity_research,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Betting Day Similarity Engine research runner")
    p.add_argument("--historical-days-path", type=str, default="")
    p.add_argument(
        "--method",
        choices=["euclidean", "manhattan", "cosine", "mahalanobis", "mixed"],
        default="mixed",
    )
    p.add_argument("--neighbors", type=int, default=10)
    p.add_argument("--regime-method", choices=["kmeans", "hierarchical", "gmm"], default="kmeans")
    p.add_argument("--output-dir", type=str, default="")
    p.add_argument("--forward-shadow", action="store_true", default=True)
    p.add_argument("--target-date", type=str, default="")
    p.add_argument("--policy", choices=["baseline", "calibrated", "both"], default="both")
    p.add_argument("--seed", type=int, default=20260731)
    p.add_argument("--max-historical", type=int, default=1200)
    args = p.parse_args(argv)

    result = run_betting_day_similarity_research(
        output_dir=Path(args.output_dir) if args.output_dir else None,
        method=str(args.method),
        neighbors=int(args.neighbors),
        regime_method=str(args.regime_method),
        max_historical=int(args.max_historical),
        seed=int(args.seed),
    )
    print(
        json.dumps(
            {
                "status": result.get("status"),
                "recommendation": result.get("recommendation"),
                "artifact_dir": result.get("artifact_dir"),
                "selected_similarity_method": result.get("selected_similarity_method"),
                "selected_k": result.get("selected_k"),
                "always_bet_roi": result.get("always_bet_roi"),
                "baseline_portfolio_roi": result.get("baseline_portfolio_roi"),
                "similarity_overlay_roi": result.get("similarity_overlay_roi"),
                "guardrails_passed": result.get("guardrails_passed"),
                "guardrails_failed": result.get("guardrails_failed"),
                "deployment_status": "NOT_DEPLOYED",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
