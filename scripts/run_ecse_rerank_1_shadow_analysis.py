#!/usr/bin/env python3
"""ECSE-RERANK-1 — Shadow re-rank analysis (read-only DB, artifact output only)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.research.ecse_rerank.runner import run_shadow_analysis

PHASE = "ECSE-RERANK-1"


def main() -> int:
    parser = argparse.ArgumentParser(description="ECSE-RERANK-1 shadow analysis")
    parser.add_argument("--db-path", default=None, help="SQLite path (default: settings)")
    parser.add_argument("--artifacts-dir", default=str(ROOT / "artifacts"))
    args = parser.parse_args()

    print(f"{PHASE} shadow analysis (read-only, no DB writes)\n")
    result = run_shadow_analysis(db_path=args.db_path, artifacts_dir=args.artifacts_dir)
    payload = result["payload"]
    print(json.dumps(
        {
            "phase": PHASE,
            "shadow_only": True,
            "match_count": payload["match_count"],
            "finished_count": payload["finished_count"],
            "baseline_audit": payload["baseline_audit"],
            "summary_segments": list(payload["summary"]["segments"].keys()),
            "json_path": result["json_path"],
            "jsonl_path": result["jsonl_path"],
        },
        indent=2,
    ))
    print(f"\nWrote {result['json_path']}")
    print(f"Wrote {result['jsonl_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
