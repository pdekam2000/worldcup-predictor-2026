#!/usr/bin/env python3
"""Re-emit / print report for an existing forward aligned scan."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from worldcup_predictor.research.forward_aligned_scan.constants import ARTIFACT_ROOT
from worldcup_predictor.research.forward_aligned_scan.store import write_report_markdown


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--scan-id", required=True)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    summary_path = ROOT / ARTIFACT_ROOT / args.scan_id / "summary.json"
    if not summary_path.is_file():
        print(f"MISSING {summary_path}")
        return 2
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    report = write_report_markdown(payload, root=ROOT)
    if args.json:
        print(json.dumps({"scan_id": args.scan_id, "report": report, "status": payload.get("status")}, indent=2))
    else:
        print(f"STATUS={payload.get('status')}")
        print(f"SCAN_ID={args.scan_id}")
        print(f"report={report}")
        sel = payload.get("selection") or {}
        for label, key in (("S", "tier_s"), ("A", "tier_a"), ("B", "tier_b")):
            rows = sel.get(key) or []
            print(f"TIER_{label}_n={len(rows)}")
            for r in rows:
                print(
                    f"  #{r.get('rank')} {r.get('fixture_id')} {r.get('home_team')} vs {r.get('away_team')} "
                    f"score={r.get('alignment_score')} wde={(r.get('directions') or {}).get('wde_decision')}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
