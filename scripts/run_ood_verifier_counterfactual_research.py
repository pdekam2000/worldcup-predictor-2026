"""Research runner: OOD Verifier Counterfactual Research.

Read-only. No new models. No retune. No deploy.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from worldcup_predictor.research.betting_day_similarity.ood_counterfactual.pipeline import (
    run_ood_counterfactual_research,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="OOD Verifier counterfactual research")
    p.add_argument("--output-dir", type=str, default="")
    p.add_argument("--max-historical", type=int, default=1200)
    p.add_argument("--seed", type=int, default=20260731)
    args = p.parse_args(argv)

    result = run_ood_counterfactual_research(
        output_dir=Path(args.output_dir) if args.output_dir else None,
        max_historical=int(args.max_historical),
        seed=int(args.seed),
    )
    print(
        json.dumps(
            {
                "status": result.get("status"),
                "decision": result.get("decision"),
                "original_roi": result.get("original_roi"),
                "counterfactual_roi": result.get("counterfactual_roi"),
                "perfect_ood_roi": result.get("perfect_ood_roi"),
                "recovered_profit": result.get("recovered_profit"),
                "n_false_ood": result.get("n_false_ood"),
                "artifact_dir": result.get("artifact_dir"),
                "deployment_status": "NOT_DEPLOYED",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
