#!/usr/bin/env python3
"""PHASE ECSE-X3-A — Composite market algebra shadow engine (research only)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_x2_m2.build import baseline_table_row_count
from worldcup_predictor.research.ecse_x3.constants import (
    ACCEPTED_SIGNALS,
    REJECTED_SIGNALS,
    SHADOW_ARTIFACT,
    SUMMARY_ARTIFACT,
)
from worldcup_predictor.research.ecse_x3.runner import run_composite_shadow

SUMMARY_PATH = ROOT / SUMMARY_ARTIFACT
SHADOW_PATH = ROOT / SHADOW_ARTIFACT
REPORT_PATH = ROOT / "ECSE_X3_A_COMPOSITE_MARKET_ALGEBRA_SHADOW_REPORT.md"


def _report_md(payload: dict, baseline_before: int) -> str:
    rec = payload.get("recommendation") or {}
    cov = payload.get("coverage") or {}
    lines = [
        "# ECSE-X3-A — Composite Market Algebra Shadow Report",
        "",
        "**Phase:** ECSE-X3-A  ",
        "**Mode:** Research/shadow only — no public prediction changes  ",
        f"**Recommendation:** **{rec.get('recommendation', 'PENDING')}**  ",
        "",
        "## Accepted ECSE-X2 signals (used in X3)",
        "",
    ]
    for s in ACCEPTED_SIGNALS:
        lines.append(f"- {s}")
    lines.extend(["", "## Rejected ECSE-X2 signals (excluded)", ""])
    for s in REJECTED_SIGNALS:
        lines.append(f"- {s}")

    lines.extend(
        [
            "",
            "## Coverage",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Eligible fixtures | {payload.get('eligible_n', 0):,} |",
            f"| Test holdout (30%) | {payload.get('test_n', 0):,} |",
            f"| ft_home coverage | {cov.get('ft_home_coverage_pct', 0)}% |",
            f"| Missing odds rate | {cov.get('missing_odds_rate_pct', 0)}% |",
            f"| ZZ2 flag rate | {cov.get('zz2_flag_rate_pct', 0)}% |",
            f"| ≥4 signal families | {cov.get('full_signal_families_pct', 0)}% |",
            f"| Baseline table rows (unchanged) | {baseline_before:,} |",
            "",
            "## Challenger comparison (overall test)",
            "",
            "| Method | Top-1 Δ | Top-3 Δ | Top-5 Δ | Top-10 Δ | LogLoss Δ | MRR Δ | Accepted |",
            "|--------|---------|---------|---------|----------|-----------|-------|----------|",
        ]
    )

    for method, data in (payload.get("method_results") or {}).items():
        if method == "champion":
            continue
        d = (data.get("overall") or {}).get("delta") or {}
        a = data.get("assessment") or {}
        lines.append(
            f"| {method} | {d.get('top1_delta_pp', 0):+.4f} | {d.get('top3_delta_pp', 0):+.4f} | "
            f"{d.get('top5_delta_pp', 0):+.4f} | {d.get('top10_delta_pp', 0):+.4f} | "
            f"{d.get('avg_log_loss', 0):+.6f} | {d.get('mean_reciprocal_rank', 0):+.6f} | "
            f"{a.get('accepted', False)} |"
        )

    best = rec.get("best_method")
    if best:
        lines.extend(["", f"## Fold stability ({best})", "", "| Fold | n | Top-1 Δ | Top-3 Δ | Top-5 Δ |", "|------|---|---------|---------|---------|"])
        for fr in (payload.get("method_results") or {}).get(best, {}).get("fold_results") or []:
            d = fr.get("delta") or {}
            lines.append(
                f"| {fr.get('fold')} | {fr.get('test_n', 0):,} | "
                f"{d.get('top1_delta_pp', 0):+.4f} | {d.get('top3_delta_pp', 0):+.4f} | "
                f"{d.get('top5_delta_pp', 0):+.4f} |"
            )

    lines.extend(["", "## Segment analysis (Top-5 Δ vs champion)", ""])
    for segment, seg in (payload.get("segment_results") or {}).items():
        lines.append(f"### {segment} (n={seg.get('n', 0):,})")
        for method, md in (seg.get("methods") or {}).items():
            d = md.get("delta") or {}
            lines.append(f"- **{method}**: top1 Δ={d.get('top1_delta_pp', 0):+.4f}, top5 Δ={d.get('top5_delta_pp', 0):+.4f}")
        lines.append("")

    lines.extend(["", "## Missing odds analysis", ""])
    for field, count in sorted((cov.get("missing_field_counts") or {}).items(), key=lambda x: -x[1])[:10]:
        lines.append(f"- `{field}`: {count:,}")

    lines.extend(["", "## Examples — composite improved rank", ""])
    for ex in payload.get("examples_improved") or []:
        lines.append(f"- Fixture {ex.get('fixture_id')}: actual {ex.get('actual')}, baseline rank {ex.get('baseline_rank')} → {ex.get(f'{best}_rank')}")

    lines.extend(["", "## Examples — composite worsened rank", ""])
    for ex in payload.get("examples_worsened") or []:
        lines.append(f"- Fixture {ex.get('fixture_id')}: actual {ex.get('actual')}, baseline rank {ex.get('baseline_rank')} → {ex.get(f'{best}_rank')}")

    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- No public prediction output changes",
            "- No ECSE baseline table changes",
            "- Phi/Fibonacci logic not used (archived X2 research only)",
            "- Shadow artifact only",
            "",
            "## Artifacts",
            "",
            f"- `{SHADOW_ARTIFACT}`",
            f"- `{SUMMARY_ARTIFACT}`",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    settings = get_settings()
    conn = connect(get_db_path(settings.sqlite_path))
    try:
        before = baseline_table_row_count(conn)
        if SHADOW_PATH.exists():
            SHADOW_PATH.unlink()
        payload = run_composite_shadow(conn, artifact_path=SHADOW_PATH)
        after = baseline_table_row_count(conn)
    finally:
        conn.close()

    if before != after:
        print("ERROR: baseline table modified", file=sys.stderr)
        return 2

    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    REPORT_PATH.write_text(_report_md(payload, before), encoding="utf-8")

    print(json.dumps(payload.get("recommendation"), indent=2))
    print(f"\nWrote {SHADOW_PATH}")
    print(f"Wrote {SUMMARY_PATH}")
    print(f"Wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
