#!/usr/bin/env python3
"""Two-fixture forward shadow cycle — collect / freeze / evaluate / report (no betting)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.database.migrations import ensure_schema_compat
from worldcup_predictor.research.two_fixture_forward_shadow.cycle import run_cycle


def main() -> int:
    ap = argparse.ArgumentParser(description="Two-fixture forward shadow (owner-only, no betting)")
    ap.add_argument(
        "--jobs",
        default="all",
        help="Comma-separated: collect,freeze,evaluate,report,all",
    )
    args = ap.parse_args()
    jobs = [j.strip() for j in args.jobs.split(",") if j.strip()]
    settings = get_settings()
    conn = connect(settings.sqlite_path)
    ensure_schema_compat(conn)
    result = run_cycle(conn, jobs=jobs)
    out = ROOT / "artifacts" / "two_fixture_forward_shadow" / "last_cycle.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"lock": result.get("lock"), "jobs": list((result.get("jobs") or {}).keys()), "obs": result.get("observability")}, indent=2, default=str))
    return 0 if result.get("lock") != "busy" else 2


if __name__ == "__main__":
    raise SystemExit(main())
