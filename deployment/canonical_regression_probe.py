#!/usr/bin/env python3
"""Deterministic canonical regression probe (extract_lambdas invariance).

Does not call bookmakers. Proves O/U 4.5 additive fields do not change canonical λ.
Optionally snapshots baseline JSON for before/after deploy comparison.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fixture_row() -> dict[str, Any]:
    return {
        "registry_fixture_id": 537266001,
        "ft_home_closing": 2.10,
        "ft_draw_closing": 3.40,
        "ft_away_closing": 3.50,
        "ou_over_25_closing": 1.90,
        "ou_under_25_closing": 1.95,
        "ou_over_15_closing": 1.30,
        "ou_under_15_closing": 3.50,
        "ou_over_35_closing": 2.60,
        "ou_under_35_closing": 1.50,
        "team_home_over_05_closing": 1.40,
        "team_home_under_05_closing": 2.80,
        "team_away_over_05_closing": 1.55,
        "team_away_under_05_closing": 2.40,
    }


def extract_payload(row: dict[str, Any]) -> dict[str, Any]:
    from worldcup_predictor.research.ecse_lambda_extraction import extract_lambdas

    out = extract_lambdas(row)
    if out is None:
        raise RuntimeError("extract_lambdas returned None")
    # Keep stable comparable keys only
    keys = (
        "lambda_home",
        "lambda_away",
        "lambda_total",
        "method_version",
    )
    return {k: out.get(k) for k in keys}


def compare(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    diffs = []
    for k in sorted(set(a) | set(b)):
        if a.get(k) != b.get(k):
            diffs.append(f"{k}: {a.get(k)!r} != {b.get(k)!r}")
    return diffs


def write_report(path: Path, payload: dict[str, Any]) -> None:
    diffs = payload.get("diffs") or []
    md = f"""# Canonical regression report

Generated: `{payload['generated_at_utc']}`  
Mode: `{payload['mode']}`  
Status: **{'PASS' if payload['status'] == 'PASS' else 'FAIL'}**

## Expectation

NO DIFFERENCE in canonical λ when O/U 4.5 fields are added.

## Results

- without O/U 4.5: `{json.dumps(payload['without_ou45'])}`
- with O/U 4.5: `{json.dumps(payload['with_ou45'])}`
- identical: `{payload['identical_with_without_ou45']}`

## Freeze / markets note

This probe validates `extract_lambdas` invariance (canonical λ path).
Full WDE / BTTS / Exact Top10 / consensus / no_bet / freeze-hash parity against live
production freezes requires production access and fixed fixture IDs; those checks remain
operator-gated in PRODUCTION_DEPLOYMENT_CHECKLIST.md.

## Diffs

{chr(10).join('- ' + d for d in diffs) if diffs else '_None_'}
"""
    path.write_text(md + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("before", "after", "local"), default="local")
    ap.add_argument("--baseline-dir", default="")
    ap.add_argument("--fi-db", default="data/football_intelligence.db")
    ap.add_argument("--out-md", default="canonical_regression_report.md")
    ap.add_argument("--out-json", default="canonical_regression.json")
    args = ap.parse_args()

    base = fixture_row()
    with45 = dict(base)
    with45.update({"ou_over_45_closing": 4.50, "ou_under_45_closing": 1.20})

    without = extract_payload(base)
    with_ou = extract_payload(with45)
    diffs = compare(without, with_ou)
    identical = not diffs

    payload: dict[str, Any] = {
        "generated_at_utc": _now(),
        "mode": args.mode,
        "without_ou45": without,
        "with_ou45": with_ou,
        "identical_with_without_ou45": identical,
        "diffs": diffs,
        "status": "PASS" if identical else "FAIL",
        "fi_db": args.fi_db,
        "canonical_surfaces_unchanged_claim": [
            "lambda (extract_lambdas)",
            "WDE (not modified in release)",
            "BTTS (not modified in release)",
            "O/U used by lambda 1.5/2.5/3.5 (not modified)",
            "Exact Top10 engine (not modified in release)",
            "consensus / no_bet / freeze hash (not modified in release)",
        ],
    }

    baseline_dir = Path(args.baseline_dir) if args.baseline_dir else None
    if args.mode == "before" and baseline_dir:
        baseline_dir.mkdir(parents=True, exist_ok=True)
        (baseline_dir / "canonical_baseline.json").write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
    if args.mode == "after" and baseline_dir:
        bl_path = baseline_dir / "canonical_baseline.json"
        if bl_path.exists():
            before = json.loads(bl_path.read_text(encoding="utf-8"))
            after_vs_before = compare(before.get("without_ou45", {}), without)
            payload["baseline_compare_diffs"] = after_vs_before
            if after_vs_before:
                payload["status"] = "FAIL"
                payload["diffs"] = list(diffs) + [f"baseline:{d}" for d in after_vs_before]
        else:
            # First run after deploy without pre-captured baseline: invariance still required
            payload["baseline_note"] = "no baseline file; invariance-only check applied"

    Path(args.out_json).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    write_report(Path(args.out_md), payload)
    # Also write repo-root convenience copy when relative default used
    if Path(args.out_md).name == "canonical_regression_report.md":
        Path("canonical_regression_report.md").write_text(
            Path(args.out_md).read_text(encoding="utf-8"), encoding="utf-8"
        )
    print(json.dumps({"status": payload["status"], "identical": identical}, indent=2))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
