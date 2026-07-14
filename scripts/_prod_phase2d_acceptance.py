#!/usr/bin/env python3
"""Phase 2D production controlled acceptance — small fixture set only."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / "worldcup_predictor").is_dir():
    ROOT = Path("/opt/worldcup-predictor")
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup_predictor.forward_evaluation.evaluation_service import evaluate_frozen_prediction
from worldcup_predictor.forward_evaluation.result_sync_service import sync_result_for_fixture


DEFAULT_FIXTURES = [
    # Frozen prematch fixtures (still NS on production 2026-07-14)
    1494204,
    1497629,
    1554381,
    1494208,
]

# Completed fixture without freeze — result-sync idempotency only
RESULT_SYNC_ONLY_FIXTURE = 1581821


def _snapshot_fixture(fid: int, *, allow_provider_fetch: bool = False) -> dict:
    sync1 = sync_result_for_fixture(fid, dry_run=False, allow_provider_fetch=allow_provider_fetch)
    sync2 = sync_result_for_fixture(fid, dry_run=False, allow_provider_fetch=False)
    eval1 = evaluate_frozen_prediction(fid, dry_run=False)
    eval2 = evaluate_frozen_prediction(fid, dry_run=False)
    dry_eval = evaluate_frozen_prediction(fid, dry_run=True)
    return {
        "fixture_id": fid,
        "result_sync_first": sync1,
        "result_sync_repeat": sync2,
        "evaluation_first": eval1,
        "evaluation_repeat": eval2,
        "evaluation_dry_run": dry_eval,
        "idempotent_result_sync": bool(sync2.get("reused")),
        "idempotent_evaluation": eval2.get("reason") == "already_evaluated",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", nargs="*", type=int, default=DEFAULT_FIXTURES)
    parser.add_argument("--result-sync-only", type=int, default=RESULT_SYNC_ONLY_FIXTURE)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts" / "phase2d_production_acceptance.json",
    )
    args = parser.parse_args()

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "note": "Controlled acceptance — no broad batch; frozen fixtures may be prematch-only.",
        "result_sync_idempotency_fixture": _snapshot_fixture(
            int(args.result_sync_only), allow_provider_fetch=False
        ),
        "frozen_fixtures": [_snapshot_fixture(fid, allow_provider_fetch=False) for fid in args.fixtures],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "fixture_count": len(args.fixtures)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
