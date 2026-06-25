"""Phase 56A — Market Behavior Intelligence orchestrator."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from worldcup_predictor.mbi.buckets import build_bucket_table, market_bucket_summary, overall_calibration
from worldcup_predictor.mbi.collector import collect_all_selections
from worldcup_predictor.mbi.edge_detection import detect_edges, market_edge_ranking
from worldcup_predictor.mbi.inventory import run_inventory
from worldcup_predictor.mbi.models import VALID_RECOMMENDATIONS
from worldcup_predictor.mbi.prior_feasibility import decide_prior_recommendation, simulate_prior_blend

ARTIFACT_DIR = Path("artifacts/phase56a_market_behavior_intelligence")
REPORT_PATH = Path("PHASE_56A_MARKET_BEHAVIOR_INTELLIGENCE_REPORT.md")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_phase56a() -> dict[str, Any]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    inventory = run_inventory()
    (ARTIFACT_DIR / "odds_inventory.json").write_text(
        json.dumps(inventory.to_dict(), indent=2), encoding="utf-8"
    )

    selections, collect_meta = collect_all_selections()
    sel_df = pd.DataFrame([s.to_dict() for s in selections])
    sel_df.to_parquet(ARTIFACT_DIR / "mbi_selections.parquet", index=False)
    (ARTIFACT_DIR / "collection_meta.json").write_text(json.dumps(collect_meta, indent=2), encoding="utf-8")

    bucket_table = build_bucket_table(selections)
    (ARTIFACT_DIR / "odds_buckets.json").write_text(json.dumps(bucket_table, indent=2), encoding="utf-8")

    market_summary = market_bucket_summary(bucket_table)
    (ARTIFACT_DIR / "market_bucket_summary.json").write_text(
        json.dumps(market_summary, indent=2), encoding="utf-8"
    )

    calibration = overall_calibration(selections)
    (ARTIFACT_DIR / "calibration.json").write_text(json.dumps(calibration, indent=2), encoding="utf-8")

    edges = detect_edges(bucket_table)
    (ARTIFACT_DIR / "edge_detection.json").write_text(json.dumps(edges, indent=2), encoding="utf-8")

    market_rank = market_edge_ranking(bucket_table)
    (ARTIFACT_DIR / "market_edge_ranking.json").write_text(
        json.dumps(market_rank, indent=2), encoding="utf-8"
    )

    prior = simulate_prior_blend(selections, bucket_table)
    (ARTIFACT_DIR / "prior_feasibility.json").write_text(json.dumps(prior, indent=2), encoding="utf-8")

    decision = decide_prior_recommendation(prior, edges)
    top_market = market_rank[0]["market_key"] if market_rank else None
    has_predictive = any(
        int(r.get("biased_buckets") or 0) > 0 for r in market_rank
    )
    has_persistent = int(edges.get("bias_count") or 0) > 0

    decision["questions"] = {
        "odds_buckets_predictive": has_predictive,
        "persistent_biases": has_persistent,
        "mbi_worth_building": decision["recommendation"] != "MBI_NO_VALUE",
        "top_market": top_market,
    }
    (ARTIFACT_DIR / "decision.json").write_text(json.dumps(decision, indent=2), encoding="utf-8")

    recommendation = decision.get("recommendation", "MBI_NO_VALUE")
    if recommendation not in VALID_RECOMMENDATIONS:
        recommendation = "MBI_NO_VALUE"

    report = {
        "generated_at": _utc_now(),
        "phase": "56A",
        "inventory": inventory.to_dict(),
        "collection": collect_meta,
        "calibration": calibration,
        "edges": {
            "bias_count": edges.get("bias_count"),
            "strong_bias_count": edges.get("strong_bias_count"),
        },
        "prior": prior,
        "market_ranking": market_rank[:5],
        "decision": decision,
        "recommendation": recommendation,
        "production_changes": False,
        "api_calls_used": 0,
    }
    (ARTIFACT_DIR / "phase56a_report.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )
    _write_markdown(report, inventory, collect_meta, bucket_table, calibration, edges, prior, market_rank, decision)
    return report


def _write_markdown(
    report: dict[str, Any],
    inventory: Any,
    collect_meta: dict[str, Any],
    bucket_table: list[dict[str, Any]],
    calibration: dict[str, Any],
    edges: dict[str, Any],
    prior: dict[str, Any],
    market_rank: list[dict[str, Any]],
    decision: dict[str, Any],
) -> None:
    rec = report.get("recommendation")
    qs = decision.get("questions") or {}
    inv = inventory.to_dict()
    thresholds = edges.get("min_sample_thresholds") or {}

    lines = [
        "# PHASE 56A — Market Behavior Intelligence (MBI)",
        "",
        f"**Date:** {report.get('generated_at', '')[:10]}",
        "**Mode:** Research → Historical Odds Intelligence",
        "**Status:** Complete — research only",
        "**API calls:** 0",
        "",
        f"### Final recommendation: **`{rec}`**",
        "",
        "---",
        "",
        "## Part A — Odds Inventory",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total snapshot rows | {inv.get('total_snapshot_rows', 0)} |",
        f"| Normalized market lines | {inv.get('total_selections', 0)} |",
        f"| MBI selections collected | {collect_meta.get('total_selections', 0)} |",
        f"| Selections with outcomes | {collect_meta.get('with_outcomes', 0)} |",
        "",
        "### Sources",
        "",
    ]
    for src in inv.get("sources") or []:
        lines.append(
            f"- **{src.get('source')}**: {src.get('fixtures', 0)} fixtures, "
            f"{src.get('odds_rows', 0)} odds rows"
        )

    lines.extend(
        [
            "",
            "Artifact: `artifacts/phase56a_market_behavior_intelligence/odds_inventory.json`",
            "",
            "## Part B — Odds Buckets",
            "",
            "Buckets: 1.10–1.20, 1.20–1.30, … 10.90–11.00, 11.00+",
            "",
            f"Bucket cells with outcomes: **{len(bucket_table)}**",
            "",
            "## Part C — Real Outcomes vs Implied",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Global Brier | {calibration.get('brier')} |",
            f"| Global ECE | {calibration.get('ece')} |",
            f"| Scored selections | {calibration.get('n', 0)} |",
            "",
            "### Top calibration gaps (n≥30)",
            "",
            "| Market | Bucket | Selection | N | Hit% | Implied | Gap |",
            "|--------|--------|-----------|---|------|---------|-----|",
        ]
    )

    top_gaps = sorted(
        [r for r in bucket_table if int(r["count"]) >= 30],
        key=lambda r: abs(float(r["calibration_gap"])),
        reverse=True,
    )[:10]
    for r in top_gaps:
        lines.append(
            f"| {r['market_key']} | {r['bucket']} | {r['selection']} | {r['count']} | "
            f"{r['hit_rate']:.2%} | {r['implied_mean']:.2%} | {r['calibration_gap']:+.2%} |"
        )
    if not top_gaps:
        lines.append("| — | — | — | — | — | — | — |")

    lines.extend(
        [
            "",
            "## Part D — Edge Detection",
            "",
            f"| Threshold | Min N |",
            f"|-----------|-------|",
            f"| Weak signal | {thresholds.get('weak_signal', 15)} |",
            f"| Persistent bias | {thresholds.get('persistent_bias', 30)} |",
            f"| Strong bias | {thresholds.get('strong_bias', 50)} |",
            "",
            f"Persistent biases (n≥30, |gap|≥5pp): **{edges.get('bias_count', 0)}**",
            f"Strong biases (n≥50, |gap|≥7pp): **{edges.get('strong_bias_count', 0)}**",
            "",
        ]
    )

    for label, key in (
        ("Persistent overpricing", "persistent_overpricing"),
        ("Persistent underpricing", "persistent_underpricing"),
    ):
        rows = edges.get(key) or []
        if rows:
            lines.append(f"### {label}")
            lines.append("")
            for r in rows[:5]:
                lines.append(
                    f"- {r['market_key']} {r['bucket']} {r['selection']}: "
                    f"gap {r['calibration_gap']:+.2%} (n={r['count']})"
                )
            lines.append("")

    lines.extend(
        [
            "## Part E — Prior Feasibility",
            "",
            "| Prior weight | Brier | N |",
            "|--------------|-------|---|",
        ]
    )
    for w, metrics in (prior.get("by_weight") or {}).items():
        lines.append(f"| {float(w):.0%} | {metrics.get('brier')} | {metrics.get('n')} |")

    lines.extend(
        [
            "",
            f"Best prior weight: **{prior.get('best_weight', 0):.0%}**",
            f"Brier improvement: **{prior.get('improvement')}**",
            f"Prior feasible: **{prior.get('feasible')}**",
            "",
            "## Part F — Decision Questions",
            "",
            f"1. **Do odds buckets contain predictive information?** {qs.get('odds_buckets_predictive')}",
            f"2. **Are there persistent biases?** {qs.get('persistent_biases')}",
            f"3. **Is MBI worth building?** {qs.get('mbi_worth_building')}",
            f"4. **Which markets benefit most?** {qs.get('top_market')}",
            "",
            f"### Final recommendation: **`{rec}`**",
            "",
            decision.get("rationale", ""),
            "",
            "### Market ranking by signal score",
            "",
        ]
    )
    for r in market_rank[:5]:
        lines.append(
            f"- **{r['market_key']}**: signal={r.get('signal_score')}, "
            f"biased_buckets={r.get('biased_buckets')}, n={r.get('n')}"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## Constraints honored",
            "",
            "- No deploy, production integration, or modeling changes",
            "- Cache-first historical odds intelligence only",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
