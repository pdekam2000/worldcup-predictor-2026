#!/usr/bin/env python3
"""Run forward multi-day aligned fixture scan (ephemeral research)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from worldcup_predictor.research.forward_aligned_scan.runner import run_forward_aligned_scan


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Forward aligned fixture scan (research ephemeral)")
    p.add_argument("--from-date", default=None, help="Vienna start date YYYY-MM-DD|today|tomorrow")
    p.add_argument("--days", type=int, default=6, help="Calendar days 3–6 (default 6)")
    p.add_argument("--scope", default="owner")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--max-fixtures", type=int, default=None, help="optional cap for debugging")
    p.add_argument(
        "--fixture-ids",
        default=None,
        help="Comma-separated fixture IDs to refresh within the date window (new scan ID)",
    )
    p.add_argument(
        "--compare-to-scan",
        default=None,
        help="Baseline scan ID for immutable comparison (does not modify baseline)",
    )
    p.add_argument(
        "--skip-isolation-preflight",
        action="store_true",
        help="Skip isolation preflight (not recommended)",
    )
    args = p.parse_args(argv)

    out = run_forward_aligned_scan(
        from_date=args.from_date,
        days=args.days,
        scope=args.scope,
        dry_run=args.dry_run,
        root=ROOT,
        max_fixtures=args.max_fixtures,
        fixture_ids=args.fixture_ids,
        compare_to_scan=args.compare_to_scan,
        skip_isolation_preflight=args.skip_isolation_preflight,
    )
    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    else:
        disc = out.get("discovery") or {}
        sel = out.get("selection") or {}
        counts = sel.get("counts") or {}
        print(f"STATUS={out.get('status')}")
        print(f"FRESH_STATUS={out.get('fresh_status')}")
        print(f"SCAN_ID={out.get('scan_id')}")
        rng = disc.get("range") or {}
        print(f"RANGE={rng.get('from_date')}..{rng.get('to_date')} days={rng.get('days')}")
        print(f"VIENNA={out.get('generated_at_vienna')}")
        print(
            f"raw={disc.get('raw_discovered')} included={disc.get('included_count')} "
            f"excluded={disc.get('excluded_count')} predicted={out.get('predicted_count')}"
        )
        print(
            f"selected S/A/B={counts.get('tier_s_selected')}/{counts.get('tier_a_selected')}/{counts.get('tier_b_selected')} "
            f"rejected={counts.get('rejected')}"
        )
        print(f"probs_persisted={out.get('probabilities_persisted_all_predicted')}")
        print(f"canonical_unchanged={out.get('canonical_state_unchanged')}")
        zw = out.get("zero_write_integrity") or {}
        print(zw.get("proof_text") or zw)
        if out.get("baseline_comparison"):
            bc = out["baseline_comparison"]
            print(f"baseline={bc.get('baseline_scan_id')} labels={bc.get('summary_labels')}")
        outs = out.get("outputs") or {}
        if outs.get("fresh_report"):
            print(f"fresh_report={outs.get('fresh_report')}")
        if outs.get("comparison_report"):
            print(f"comparison_report={outs.get('comparison_report')}")
        if outs.get("artifact_dir"):
            print(f"artifacts={outs.get('artifact_dir')}")
    blocked = {
        "BLOCKED_RESEARCH_ISOLATION_NOT_PROVEN",
        "FORWARD_ALIGNED_FRESH_RESCAN_BLOCKED",
        "FORWARD_ALIGNED_FRESH_RESCAN_VALIDATION_FAILED",
        "FORWARD_ALIGNED_SCAN_VALIDATION_FAILED",
    }
    return 2 if out.get("status") in blocked or out.get("fresh_status") in blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
