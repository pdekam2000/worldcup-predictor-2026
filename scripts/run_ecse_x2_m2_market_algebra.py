#!/usr/bin/env python3
"""PHASE ECSE-X2-M2 — Market algebra equation miner."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_x2_m2.build import baseline_table_row_count
from worldcup_predictor.research.ecse_x2_m2.miner import run_market_algebra_miner

SUMMARY_PATH = ROOT / "artifacts" / "ecse_x2_m2_equation_rankings.json"
REPORT_PATH = ROOT / "ECSE_X2_M2_MARKET_ALGEBRA_REPORT.md"


def _report_md(payload: dict, baseline_before: int) -> str:
    lines = [
        "# ECSE-X2-M2 — Market Algebra Equation Miner",
        "",
        f"**Phase:** ECSE-X2-M2  ",
        f"**Method:** `{payload.get('method_version')}`  ",
        f"**Equations tested:** {payload.get('equations_tested', 0)}  ",
        f"**Equations accepted:** {payload.get('equations_accepted', 0)}  ",
        "",
        "## Goal",
        "",
        "Search hidden mathematical relationships between prematch odds markets that improve",
        "ECSE exact-score ranking via quantile-conditioned reorder rules (train 70% / test 30%).",
        "",
        "## Baseline (temporal test slice)",
        "",
    ]
    b = payload.get("baseline_test_overall") or {}
    lines.extend(
        [
            f"- Fixtures: **{b.get('n', 0):,}**",
            f"- Top-1: **{b.get('top1_hit_rate_pct', 0)}%**",
            f"- Top-3: **{b.get('top3_hit_rate_pct', 0)}%**",
            f"- Top-5: **{b.get('top5_hit_rate_pct', 0)}%**",
            f"- Log loss: **{b.get('avg_log_loss', 0)}**",
            "",
            "## Top 20 equations (ranked)",
            "",
            "| Rank | Equation | Test n | Top-1 Δ | Top-3 Δ | Top-5 Δ | LogLoss Δ | Status |",
            "|------|----------|--------|---------|---------|---------|-----------|--------|",
        ]
    )
    for i, row in enumerate(payload.get("top_equations") or [], start=1):
        d = row.get("delta") or {}
        status = row.get("reject_reason") or "accepted"
        lines.append(
            f"| {i} | `{row.get('label')}` | {row.get('test_n', 0):,} | "
            f"{d.get('top1_hit_rate_pct', 0):+.4f} | {d.get('top3_hit_rate_pct', 0):+.4f} | "
            f"{d.get('top5_hit_rate_pct', 0):+.4f} | {d.get('avg_log_loss', 0):+.6f} | {status} |"
        )

    lines.extend(
        [
            "",
            "## Rejection rules",
            "",
            "- Train sample < 5,000",
            "- Test sample < 3,000",
            "- Log loss worsens by > 0.005",
            "- No OOS top-3 lift when log loss worsens",
            "- Improvement concentrated in < 3 leagues (n≥800)",
            "",
            "## Safety",
            "",
            f"- Baseline `ecse_score_distributions` rows unchanged: **{baseline_before:,}**",
            "- No API calls, no retraining, no deployment",
            "- Prematch odds only in reorder (results used for evaluation only)",
            "",
            f"## Artifact",
            "",
            f"- `{SUMMARY_PATH.as_posix()}`",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    settings = get_settings()
    conn = connect(get_db_path(settings.sqlite_path))
    try:
        baseline_before = baseline_table_row_count(conn)
        mine = run_market_algebra_miner(conn)
        baseline_after = baseline_table_row_count(conn)
    finally:
        conn.close()

    if baseline_before != baseline_after:
        print("ERROR: baseline table modified", file=sys.stderr)
        return 2

    payload = mine.to_dict()
    payload["all_results"] = mine.all_results
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    REPORT_PATH.write_text(_report_md(payload, baseline_before), encoding="utf-8")

    print(json.dumps(payload, indent=2, default=str))
    print(f"\nWrote {SUMMARY_PATH}")
    print(f"Wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
