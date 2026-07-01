#!/usr/bin/env python3
"""PHASE ECSE-X2-M3 — Champion/Challenger shadow validation (no production changes)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_x2_m2.build import baseline_table_row_count
from worldcup_predictor.research.ecse_x2_m3.constants import SHADOW_ARTIFACT
from worldcup_predictor.research.ecse_x2_m3.shadow_runner import run_champion_challenger_shadow

SUMMARY_PATH = ROOT / "artifacts" / "ecse_x2_m3_champion_challenger_summary.json"
REPORT_PATH = ROOT / "ECSE_X2_M3_CHAMPION_CHALLENGER_SHADOW_REPORT.md"


def _report_md(payload: dict, baseline_before: int, baseline_after: int) -> str:
    ov = payload.get("overall") or {}
    delta = ov.get("delta") or {}
    overfit = payload.get("overfit") or {}
    lines = [
        "# ECSE-X2-M3 — Champion/Challenger Shadow Report",
        "",
        "**Phase:** ECSE-X2-M3  ",
        "**Mode:** Shadow-only — no production prediction changes  ",
        f"**Equation:** `{payload.get('equation_name')}` — log(home_prob) / log(1.618)  ",
        f"**Recommendation:** **{overfit.get('recommendation', 'PENDING')}**  ",
        "",
        "## X2-M2 Context",
        "",
        "ECSE-X2-M2 identified `log_home_prob_phi` as best market algebra equation",
        "(Top-1 +1.08pp, Top-3 +1.63pp on original 70/30 split).",
        "",
        "## Sample",
        "",
        f"- Eligible fixtures (home odds): **{payload.get('eligible_n', 0):,}**",
        f"- Shadow rows written: **{payload.get('shadow_rows_written', 0):,}**",
        f"- Shadow rows skipped (idempotent): **{payload.get('shadow_rows_skipped', 0):,}**",
        f"- Baseline table rows unchanged: **{baseline_before:,}**",
        "",
        "## Overall Champion vs Challenger (70/30 temporal test)",
        "",
        "| Metric | Champion | Challenger | Δ |",
        "|--------|----------|------------|---|",
    ]
    ch = ov.get("champion") or {}
    cl = ov.get("challenger") or {}
    rows = [
        ("Top-1 hit %", "champion_top1_hit_rate_pct", "challenger_top1_hit_rate_pct", "top1_delta_pp"),
        ("Top-3 hit %", "champion_top3_hit_rate_pct", "challenger_top3_hit_rate_pct", "top3_delta_pp"),
        ("Top-5 hit %", "champion_top5_hit_rate_pct", "challenger_top5_hit_rate_pct", "top5_delta_pp"),
        ("Top-10 hit %", "champion_top10_hit_rate_pct", "challenger_top10_hit_rate_pct", "top10_delta_pp"),
        ("Log loss", "champion_avg_log_loss", "challenger_avg_log_loss", "avg_log_loss"),
        ("Brier", "champion_avg_brier", "challenger_avg_brier", "avg_brier"),
    ]
    for label, ck, chk, dk in rows:
        lines.append(
            f"| {label} | {ch.get(ck, 'n/a')} | {cl.get(chk, 'n/a')} | {delta.get(dk, 'n/a')} |"
        )
    lines.extend(
        [
            "",
            f"- Pick disagreement rate: **{cl.get('pick_disagreement_rate_pct', 'n/a')}%**",
            "",
            "## Fold-by-fold (temporal)",
            "",
            "| Fold | n | Top-1 Δ | Top-3 Δ | Top-5 Δ | LogLoss Δ |",
            "|------|---|---------|---------|---------|-----------|",
        ]
    )
    for fr in payload.get("fold_results") or []:
        d = fr.get("delta") or {}
        lines.append(
            f"| {fr.get('fold')} | {fr.get('test_n', 0):,} | "
            f"{d.get('top1_delta_pp', 0):+.4f} | {d.get('top3_delta_pp', 0):+.4f} | "
            f"{d.get('top5_delta_pp', 0):+.4f} | {d.get('avg_log_loss', 0):+.6f} |"
        )

    lines.extend(["", "## Breakdown highlights", ""])
    for section, title in (
        ("by_league", "League"),
        ("by_match_state", "Match state"),
        ("by_home_prob_bucket", "Home prob bucket"),
        ("by_liquidity", "Odds liquidity"),
    ):
        lines.append(f"### {title}")
        items = list((payload.get("breakdowns") or {}).get(section, {}).items())[:8]
        for k, v in items:
            d = v.get("delta") or {}
            lines.append(
                f"- **{k}** (n={v.get('n', 0):,}): "
                f"top3 Δ={d.get('top3_delta_pp', 0):+.4f}, logloss Δ={d.get('avg_log_loss', 0):+.6f}"
            )
        lines.append("")

    lines.extend(["## Rank movement examples", ""])
    for ex in payload.get("examples") or []:
        lines.append(
            f"- {ex.get('match')} — actual `{ex.get('actual')}`: "
            f"rank {ex.get('baseline_rank')} → {ex.get('challenger_rank')} "
            f"(Δ{ex.get('rank_delta')}); top1 {ex.get('baseline_top1')} → {ex.get('challenger_top1')}"
        )

    lines.extend(
        [
            "",
            "## Overfit risk",
            "",
            f"- Folds with positive Top-3 Δ: **{overfit.get('folds_top3_positive', 0)}**",
            f"- Risk flags: `{', '.join(overfit.get('reasons') or []) or 'none'}`",
            "",
            "## Safety",
            "",
            "- No public API / UI exposure",
            "- No WDE / EGIE / baseline ECSE table changes",
            "- Shadow artifact append-only",
            "",
            f"## Artifacts",
            "",
            f"- `{SHADOW_ARTIFACT}`",
            f"- `{SUMMARY_PATH.as_posix()}`",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    settings = get_settings()
    conn = connect(get_db_path(settings.sqlite_path))
    try:
        before = baseline_table_row_count(conn)
        result = run_champion_challenger_shadow(conn, artifact_path=ROOT / SHADOW_ARTIFACT)
        after = baseline_table_row_count(conn)
    finally:
        conn.close()

    if before != after:
        print("ERROR: baseline table modified", file=sys.stderr)
        return 2

    payload = result.to_dict()
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    REPORT_PATH.write_text(_report_md(payload, before, after), encoding="utf-8")

    print(json.dumps({"recommendation": payload.get("overfit", {}).get("recommendation"), "overall_delta": payload.get("overall", {}).get("delta")}, indent=2))
    print(f"\nWrote {ROOT / SHADOW_ARTIFACT}")
    print(f"Wrote {SUMMARY_PATH}")
    print(f"Wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
