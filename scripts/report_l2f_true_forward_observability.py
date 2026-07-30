#!/usr/bin/env python3
"""Owner-only Phase 4 observability + readiness report (read-only)."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if (ROOT / ".env.production").exists() and not os.environ.get("APP_ENV"):
    os.environ["APP_ENV"] = "production"

from worldcup_predictor.research.infra_l2f_forward.observability import build_observability_report
from worldcup_predictor.research.infra_l2f_forward.readiness import evaluate_readiness


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-db", default="data/evaluation/forward_prediction_tracking.db")
    ap.add_argument("--fi-db", default="data/football_intelligence.db")
    ap.add_argument("--out", default=None)
    ap.add_argument("--include-readiness", action="store_true", default=True)
    args = ap.parse_args()
    fi = sqlite3.connect(args.fi_db)
    fi.row_factory = sqlite3.Row
    ev = sqlite3.connect(args.eval_db)
    ev.row_factory = sqlite3.Row
    obs = build_observability_report(fi, ev)
    payload = {"observability": obs}
    if args.include_readiness:
        payload["readiness"] = evaluate_readiness(fi, ev, obs=obs)
    text = json.dumps(payload, indent=2, default=str)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
