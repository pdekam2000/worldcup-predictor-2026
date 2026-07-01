#!/usr/bin/env python3
"""PHASE ECSE-X2-M4 — Targeted internal weight test (shadow-only, no production changes)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_x2_m2.build import baseline_table_row_count
from worldcup_predictor.research.ecse_x2_m4.constants import SHADOW_ARTIFACT, SUMMARY_ARTIFACT
from worldcup_predictor.research.ecse_x2_m4.weight_runner import run_internal_weight_test

SUMMARY_PATH = ROOT / SUMMARY_ARTIFACT
REPORT_PATH = ROOT / "ECSE_X2_M4_INTERNAL_WEIGHT_TEST_REPORT.md"


def _report_md(payload: dict, baseline_before: int) -> str:
    rec = payload.get("recommendation") or {}
    best_w = rec.get("best_weight")
    lines = [
        "# ECSE-X2-M4 — Internal Weight Test Report",
        "",
        "**Phase:** ECSE-X2-M4  ",
        "**Mode:** Shadow/internal weight test — no public exposure  ",
        "**Equation:** `log_home_prob_phi` — log(home_prob) / log(1.618)  ",
        f"**Recommendation:** **{rec.get('recommendation', 'PENDING')}**  ",
        "",
        "## M3 context",
        "",
        "M3 full reorder on eligible cohort: Top-3 +1.63pp, log loss −0.176.",
        "M4 applies the same lift signal as a small blend (max weight 0.10) only in the",
        "home-favorite / home_prob≥0.55 segment where M3 was strongest.",
        "",
        "## Target segment",
        "",
        "Apply adjustment only when:",
        "- `ft_home` / home_prob exists",
        "- home_prob >= 0.55",
        "- classified as home favorite",
        "- valid odds snapshot",
        "- not balanced",
        "",
        "## Sample",
        "",
        f"- Eligible fixtures (any home odds): **{payload.get('eligible_n', 0):,}**",
        f"- Target segment fixtures: **{payload.get('segment_n', 0):,}**",
        f"- Segment coverage: **{100 * float(payload.get('segment_coverage_rate', 0)):.1f}%**",
        f"- Shadow rows written: **{payload.get('shadow_rows_written', 0):,}**",
        f"- Shadow rows skipped: **{payload.get('shadow_rows_skipped', 0):,}**",
        f"- Baseline table unchanged: **{baseline_before:,}**",
        "",
        f"## Best weight: **{best_w}**" if best_w is not None else "## Best weight: none accepted",
        "",
        "## Per-weight comparison (70/30 test)",
        "",
        "| Weight | Top-1 Δ | Top-3 Δ | Top-5 Δ | LogLoss Δ | Volatility | Accepted |",
        "|--------|---------|---------|---------|-----------|------------|----------|",
    ]

    for w in payload.get("per_weight") or []:
        d = (w.get("metrics") or {}).get("delta") or {}
        vol = (w.get("metrics") or {}).get("volatility_score", 0)
        accepted = (w.get("assessment") or {}).get("accepted", False)
        lines.append(
            f"| {w.get('weight')} | {d.get('top1_delta_pp', 0):+.4f} | "
            f"{d.get('top3_delta_pp', 0):+.4f} | {d.get('top5_delta_pp', 0):+.4f} | "
            f"{d.get('avg_log_loss', 0):+.6f} | {vol} | {'yes' if accepted else 'no'} |"
        )

    lines.extend(["", "## Rejection summary", ""])
    for w in payload.get("per_weight") or []:
        a = w.get("assessment") or {}
        reasons = ", ".join(a.get("reasons") or []) or "none"
        lines.append(
            f"- weight **{w.get('weight')}**: accepted={a.get('accepted')} — {reasons}"
        )

    lines.extend(["", "## Fold results (best weight)", ""])
    if best_w is not None:
        best_entry = next((w for w in (payload.get("per_weight") or []) if w.get("weight") == best_w), None)
        if best_entry:
            lines.append("| Fold | n | Top-3 Δ | LogLoss Δ |")
            lines.append("|------|---|---------|-----------|")
            for fr in best_entry.get("fold_results") or []:
                d = fr.get("delta") or {}
                lines.append(
                    f"| {fr.get('fold')} | {fr.get('test_n', 0):,} | "
                    f"{d.get('top3_delta_pp', 0):+.4f} | {d.get('avg_log_loss', 0):+.6f} |"
                )

    lines.extend(["", "## Segment breakdown (best weight)", ""])
    if best_w is not None:
        best_entry = next((w for w in (payload.get("per_weight") or []) if w.get("weight") == best_w), None)
        if best_entry:
            for seg, data in (best_entry.get("segment_breakdown") or {}).items():
                d = data.get("delta") or {}
                lines.append(
                    f"- **{seg}** (n={data.get('n', 0):,}): "
                    f"top3 Δ={d.get('top3_delta_pp', 0):+.4f}, logloss Δ={d.get('avg_log_loss', 0):+.6f}"
                )

    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- No public API / UI exposure",
            "- No WDE / EGIE / baseline ECSE table changes",
            "- Balanced matches excluded from adjustment",
            "- Shadow artifact append-only",
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
        result = run_internal_weight_test(conn, artifact_path=ROOT / SHADOW_ARTIFACT)
        after = baseline_table_row_count(conn)
    finally:
        conn.close()

    if before != after:
        print("ERROR: baseline table modified", file=sys.stderr)
        return 2

    payload = result.to_dict()
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    REPORT_PATH.write_text(_report_md(payload, before), encoding="utf-8")

    print(
        json.dumps(
            {
                "recommendation": payload.get("recommendation", {}).get("recommendation"),
                "best_weight": payload.get("recommendation", {}).get("best_weight"),
            },
            indent=2,
        )
    )
    print(f"\nWrote {ROOT / SHADOW_ARTIFACT}")
    print(f"Wrote {SUMMARY_PATH}")
    print(f"Wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
