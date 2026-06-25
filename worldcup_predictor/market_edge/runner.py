"""Phase 55A market edge discovery orchestrator."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.market_edge.collectors import collect_all_profiles
from worldcup_predictor.market_edge.models import MARKET_IDS, VALID_RECOMMENDATIONS
from worldcup_predictor.market_edge.scoring import rank_markets, recommend_dev_hours, select_candidates

ARTIFACT_DIR = Path("artifacts/phase55a_market_edge_discovery")
REPORT_PATH = Path("PHASE_55A_MARKET_EDGE_DISCOVERY_REPORT.md")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_phase55a() -> dict[str, Any]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    profiles = collect_all_profiles()
    ranked = rank_markets(profiles)
    candidates = select_candidates(ranked)
    dev_rec = recommend_dev_hours(ranked)

    ranking_payload = [m.to_dict() for m in ranked]
    (ARTIFACT_DIR / "market_profiles.json").write_text(
        json.dumps({k: v.to_dict() for k, v in profiles.items()}, indent=2),
        encoding="utf-8",
    )
    (ARTIFACT_DIR / "market_rankings.json").write_text(json.dumps(ranking_payload, indent=2), encoding="utf-8")
    (ARTIFACT_DIR / "candidates.json").write_text(json.dumps(candidates, indent=2), encoding="utf-8")
    (ARTIFACT_DIR / "dev_hours_recommendation.json").write_text(json.dumps(dev_rec, indent=2), encoding="utf-8")

    recommendation = dev_rec.get("recommendation", "MULTI_MARKET_PORTFOLIO")
    if recommendation not in VALID_RECOMMENDATIONS:
        recommendation = "MULTI_MARKET_PORTFOLIO"

    report = {
        "generated_at": _utc_now(),
        "phase": "55A",
        "markets_evaluated": len(MARKET_IDS),
        "rankings": ranking_payload,
        "candidates": candidates,
        "dev_hours_recommendation": dev_rec,
        "recommendation": recommendation,
        "production_changes": False,
        "api_calls_used": 0,
    }
    (ARTIFACT_DIR / "phase55a_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    _write_markdown(report, ranked, candidates, dev_rec)
    return report


def _write_markdown(
    report: dict[str, Any],
    ranked: list,
    candidates: dict[str, Any],
    dev_rec: dict[str, Any],
) -> None:
    lines = [
        "# PHASE 55A — Market Edge Discovery",
        "",
        f"**Date:** {report.get('generated_at', '')[:10]}  ",
        "**Mode:** Research — aggregate existing infrastructure  ",
        "**Status:** Complete  ",
        "**API calls:** 0",
        "",
        f"### Next 100 dev hours → **`{dev_rec.get('recommendation')}`** ({dev_rec.get('target_market')})",
        "",
        dev_rec.get("rationale", ""),
        "",
        "---",
        "",
        "## Market rankings (MARKET_EDGE_SCORE)",
        "",
        "| Rank | Market | Score | Accuracy | Metric | Dataset | Odds cov | Production |",
        "|------|--------|-------|----------|--------|---------|----------|------------|",
    ]
    for i, m in enumerate(ranked, start=1):
        p = m.profile
        acc = f"{p.accuracy:.1%}" if p.accuracy is not None else "n/a"
        lines.append(
            f"| {i} | {m.display_name} | **{m.market_edge_score}** | {acc} | {p.accuracy_metric} | "
            f"{p.dataset_size:,} | {p.odds_availability_pct:.1%} | {p.production_status} |"
        )

    lines.extend(["", "## Score breakdown (top 5)", ""])
    for m in ranked[:5]:
        lines.append(f"### {m.display_name} — {m.market_edge_score}")
        for k, v in m.score_breakdown.items():
            lines.append(f"- {k}: {v}")
        lines.append("")

    lines.extend(
        [
            "## TOP 10 strongest markets",
            "",
        ]
    )
    for i, item in enumerate(candidates.get("top10_strongest") or [], 1):
        lines.append(f"{i}. **{item.get('display_name')}** — score {item.get('market_edge_score')}")

    lines.extend(["", "## TOP 5 research candidates", ""])
    for i, item in enumerate(candidates.get("top5_research_candidates") or [], 1):
        status = (item.get("profile") or {}).get("production_status", "")
        lines.append(f"{i}. **{item.get('display_name')}** — score {item.get('market_edge_score')} ({status})")

    lines.extend(["", "## TOP 3 production candidates", ""])
    for i, item in enumerate(candidates.get("top3_production_candidates") or [], 1):
        lines.append(f"{i}. **{item.get('display_name')}** — score {item.get('market_edge_score')}")

    lines.extend(
        [
            "",
            "## Per-market detail",
            "",
        ]
    )
    for m in ranked:
        p = m.profile
        lines.extend(
            [
                f"### {p.display_name}",
                "",
                f"| Dimension | Value |",
                f"|-----------|-------|",
                f"| Dataset size | {p.dataset_size:,} |",
                f"| Coverage | {p.coverage_pct:.1%} |",
                f"| Accuracy | {p.accuracy} ({p.accuracy_metric}) |",
                f"| Baseline | {p.baseline_accuracy} |",
                f"| Calibration ECE | {p.calibration_ece} |",
                f"| Stability | {p.stability_score} |",
                f"| Odds availability | {p.odds_availability_pct:.1%} |",
                f"| ROI potential | {p.roi_potential} |",
                f"| Infrastructure | {p.infrastructure_tier} |",
                f"| Notes | {p.notes or '—'} |",
                "",
            ]
        )

    lines.extend(
        [
            "---",
            "",
            "## Constraints honored",
            "",
            "- No deploy, production changes, or live prediction changes",
            "- Research aggregation only",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
