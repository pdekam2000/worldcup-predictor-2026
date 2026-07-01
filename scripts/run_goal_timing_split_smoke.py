#!/usr/bin/env python3
"""PHASE GT-1 — Goal timing split smoke run (8 ECSE-LIVE fixtures)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.goal_timing_split.runner import run_goal_timing_split_smoke

REPORT_PATH = ROOT / "GOAL_TIMING_SPLIT_SMOKE_REPORT.md"
ARTIFACT_PATH = ROOT / "artifacts" / "goal_timing_split_smoke.json"


def _pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{float(value) * 100:.1f}%"


def _write_report(payload: dict) -> None:
    lines = [
        "# GOAL TIMING SPLIT — Smoke Report (GT-1)",
        "",
        f"**Phase:** GT-1  ",
        f"**Mode:** Internal research — ECSE-LIVE-1 smoke fixtures  ",
        f"**Status:** {payload.get('status', 'ok')}  ",
        f"**Model:** `{payload.get('model_version', 'GT-1-v1')}`  ",
        "",
        "> Probabilistic research outputs only — not guaranteed predictions.",
        "",
        "## Summary",
        "",
        f"- Targets: **{payload.get('targets', 0)}**",
        f"- Predicted: **{payload.get('predicted', 0)}**",
        f"- Inserted: **{payload.get('inserted', 0)}**",
        f"- Already exists (idempotent): **{payload.get('already_exists', 0)}**",
        f"- Insufficient data: **{payload.get('insufficient', 0)}**",
        "",
        "## Fixture Results",
        "",
        "| Match | Fixture | Side | Window | Tier | Home 0–30 | Away 0–30 | Home 31+ | Away 31+ | No goal |",
        "|-------|---------|------|--------|------|-----------|-----------|----------|----------|---------|",
    ]
    for row in payload.get("results") or []:
        lines.append(
            "| {match} | {fid} | {side} | {win} | {tier} | {h0} | {a0} | {h1} | {a1} | {ng} |".format(
                match=row.get("match", "—"),
                fid=row.get("fixture_id") or "—",
                side=row.get("recommended_side") or row.get("status") or "—",
                win=row.get("recommended_window") or "—",
                tier=row.get("confidence_tier") or "—",
                h0=_pct(row.get("p_home_0_30")),
                a0=_pct(row.get("p_away_0_30")),
                h1=_pct(row.get("p_home_31_plus")),
                a1=_pct(row.get("p_away_31_plus")),
                ng=_pct(row.get("p_no_goal")),
            )
        )

    lines.extend(
        [
            "",
            "## Method (brief)",
            "",
            "- ECSE λ_home / λ_away baseline for first-goal team share",
            "- Total λ + O/U / BTTS odds adjust scoring likelihood",
            "- Early vs late split from EGIE/historical priors (default ~43% in 0–30)",
            "- Confidence tiers A/B/C from data quality + probability spread",
            "",
            "## Safety",
            "",
            "- No WDE / EGIE / ECSE source table writes",
            "- No public API or UI exposure",
            "- Repeat run skips existing `fixture_id` + `model_version` rows",
            "",
            "## Artifacts",
            "",
            f"- `{ARTIFACT_PATH.as_posix()}`",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="GT-1 goal timing split smoke")
    parser.add_argument("--dry-run", action="store_true", help="Predict without DB insert")
    args = parser.parse_args()

    settings = get_settings()
    conn = connect(get_db_path(settings.sqlite_path))
    try:
        report = run_goal_timing_split_smoke(conn, dry_run=args.dry_run)
    finally:
        conn.close()

    payload = report.to_dict()
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload)

    print(json.dumps(payload, indent=2, default=str))
    print(f"\nWrote {ARTIFACT_PATH}")
    print(f"Wrote {REPORT_PATH}")
    return 0 if payload.get("status") in {"ok", "insufficient_data"} else 1


if __name__ == "__main__":
    sys.exit(main())
