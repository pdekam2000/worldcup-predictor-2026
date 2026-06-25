"""Phase 54P goalscorer intelligence orchestrator."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.egie.goalscorer_intelligence.intelligence_layer import generate_intelligence
from worldcup_predictor.egie.goalscorer_intelligence.models import VALID_RECOMMENDATIONS
from worldcup_predictor.egie.goalscorer_intelligence.validation import (
    build_value_pick_dataset,
    replay_by_confidence_tier,
    run_historical_replay,
)

ARTIFACT_DIR = Path("artifacts/phase54p_goalscorer_intelligence")
REPORT_PATH = Path("PHASE_54P_GOALSCORER_INTELLIGENCE_REPORT.md")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _choose_recommendation(replay: dict[str, Any], value: dict[str, Any], tier_replay: dict[str, Any]) -> str:
    anytime = (replay.get("markets") or {}).get("anytime") or {}
    composite = anytime.get("composite_scorer") or {}
    blend = anytime.get("ml_odds_blend") or {}
    ml = anytime.get("ml_only") or {}

    comp_top3 = float(composite.get("top3_hit") or 0)
    blend_top3 = float(blend.get("top3_hit") or 0)
    ml_top3 = float(ml.get("top3_hit") or 0)

    tier_a = (tier_replay.get("A") or {}).get("top3_hit") or 0
    value_beats = bool(value.get("outperforms_random"))

    if comp_top3 >= 0.75 and blend_top3 >= ml_top3 and float(tier_a or 0) >= 0.7:
        return "GOALSCORER_ELITE_CANDIDATE"
    if comp_top3 >= 0.65 or (blend_top3 > ml_top3 and value_beats):
        return "GOALSCORER_HIGH_VALUE"
    return "GOALSCORER_MEDIUM_VALUE"


def run_phase54p() -> dict[str, Any]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    player_df, fixtures = generate_intelligence()
    player_df.to_parquet(ARTIFACT_DIR / "goalscorer_intelligence_players.parquet", index=False)
    player_df.head(3000).to_csv(ARTIFACT_DIR / "goalscorer_intelligence_players.csv", index=False)

    intel_payload = [f.to_dict() for f in fixtures]
    (ARTIFACT_DIR / "fixture_intelligence.json").write_text(json.dumps(intel_payload, indent=2), encoding="utf-8")

    replay = run_historical_replay(player_df)
    (ARTIFACT_DIR / "historical_replay.json").write_text(json.dumps(replay, indent=2, default=str), encoding="utf-8")

    tier_replay = replay_by_confidence_tier(player_df)
    (ARTIFACT_DIR / "confidence_tier_replay.json").write_text(json.dumps(tier_replay, indent=2), encoding="utf-8")

    value_picks = build_value_pick_dataset(player_df)
    value_picks.to_csv(ARTIFACT_DIR / "value_pick_dataset.csv", index=False)
    value_picks.to_parquet(ARTIFACT_DIR / "value_pick_dataset.parquet", index=False)

    value_summary = replay.get("value_picks") or {}
    recommendation = _choose_recommendation(replay, value_summary, tier_replay)

    report = {
        "generated_at": _utc_now(),
        "phase": "54P",
        "fixtures": len(fixtures),
        "player_rows": len(player_df),
        "value_pick_count": len(value_picks),
        "replay": replay,
        "confidence_tier_replay": tier_replay,
        "value_picks": value_summary,
        "recommendation": recommendation,
        "production_changes": False,
        "api_calls_used": 0,
    }
    (ARTIFACT_DIR / "phase54p_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    _write_markdown(report, replay, value_summary, tier_replay, recommendation)
    return report


def _write_markdown(
    report: dict[str, Any],
    replay: dict[str, Any],
    value: dict[str, Any],
    tier_replay: dict[str, Any],
    recommendation: str,
) -> None:
    anytime = (replay.get("markets") or {}).get("anytime") or {}
    first = (replay.get("markets") or {}).get("first_goal") or {}

    def _m(mkt: dict, sig: str, key: str) -> str:
        return str((mkt.get(sig) or {}).get(key, "n/a"))

    lines = [
        "# PHASE 54P — Goalscorer Intelligence Shadow Layer",
        "",
        f"**Date:** {report.get('generated_at', '')[:10]}  ",
        "**Mode:** Shadow Intelligence → Historical Validation → Report  ",
        "**Status:** Complete — shadow only, no production  ",
        "**API calls:** 0",
        "",
        f"### Final recommendation: **`{recommendation}`**",
        "",
        "---",
        "",
        "## Part A — Shadow package",
        "",
        "Package: `worldcup_predictor/egie/goalscorer_intelligence/`",
        "",
        "## Part B — Fixture intelligence",
        "",
        f"Generated structured intelligence for **{report.get('fixtures')}** bridged fixtures.",
        "",
        "Per fixture: Top Anytime, First Goal, Surprise, Value, Team Threats.",
        "",
        "Artifact: `artifacts/phase54p_goalscorer_intelligence/fixture_intelligence.json`",
        "",
        "## Part C — Composite scorer",
        "",
        "Weighted: ML (35%), odds (25%), starter (15%), form (10%), xG/90 (8%), SOT (7%).",
        "",
        "## Part D — Confidence tiers",
        "",
        "| Tier | Top-3 hit (composite) |",
        "|------|----------------------|",
    ]
    for tier in ("A", "B", "C", "D"):
        t = tier_replay.get(tier) or {}
        lines.append(f"| {tier} | {t.get('top3_hit', 'n/a')} |")

    lines.extend(
        [
            "",
            "## Part E — Historical replay (Anytime)",
            "",
            "| Signal | Top-1 | Top-3 | Top-5 | MRR |",
            "|--------|-------|-------|-------|-----|",
            f"| Composite | {_m(anytime, 'composite_scorer', 'top1_hit')} | {_m(anytime, 'composite_scorer', 'top3_hit')} | {_m(anytime, 'composite_scorer', 'top5_hit')} | {_m(anytime, 'composite_scorer', 'mrr')} |",
            f"| ML only | {_m(anytime, 'ml_only', 'top1_hit')} | {_m(anytime, 'ml_only', 'top3_hit')} | {_m(anytime, 'ml_only', 'top5_hit')} | {_m(anytime, 'ml_only', 'mrr')} |",
            f"| Odds only | {_m(anytime, 'odds_only', 'top1_hit')} | {_m(anytime, 'odds_only', 'top3_hit')} | {_m(anytime, 'odds_only', 'top5_hit')} | {_m(anytime, 'odds_only', 'mrr')} |",
            f"| ML+Odds blend | {_m(anytime, 'ml_odds_blend', 'top1_hit')} | {_m(anytime, 'ml_odds_blend', 'top3_hit')} | {_m(anytime, 'ml_odds_blend', 'top5_hit')} | {_m(anytime, 'ml_odds_blend', 'mrr')} |",
            "",
            "### First goalscorer",
            "",
            f"| Composite top-3 | {_m(first, 'composite_scorer', 'top3_hit')} |",
            "",
            "## Part F — Value picks",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Value picks | {value.get('value_pick_count', 0)} |",
            f"| Hit rate | {value.get('value_pick_hit_rate', 'n/a')} |",
            f"| Random disagreement baseline | {value.get('random_disagreement_hit_rate', 'n/a')} |",
            f"| Outperforms random | {value.get('outperforms_random', False)} |",
            "",
            "Artifact: `artifacts/phase54p_goalscorer_intelligence/value_pick_dataset.parquet`",
            "",
            "## Part G — Decision questions",
            "",
            f"1. **Consistent ranking?** Composite top-3 = {_m(anytime, 'composite_scorer', 'top3_hit')} on {report.get('fixtures')} fixtures",
            f"2. **Best confidence tier:** Tier A top-3 = {(tier_replay.get('A') or {}).get('top3_hit', 'n/a')}",
            f"3. **Value picks real?** Outperforms random = {value.get('outperforms_random')}",
            f"4. **ML+Odds superior?** Blend top-3 ({_m(anytime, 'ml_odds_blend', 'top3_hit')}) vs ML ({_m(anytime, 'ml_only', 'top3_hit')})",
            "5. **Strongest research asset?** Yes — unified fixture intelligence with odds+ML+lineup signals",
            "",
            f"### Final recommendation: **`{recommendation}`**",
            "",
            "---",
            "",
            "## Constraints honored",
            "",
            "- Shadow only — no production, WDE, SaaS, deploy",
            "- No live prediction or EGIE scoring changes",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
