#!/usr/bin/env python3
"""Phase 2E — Forward evaluation scheduler CLI (dry-run default)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup_predictor.forward_evaluation.scheduler import run_forward_evaluation_cycle


def main() -> int:
    parser = argparse.ArgumentParser(description="Forward evaluation scheduler cycle")
    parser.add_argument("--apply", action="store_true", help="Perform writes (default is dry-run)")
    parser.add_argument("--fixture-limit", type=int, default=25)
    parser.add_argument("--lookback-hours", type=int, default=72)
    parser.add_argument(
        "--scope",
        choices=["production", "owner_shadow", "owner_daily", "all"],
        default="all",
    )
    parser.add_argument("--fixture-id", action="append", type=int, default=[])
    parser.add_argument("--output-json", type=Path, default=None)
    args = parser.parse_args()

    dry_run = not args.apply
    scope = None if args.scope == "all" else args.scope
    fixture_ids = args.fixture_id or None

    out = run_forward_evaluation_cycle(
        dry_run=dry_run,
        fixture_limit=args.fixture_limit,
        scope=scope,
        lookback_hours=args.lookback_hours,
        fixture_ids=fixture_ids,
    )

    output_path = args.output_json
    if output_path is None:
        suffix = "dry_run" if dry_run else "apply"
        output_path = ROOT / "artifacts" / f"forward_evaluation_cycle_{suffix}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")

    mode = "dry_run" if dry_run else "apply"
    print(
        json.dumps(
            {
                "run_id": out.get("run_id"),
                "mode": mode,
                "candidates_found": out.get("candidates_found"),
                "classifications": out.get("classifications"),
                "results_inserted": out.get("results_inserted"),
                "results_reused": out.get("results_reused"),
                "evaluations_inserted": out.get("evaluations_inserted"),
                "evaluations_reused": out.get("evaluations_reused"),
                "final_status": out.get("final_status"),
                "ledger_path": str(output_path),
            },
            indent=2,
        )
    )
    return 0 if out.get("final_status") != "FORWARD_EVALUATION_CYCLE_ALREADY_RUNNING" else 2


if __name__ == "__main__":
    raise SystemExit(main())
