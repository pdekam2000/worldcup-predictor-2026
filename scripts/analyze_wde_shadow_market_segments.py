#!/usr/bin/env python3
"""PHASE WDE-SHADOW-3 Part C — Test-split segment analysis for O/U2.5 and BTTS."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.research.wde_shadow_market_segments import (
    DEFAULT_MODEL_DIR,
    SEGMENT_ARTIFACT,
    run_segment_analysis,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", default=str(DEFAULT_MODEL_DIR))
    args = parser.parse_args()

    result = run_segment_analysis(Path(args.model_dir))
    print(json.dumps({"test_rows": result.get("test_rows"), "status": result.get("status", "ok")}, indent=2))
    print(f"Written: {SEGMENT_ARTIFACT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
