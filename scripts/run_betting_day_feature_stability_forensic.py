"""Research runner: Betting Day Feature Stability & OOD Forensic Audit.

Research only. No retune. No deploy. Does not modify Similarity Overlay / PM / Coverage / Insurance.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from worldcup_predictor.research.betting_day_similarity.feature_stability.pipeline import (
    run_feature_stability_forensic,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Feature stability / OOD forensic audit")
    p.add_argument("--output-dir", type=str, default="")
    p.add_argument("--max-historical", type=int, default=1200)
    p.add_argument("--max-ablation-features", type=int, default=18)
    p.add_argument("--seed", type=int, default=20260731)
    args = p.parse_args(argv)

    result = run_feature_stability_forensic(
        output_dir=Path(args.output_dir) if args.output_dir else None,
        max_historical=int(args.max_historical),
        max_ablation_features=int(args.max_ablation_features),
        seed=int(args.seed),
    )
    print(
        json.dumps(
            {
                "status": result.get("status"),
                "primary_root_cause": result.get("primary_root_cause"),
                "false_ood_count": result.get("false_ood_count"),
                "minimal_stable_feature_count": result.get("minimal_stable_feature_count"),
                "top_unstable_features": (result.get("top_unstable_features") or [])[:8],
                "artifact_dir": result.get("artifact_dir"),
                "deployment_status": "NOT_DEPLOYED",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
