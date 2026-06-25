"""Phase 55B UEFA goalscorer odds expansion orchestrator."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.egie.goalscorer_uefa_expansion.bridge import build_expanded_bridge_set, map_expanded_odds
from worldcup_predictor.egie.goalscorer_uefa_expansion.dataset import build_after_dataset, build_before_dataset
from worldcup_predictor.egie.goalscorer_uefa_expansion.inventory import audit_all_sources, build_uefa_inventory
from worldcup_predictor.egie.goalscorer_uefa_expansion.models import VALID_RECOMMENDATIONS
from worldcup_predictor.egie.goalscorer_uefa_expansion.revalidation import decide_recommendation, run_before_after

ARTIFACT_DIR = Path("artifacts/phase55b_uefa_goalscorer_odds_expansion")
REPORT_PATH = Path("PHASE_55B_UEFA_GOALSCORER_ODDS_EXPANSION_REPORT.md")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_phase55b() -> dict[str, Any]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    source_audit = audit_all_sources()
    (ARTIFACT_DIR / "source_audit.json").write_text(json.dumps(source_audit, indent=2, default=str), encoding="utf-8")

    uefa_inventory = build_uefa_inventory()
    (ARTIFACT_DIR / "uefa_goalscorer_inventory.json").write_text(json.dumps(uefa_inventory, indent=2), encoding="utf-8")

    bridges, raw_odds, bridge_meta = build_expanded_bridge_set()
    (ARTIFACT_DIR / "expanded_bridge_meta.json").write_text(json.dumps(bridge_meta, indent=2), encoding="utf-8")
    (ARTIFACT_DIR / "expanded_bridges.json").write_text(
        json.dumps([b.to_dict() for b in bridges], indent=2), encoding="utf-8"
    )

    mapped, unmapped, mapping_meta = map_expanded_odds(bridges, raw_odds)
    (ARTIFACT_DIR / "mapping_summary.json").write_text(json.dumps(mapping_meta, indent=2, default=str), encoding="utf-8")

    before_df, before_meta = build_before_dataset()
    after_df, after_meta = build_after_dataset(bridges, mapped)

    before_df.to_parquet(ARTIFACT_DIR / "goalscorer_dataset_before.parquet", index=False)
    after_df.to_parquet(ARTIFACT_DIR / "goalscorer_dataset_expanded.parquet", index=False)
    (ARTIFACT_DIR / "dataset_before_meta.json").write_text(json.dumps(before_meta, indent=2), encoding="utf-8")
    (ARTIFACT_DIR / "dataset_after_meta.json").write_text(json.dumps(after_meta, indent=2), encoding="utf-8")

    revalidation = run_before_after(before_df, after_df)
    (ARTIFACT_DIR / "revalidation.json").write_text(json.dumps(revalidation, indent=2, default=str), encoding="utf-8")

    decision = decide_recommendation(revalidation.get("impact") or {}, revalidation)
    (ARTIFACT_DIR / "decision.json").write_text(json.dumps(decision, indent=2), encoding="utf-8")

    recommendation = decision.get("recommendation", "ODDS_NOT_ENOUGH")
    if recommendation not in VALID_RECOMMENDATIONS:
        recommendation = "ODDS_NOT_ENOUGH"

    report = {
        "generated_at": _utc_now(),
        "phase": "55B",
        "source_audit": source_audit,
        "uefa_inventory": uefa_inventory,
        "bridge_meta": bridge_meta,
        "mapping_meta": mapping_meta,
        "before_meta": before_meta,
        "after_meta": after_meta,
        "revalidation": revalidation,
        "decision": decision,
        "recommendation": recommendation,
        "production_changes": False,
        "api_calls_used": 0,
    }
    (ARTIFACT_DIR / "phase55b_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    _write_markdown(report, uefa_inventory, revalidation, decision, bridge_meta, after_meta)
    return report


def _write_markdown(
    report: dict[str, Any],
    inventory: dict[str, Any],
    reval: dict[str, Any],
    decision: dict[str, Any],
    bridge_meta: dict[str, Any],
    after_meta: dict[str, Any],
) -> None:
    rec = report.get("recommendation")
    before = reval.get("before") or {}
    after = reval.get("after") or {}
    delta = reval.get("delta") or {}
    impact = reval.get("impact") or {}
    totals = inventory.get("totals") or {}

    lines = [
        "# PHASE 55B — UEFA Goalscorer Odds Expansion",
        "",
        f"**Date:** {report.get('generated_at', '')[:10]}  ",
        "**Mode:** Data Expansion → Coverage Growth → Revalidation  ",
        "**Status:** Complete — research only  ",
        "**API calls:** 0",
        "",
        f"### Final recommendation: **`{rec}`**",
        "",
        "---",
        "",
        "## Part A — Source inventory",
        "",
        f"| Source | GS fixtures (est.) |",
        f"|--------|-------------------|",
    ]
    inv = (report.get("source_audit") or {}).get("consolidated_inventory") or {}
    for src in inv.get("sources") or []:
        lines.append(f"| {src.get('source')} | {src.get('fixtures_with_goalscorer_odds')} |")

    lines.extend(
        [
            "",
            f"Sportmonks strict selections: **{(report.get('source_audit') or {}).get('sportmonks_strict_selections', 0)}**",
            f"Market types (strict): `{(report.get('source_audit') or {}).get('market_type_counts_strict', {})}`",
            "",
            "## Part B — UEFA inventory",
            "",
            "| League | Cached | Strict GS | Coverage |",
            "|--------|--------|-----------|----------|",
        ]
    )
    for league, m in (inventory.get("by_league") or {}).items():
        lines.append(
            f"| {league} | {m.get('fixtures_in_cache')} | {m.get('fixtures_strict_player_gs')} | "
            f"{m.get('coverage_pct_strict', 0):.1%} |"
        )
    lines.append(f"\n**UEFA strict coverage:** {totals.get('uefa_coverage_pct_strict', 0):.1%}")
    lines.append(f"**Bookmakers:** {inventory.get('by_bookmaker', {})}")

    lines.extend(
        [
            "",
            "## Part C — Bridge expansion",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| WC bridges (54O) | {bridge_meta.get('wc_bridges')} |",
            f"| UEFA direct bridges | {bridge_meta.get('uefa_bridges')} |",
            f"| Merged bridges | {bridge_meta.get('merged_bridges')} |",
            f"| UEFA odds selections | {bridge_meta.get('uefa_odds_selections')} |",
            f"| Total odds selections | {bridge_meta.get('total_odds_selections')} |",
            "",
            "## Part D — Revalidation",
            "",
            "| Metric | Before | After | Δ |",
            "|--------|--------|-------|---|",
            f"| Fixtures with odds | {before.get('fixtures_with_odds')} | {after.get('fixtures_with_odds')} | {delta.get('fixtures_with_odds_delta')} |",
            f"| Odds coverage | {before.get('odds_coverage_pct', 0):.1%} | {after.get('odds_coverage_pct', 0):.1%} | {delta.get('odds_coverage_pp')} |",
            f"| Overall top-3 | {(before.get('overall') or {}).get('top3_hit')} | {(after.get('overall') or {}).get('top3_hit')} | {delta.get('overall_top3_pp')} |",
            f"| UEFA top-3 | {(before.get('uefa') or {}).get('top3_hit')} | {(after.get('uefa') or {}).get('top3_hit')} | {delta.get('uefa_top3_pp')} |",
            f"| Top-1 | {(before.get('overall') or {}).get('top1_hit')} | {(after.get('overall') or {}).get('top1_hit')} | — |",
            f"| Top-5 | {(before.get('overall') or {}).get('top5_hit')} | {(after.get('overall') or {}).get('top5_hit')} | — |",
            f"| MRR | {(before.get('overall') or {}).get('mrr')} | {(after.get('overall') or {}).get('mrr')} | — |",
            f"| Brier | {(before.get('calibration') or {}).get('brier')} | {(after.get('calibration') or {}).get('brier')} | {delta.get('brier_delta')} |",
            f"| ECE | {(before.get('calibration') or {}).get('ece')} | {(after.get('calibration') or {}).get('ece')} | {delta.get('ece_delta')} |",
            "",
            "## Part E — Impact",
            "",
            f"| Question | Answer |",
            f"|----------|--------|",
            f"| UEFA weakness baseline | {impact.get('uefa_weakness_baseline_top3')} |",
            f"| UEFA after expansion | {impact.get('uefa_after_expansion_top3')} |",
            f"| Gap to WC closed | {impact.get('gap_closed_pp')} pp ({impact.get('pct_of_gap_solved', 0):.1%} of gap) |",
            f"| Coverage gain | {impact.get('coverage_gain_pp')} pp |",
            f"| WC fixtures with odds | {after_meta.get('wc_fixtures_with_odds')} |",
            f"| UEFA fixtures with odds | {after_meta.get('uefa_fixtures_with_odds')} |",
            "",
            f"### Final recommendation: **`{rec}`**",
            "",
            "---",
            "",
            "## Constraints honored",
            "",
            "- No deploy, production, or live prediction changes",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
