#!/usr/bin/env python3
"""Evaluate finished fixtures from a forward aligned scan (confirmed FT only)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from worldcup_predictor.research.forward_aligned_scan.evaluate import evaluate_scan


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--scan-id", required=True)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    out = evaluate_scan(args.scan_id, root=ROOT)
    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    else:
        print(f"SCAN_ID={out.get('scan_id')}")
        print(f"confirmed_n={out.get('confirmed_n')} pending_n={out.get('pending_n')}")
        ov = out.get("overall") or {}
        for k in ("wde", "ecse_top1_dir", "ecse_top5_maj", "exact_top5", "agreement_rule"):
            block = ov.get(k) or {}
            print(f"{k}={block.get('successes')}/{block.get('n')}={block.get('rate_pct')}%")
        gate = out.get("promotion_gate") or {}
        print(f"promotion_eligible={gate.get('eligible_for_promotion_review')} auto_promote={gate.get('auto_promote')}")
    return 0 if out.get("status") != "MISSING_SCAN" else 2


if __name__ == "__main__":
    raise SystemExit(main())
