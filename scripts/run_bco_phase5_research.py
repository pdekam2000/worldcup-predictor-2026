"""Phase 5 research runner: long-term scientific validation.

Research-only. No freeze mutation. No production deploy.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from worldcup_predictor.research.bet_coverage_optimizer.phase5.pipeline import run_phase5


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="BCO Phase 5 long-term validation research runner")
    p.add_argument("--min-fixtures", type=int, default=1000)
    p.add_argument("--max-historical", type=int, default=2500)
    p.add_argument("--top-n", type=int, choices=[8, 10, 12], default=8)
    p.add_argument("--source-db", type=str, default="")
    p.add_argument("--forward-db", type=str, default="")
    p.add_argument("--output-dir", type=str, default="")
    args = p.parse_args(argv)

    result = run_phase5(
        min_fixtures=int(args.min_fixtures),
        max_historical=int(args.max_historical),
        top_n=int(args.top_n),
        source_db=Path(args.source_db) if args.source_db else None,
        forward_db=Path(args.forward_db) if args.forward_db else None,
        output_dir=Path(args.output_dir) if args.output_dir else None,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "output_dir": result["output_dir"],
                "n_fixtures": result["n_fixtures"],
                "n_leagues": result["league"].get("n_leagues"),
                "readiness_score": result["readiness"].get("readiness_score"),
                "recommendation": result["readiness"].get("recommendation"),
                "deployment_status": "NOT_DEPLOYED",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
