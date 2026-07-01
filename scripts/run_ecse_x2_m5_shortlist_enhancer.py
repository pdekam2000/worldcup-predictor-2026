#!/usr/bin/env python3
"""PHASE ECSE-X2-M5 — Shortlist enhancer research (shadow-only, no production changes)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_x2_m2.build import baseline_table_row_count
from worldcup_predictor.research.ecse_x2_m5.constants import SHADOW_ARTIFACT, SUMMARY_ARTIFACT
from worldcup_predictor.research.ecse_x2_m5.runner import run_shortlist_enhancer

SUMMARY_PATH = ROOT / SUMMARY_ARTIFACT
REPORT_PATH = ROOT / "ECSE_X2_M5_SHORTLIST_ENHANCER_REPORT.md"


def _report_md(payload: dict, baseline_before: int) -> str:
    rec = payload.get("recommendation") or {}
    best = rec.get("best_method")
    lines = [
        "# ECSE-X2-M5 — Shortlist Enhancer Report",
        "",
        "**Phase:** ECSE-X2-M5  ",
        "**Mode:** Research/shadow only — no production changes  ",
        f"**Recommendation:** **{rec.get('recommendation', 'PENDING')}**  ",
        "",
        "## Hypothesis",
        "",
        "Market algebra may improve exact-score shortlist quality (Top-5/Top-10)",
        "even when too weak for full ranking promotion (M4 Top-3 +0.02pp).",
        "",
        "## Sample",
        "",
        f"- Eligible fixtures (ft_home odds): **{payload.get('eligible_n', 0):,}**",
        f"- Test fixtures (30% holdout): **{payload.get('test_n', 0):,}**",
        f"- Shadow rows written: **{payload.get('shadow_rows_written', 0):,}**",
        f"- Baseline table unchanged: **{baseline_before:,}**",
        "",
        f"## Best method: **{best or 'none'}**",
        "",
        "## Method comparison (overall test)",
        "",
        "| Method | Top-1 Δ | Top-3 Δ | Top-5 Δ | Top-10 Δ | LogLoss Δ | MRR Δ | Volatility |",
        "|--------|---------|---------|---------|----------|-----------|-------|------------|",
    ]

    champ = (payload.get("method_results") or {}).get("champion", {}).get("overall") or {}
    for method, data in (payload.get("method_results") or {}).items():
        if method == "champion":
            continue
        d = (data.get("overall") or {}).get("delta") or {}
        s = data.get("overall") or {}
        accepted = (data.get("assessment") or {}).get("accepted", False)
        lines.append(
            f"| {method} | {d.get('top1_delta_pp', 0):+.4f} | {d.get('top3_delta_pp', 0):+.4f} | "
            f"{d.get('top5_delta_pp', 0):+.4f} | {d.get('top10_delta_pp', 0):+.4f} | "
            f"{d.get('avg_log_loss', 0):+.6f} | {d.get('mean_reciprocal_rank', 0):+.6f} | "
            f"{s.get('rank_volatility', 0)} ({'ok' if accepted else 'rej'}) |"
        )

    lines.extend(["", "## Rejection summary", ""])
    for method, data in (payload.get("method_results") or {}).items():
        if method == "champion":
            continue
        a = data.get("assessment") or {}
        reasons = ", ".join(a.get("reasons") or []) or "none"
        lines.append(f"- **{method}**: accepted={a.get('accepted')} — {reasons}")

    lines.extend(["", "## Segment breakdown (Top-5 Δ vs champion)", ""])
    for segment, seg in (payload.get("segment_results") or {}).items():
        lines.append(f"### {segment} (n={seg.get('n', 0):,})")
        for method, md in (seg.get("methods") or {}).items():
            d = md.get("delta") or {}
            lines.append(
                f"- {method}: top5 Δ={d.get('top5_delta_pp', 0):+.4f}, top3 Δ={d.get('top3_delta_pp', 0):+.4f}"
            )
        lines.append("")

    if best:
        best_data = (payload.get("method_results") or {}).get(best) or {}
        lines.extend(["", f"## Fold results ({best})", ""])
        lines.append("| Fold | n | Top-5 Δ | Top-3 Δ | LogLoss Δ |")
        lines.append("|------|---|---------|---------|-----------|")
        for fr in best_data.get("fold_results") or []:
            d = fr.get("delta") or {}
            lines.append(
                f"| {fr.get('fold')} | {fr.get('test_n', 0):,} | "
                f"{d.get('top5_delta_pp', 0):+.4f} | {d.get('top3_delta_pp', 0):+.4f} | "
                f"{d.get('avg_log_loss', 0):+.6f} |"
            )

    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- No public API / UI exposure",
            "- No WDE / EGIE / baseline ECSE table changes",
            "- Balanced control reported separately",
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
        payload = run_shortlist_enhancer(conn, artifact_path=ROOT / SHADOW_ARTIFACT)
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
    print(f"\nWrote {ROOT / SHADOW_ARTIFACT}")
    print(f"Wrote {SUMMARY_PATH}")
    print(f"Wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
