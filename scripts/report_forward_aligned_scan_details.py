#!/usr/bin/env python3
"""Generate owner-facing details package for an existing forward aligned scan."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from worldcup_predictor.research.forward_aligned_scan.details import generate_details_package


def _run_validator(scan_id: str) -> dict:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_forward_aligned_fixture_scan.py"), "--scan-id", scan_id],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    total = failed = None
    for line in out.splitlines():
        if line.startswith("TOTAL="):
            # TOTAL=109 FAILED=0
            parts = line.replace("FAILED=", " ").replace("TOTAL=", "").split()
            try:
                total = int(parts[0])
                failed = int(parts[1]) if len(parts) > 1 else None
            except (ValueError, IndexError):
                pass
    return {
        "exit_code": proc.returncode,
        "total": total,
        "failed": failed,
        "ok": proc.returncode == 0 and (failed == 0 if failed is not None else proc.returncode == 0),
        "tail": "\n".join(out.splitlines()[-5:]),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--scan-id", required=True)
    p.add_argument("--json", action="store_true")
    p.add_argument("--skip-validator", action="store_true")
    args = p.parse_args(argv)

    result = generate_details_package(args.scan_id, root=ROOT)
    validator = None
    if not args.skip_validator:
        validator = _run_validator(args.scan_id)
        result["validation"]["validator_summary"] = (
            f"TOTAL={validator.get('total')} FAILED={validator.get('failed')} exit={validator.get('exit_code')}"
        )
        result["base_validator"] = validator
        # persist updated validation with validator summary
        art = ROOT / "artifacts" / "research" / "forward_aligned_fixture_scan" / args.scan_id
        (art / "details_validation_report.json").write_text(
            json.dumps(result["validation"], indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        if not validator.get("ok"):
            result["status"] = "FORWARD_ALIGNED_SCAN_DETAILS_VALIDATION_FAILED"

    if args.json:
        slim = {
            "status": result["status"],
            "scan_id": result["scan_id"],
            "validation": result["validation"],
            "base_validator": result.get("base_validator"),
            "owner": result["owner"],
            "rankings": {
                "directional_fixture_ids": [r["fixture_id"] for r in result["rankings"]["directional"]],
                "exact_score_fixture_ids": [r["fixture_id"] for r in result["rankings"]["exact_score"]],
                "low_risk_fixture_ids": [r["fixture_id"] for r in result["rankings"]["low_risk"]],
                "tier_b_best_alignment_ids": [r["fixture_id"] for r in result["rankings"]["tier_b_best_alignment"]],
                "tier_b_best_mass_ids": [r["fixture_id"] for r in result["rankings"]["tier_b_best_mass"]],
            },
            "outputs": result["outputs"],
            "zero_write": result["zero_write"],
        }
        print(json.dumps(slim, indent=2, ensure_ascii=False, default=str))
    else:
        print(f"STATUS={result['status']}")
        print(f"SCAN_ID={result['scan_id']}")
        print(f"DETAILS_CHECKS={result['validation'].get('passed_count')}/{result['validation'].get('total')}")
        if result.get("base_validator"):
            print(f"BASE_VALIDATOR={result['base_validator'].get('tail')}")
        print(f"full_report={result['outputs']['full_report']}")
        print(f"owner_summary={result['outputs']['owner_summary']}")
        for e in (result["owner"].get("best_available") or []):
            print(f"BEST {e['fixture_id']} {e['match']}")
    return 0 if result["status"] == "FORWARD_ALIGNED_SCAN_DETAILS_COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
