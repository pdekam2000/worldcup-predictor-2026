#!/usr/bin/env python3
"""Write PHASE_API_J_HISTORICAL_XG_AND_UEFA_SCALE_REPORT.md"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "PHASE_API_J_HISTORICAL_XG_AND_UEFA_SCALE_REPORT.md"


def _fg(metrics: dict[str, Any]) -> dict[str, Any]:
    return (metrics.get("by_market") or {}).get("first_goal_team") or {}


def write_report(
    *,
    xg_audit: dict[str, Any],
    pred_audit: dict[str, Any],
    pending: dict[str, Any],
    reingest: dict[str, Any],
    sample_size: dict[str, Any],
    utilization: dict[str, Any],
    backtest: dict[str, Any],
    impact: dict[str, Any],
    api_total: int,
    before_bt: dict[str, Any],
) -> Path:
    strategies = backtest.get("strategies") or {}
    before_a = (before_bt.get("strategies") or {}).get("A") or {}

    lines = [
        "# PHASE API-J — Historical xG Availability + UEFA EGIE Scale Validation",
        "",
        "**Mode:** Audit → Validate → Expand Sample → Re-Backtest → Report  ",
        "**Production deploy:** NO  ",
        "",
        "---",
        "",
        "## Executive Answer",
        "",
    ]

    live_xg = any(
        s.get("xg_available_type_5304")
        for lg in (xg_audit.get("live_probe") or {}).get("leagues") or []
        for s in lg.get("seasons_probed") or []
    )
    xg_cov = (utilization.get("coverage_pct") or {}).get("xg", 0)
    pred_cov = (utilization.get("coverage_pct") or {}).get("predictions", 0)

    if xg_cov > 5:
        answer = (
            f"**Partial yes.** Historical UEFA xG is available for some competitions/seasons "
            f"({xg_cov}% post-expansion). Material EGIE lift requires targeting those fixtures, not the full 2014-era cache."
        )
    elif live_xg:
        answer = (
            "**Partial yes, with limits.** Sportmonks returns true xG (`type_id=5304`) for some recent UEFA seasons "
            "(Europa League 2024/25 confirmed live) but **not** across all competitions or the legacy cached sample. "
            "Historical xG is **not** uniformly available; EGIE Strategy B cannot improve on xG alone until the dataset "
            "is filtered to xG-rich seasons and the UEFA parser reads lowercase `xgfixture`."
        )
    else:
        answer = "**No** for the current UEFA cache composition. Live probes found no xG on sampled seasons."

    lines.extend([answer, "", "---", "", "## STEP 1 — Historical xG Availability", ""])
    lines.append(f"Artifact: `artifacts/historical_xg_availability_audit.json`")
    lines.append("")
    findings = xg_audit.get("findings") or {}
    for k, v in findings.items():
        lines.append(f"- **{k}:** {v}")
    lines.extend(["", "## STEP 2 — Historical Predictions Availability", ""])
    lines.append("Artifact: `artifacts/historical_predictions_availability_audit.json`")
    pf = pred_audit.get("findings") or {}
    for k, v in pf.items():
        lines.append(f"- **{k}:** {v}")

    lines.extend(["", "## STEP 3 — Pending Fixture Root Causes", ""])
    lines.append("Artifact: `artifacts/uefa_pending_fixture_root_causes.json`")
    lines.append("")
    lines.append("| Cause | Count |")
    lines.append("|-------|-------|")
    for k, v in sorted((pending.get("summary") or {}).items(), key=lambda x: -x[1]):
        lines.append(f"| {k} | {v} |")
    if pending.get("after_reingest_summary"):
        lines.append("")
        lines.append("**After re-ingest:**")
        for k, v in sorted(pending["after_reingest_summary"].items(), key=lambda x: -x[1]):
            lines.append(f"- {k}: {v}")

    lines.extend(["", "## STEP 4 — Targeted Re-Ingest", ""])
    lines.append(f"- API calls: {reingest.get('api_calls_used')}")
    lines.append(f"- Events recovered: {reingest.get('recovered_events')}")
    lines.append(f"- xG recovered: {reingest.get('recovered_xg')}")
    lines.append(f"- Unchanged: {reingest.get('unchanged')}")

    lines.extend(["", "## STEP 5 — Sample Size Growth", ""])
    lines.append("Artifact: `artifacts/before_vs_after_sample_size.json`")
    b = sample_size.get("before") or {}
    a = sample_size.get("after_mapping") or {}
    ar = sample_size.get("after_rebuild") or {}
    lines.append(f"- Mapping fixtures: {b.get('mapping_fixtures')} → {a.get('mapping_fixtures')} (+{a.get('added', 0)})")
    lines.append(f"- Provider coverage: `{json.dumps(utilization.get('coverage_pct'))}`")

    lines.extend(["", "## STEP 6 — Dataset Rebuild", ""])
    lines.append(f"- Survival dataset: `{ar.get('survival_dataset')}`")
    lines.append("- Validations: `validate_egie_uefa_club_dataset.py`, `validate_uefa_event_team_mapping.py`")

    lines.extend(["", "## STEP 7 — A–F Backtest Comparison", ""])
    lines.append("")
    lines.append("| Strategy | FG Team | Pending | Goal Range | Soft Minute | Paid Cov |")
    lines.append("|----------|---------|---------|------------|-------------|----------|")
    for key in "ABCDEF":
        s = strategies.get(key) or {}
        m = s.get("metrics") or {}
        fg = _fg(m)
        cov = (s.get("coverage") or {}).get("with_paid_data", 0)
        wr = fg.get("winrate")
        wr_s = f"{100*float(wr):.1f}%" if wr is not None else "n/a"
        gr = s.get("goal_range_hit_rate")
        sm = s.get("goal_minute_soft_hit_rate")
        lines.append(
            f"| {key} | {wr_s} | {fg.get('pending', 'n/a')} | "
            f"{100*float(gr or 0):.1f}% | {100*float(sm or 0):.1f}% | {cov} |"
        )

    lines.append("")
    lines.append("**vs API-I baseline (Strategy A):**")
    bfg = _fg(before_a.get("metrics") or {})
    afg = _fg(strategies.get("A", {}).get("metrics") or {})
    lines.append(f"- FG pending: {bfg.get('pending')} → {afg.get('pending')}")
    lines.append(f"- FG winrate: {bfg.get('winrate')} → {afg.get('winrate')}")

    if xg_cov == 0:
        lines.append("")
        lines.append(
            "> **xG historical unavailable** under the expanded UEFA dataset for Strategy B: "
            "B metrics reflect enrichment side-effects, not true xG signal, unless coverage_pct.xg > 0."
        )

    lines.extend(["", "## STEP 8 — Feature Impact Ranking", ""])
    lines.append("Artifact: `artifacts/uefa_feature_impact_ranking.json`")
    lines.append("")
    lines.append("| Feature | Tier | FG Δ vs A | Coverage |")
    lines.append("|---------|------|-----------|----------|")
    for row in impact.get("ranked_features") or []:
        d = row.get("fg_team_delta_vs_a")
        ds = f"{100*float(d):+.1f}pp" if d is not None else "n/a"
        lines.append(
            f"| {row.get('feature')} | {row.get('tier')} | {ds} | {row.get('coverage_with_paid_data')} |"
        )

    lines.extend(["", "## Quota Usage", ""])
    lines.append(f"- Estimated total API calls (Phase API-J): **~{api_total}**")

    lines.extend(["", "## Recommendation (Phase API-K)", ""])
    lines.extend(
        [
            "1. **Build xG-rich UEFA holdout** from Europa League 2024/25+ fixtures where `type_id=5304` is confirmed.",
            "2. **Re-ingest event-missing fixtures** only if Sportmonks returns events (2005-era EL may be permanently empty).",
            "3. **Capture predictions pre-kickoff** — finished payloads retain empty `predictions[]`.",
            "4. **Do not promote** Strategy B–F until xG coverage exceeds 30% on evaluable FG fixtures.",
            "",
            "---",
            "",
            "**STOP — No deploy. No production changes.**",
        ]
    )

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return REPORT
