#!/usr/bin/env python3
"""Owner-only L2-F Canonical vs Shadow research preview (read-only)."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from worldcup_predictor.config.env_loading import project_root
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.research.infra_l2f_forward.research_preview import build_research_preview


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Owner research preview: CANONICAL vs SHADOW_RESEARCH_ONLY")
    ap.add_argument("--vienna-date", default=None, help="Europe/Vienna calendar date YYYY-MM-DD")
    ap.add_argument("--league", default=None)
    ap.add_argument("--fixture-id", type=int, default=None)
    ap.add_argument("--true-forward-status", default=None, help="true_forward | success | skipped | blocked | failed")
    ap.add_argument("--agreement", default=None, help="Agreement classification filter")
    ap.add_argument("--no-bet", choices=["true", "false"], default=None)
    ap.add_argument("--out", default=None, help="Write JSON to path")
    args = ap.parse_args(argv)

    settings = get_settings()
    fi = sqlite3.connect(str(settings.sqlite_path))
    fi.row_factory = sqlite3.Row
    # prod == fi for this project (football_intelligence.db)
    prod = fi
    ev = sqlite3.connect(str(project_root() / "data/evaluation/forward_prediction_tracking.db"))
    ev.row_factory = sqlite3.Row
    try:
        no_bet = None if args.no_bet is None else (args.no_bet == "true")
        report = build_research_preview(
            prod=prod,
            fi=fi,
            eval_conn=ev,
            vienna_date=args.vienna_date,
            league=args.league,
            fixture_id=args.fixture_id,
            true_forward_status=args.true_forward_status,
            agreement_classification=args.agreement,
            no_bet=no_bet,
        )
    finally:
        fi.close()
        ev.close()

    text = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"wrote {out} count={report.get('count')}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
