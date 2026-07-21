#!/usr/bin/env python3
"""Tier A → Tier S distance analysis from an existing forward aligned scan."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from worldcup_predictor.research.forward_aligned_scan.tier_a_near_s import run_analysis


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--scan-id", required=True)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    out = run_analysis(args.scan_id, root=ROOT)
    if args.json:
        slim = {
            "status": out["status"],
            "scan_id": out["scan_id"],
            "almost_tier_s_ranking": {
                k: {
                    "fixture_id": v["fixture_id"],
                    "match": v["match"],
                    "alignment_score": v["alignment_score"],
                    "gates_remaining": v["gates_remaining"],
                    "top5_mass": v["top5_mass"],
                    "tier_s_blocker": v["tier_s_blocker"],
                }
                for k, v in (out.get("almost_tier_s_ranking") or {}).items()
                if v
            },
            "owner_shortlist": out.get("owner_shortlist"),
            "refresh_high_priority": out.get("refresh_high_priority"),
            "outputs": out.get("outputs"),
        }
        print(json.dumps(slim, indent=2, ensure_ascii=False))
    else:
        print(f"STATUS={out['status']}")
        print(f"SCAN_ID={out['scan_id']}")
        for label in ("first", "second", "third", "fourth", "fifth"):
            a = (out.get("almost_tier_s_ranking") or {}).get(label)
            if a:
                print(f"{label.upper()}={a['fixture_id']} {a['match']} rem={a['gates_remaining']} mass={a['top5_mass']}")
        print(f"outputs={out.get('outputs')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
