#!/usr/bin/env python3
"""Report true-forward cohort status (Phase 1 hook + Phase 3 accumulation)."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.research.infra_l2f_forward.true_forward_report import true_forward_summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-db", default="data/evaluation/forward_prediction_tracking.db")
    ap.add_argument("--fi-db", default="data/football_intelligence.db")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    fi = sqlite3.connect(args.fi_db)
    fi.row_factory = sqlite3.Row
    ev = sqlite3.connect(args.eval_db)
    ev.row_factory = sqlite3.Row
    report = true_forward_summary(fi, ev)
    text = json.dumps(report, indent=2, default=str)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
