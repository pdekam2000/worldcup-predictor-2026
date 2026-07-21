#!/usr/bin/env python3
"""Owner-approved official freeze for selected aligned fixtures (NOT auto-run).

Reuses earliest immutable freezes; never overwrites. Requires --owner-approved.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from worldcup_predictor.research.forward_aligned_scan.constants import ARTIFACT_ROOT, TIER_A, TIER_S


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Freeze selected aligned fixtures (owner approval required)")
    p.add_argument("--scan-id", required=True)
    p.add_argument("--tier", choices=["S", "A", "S+A"], default="S")
    p.add_argument("--owner-approved", action="store_true", help="required explicit owner approval")
    p.add_argument("--dry-run", action="store_true", default=True, help="default dry-run; pass --execute to freeze")
    p.add_argument("--execute", action="store_true", help="actually attempt freeze capture")
    args = p.parse_args(argv)

    if not args.owner_approved:
        print("REFUSED: --owner-approved is required. No freezes created.")
        return 2

    summary_path = ROOT / ARTIFACT_ROOT / args.scan_id / "summary.json"
    if not summary_path.is_file():
        print(f"MISSING_SCAN {summary_path}")
        return 2
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    sel = summary.get("selection") or {}
    rows = []
    if args.tier in {"S", "S+A"}:
        rows.extend(sel.get("tier_s") or [])
    if args.tier in {"A", "S+A"}:
        rows.extend(sel.get("tier_a") or [])

    print(f"SCAN_ID={args.scan_id}")
    print(f"CANDIDATES={len(rows)}")
    for r in rows:
        print(
            f"  fixture={r.get('fixture_id')} {r.get('home_team')} vs {r.get('away_team')} "
            f"tier={r.get('alignment_tier')} kickoff={r.get('kickoff_vienna')}"
        )

    if not args.execute:
        print("DRY_RUN: no freezes created. Re-run with --execute --owner-approved to proceed.")
        print("Policy: reuse earliest immutable freeze; never overwrite.")
        return 0

    # Execute path: reuse bridge freeze capture without overwrite
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.database.connection import connect
    from worldcup_predictor.forward_evaluation.bridge import capture_forward_eval_freeze_from_stored
    from worldcup_predictor.forward_evaluation.db import connect_eval_db

    settings = get_settings()
    prod = connect(settings.sqlite_path)
    eval_conn = connect_eval_db()
    results = []
    try:
        for r in rows:
            fid = int(r["fixture_id"])
            # Prefer existing earliest freeze
            existing = eval_conn.execute(
                "SELECT prediction_id, frozen_at, content_hash, payload_hash FROM frozen_predictions "
                "WHERE fixture_id=? ORDER BY frozen_at ASC LIMIT 1",
                (fid,),
            ).fetchone()
            if existing:
                results.append(
                    {
                        "fixture_id": fid,
                        "status": "REUSED_EXISTING_EARLIEST_FREEZE",
                        "prediction_id": existing["prediction_id"],
                        "frozen_at": existing["frozen_at"],
                        "hash": existing["content_hash"] or existing["payload_hash"],
                    }
                )
                continue
            # Only create if stored prediction exists and gates pass — bridge handles idempotency
            try:
                out = capture_forward_eval_freeze_from_stored(
                    fixture_id=fid,
                    prod_conn=prod,
                    eval_conn=eval_conn,
                )
                results.append({"fixture_id": fid, "status": "CAPTURE_ATTEMPTED", "result": str(out)})
            except Exception as exc:
                results.append({"fixture_id": fid, "status": "FAILED", "error": f"{type(exc).__name__}:{exc}"})
    finally:
        prod.close()
        eval_conn.close()

    out_path = ROOT / ARTIFACT_ROOT / args.scan_id / "owner_freeze_attempt.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"wrote={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
