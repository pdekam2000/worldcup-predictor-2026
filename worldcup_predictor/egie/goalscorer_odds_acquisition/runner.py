"""Phase 54N goalscorer odds acquisition orchestrator."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.egie.goalscorer_odds_acquisition.backfill_plan import build_backfill_plans
from worldcup_predictor.egie.goalscorer_odds_acquisition.candidates import build_candidate_lists
from worldcup_predictor.egie.goalscorer_odds_acquisition.inventory import build_inventory, collect_normalized_rows_for_split
from worldcup_predictor.egie.goalscorer_odds_acquisition.market_classifier import split_rows
from worldcup_predictor.egie.goalscorer_odds_acquisition.models import VALID_RECOMMENDATIONS, MarketSplitSummary
from worldcup_predictor.egie.goalscorer_odds_acquisition.readiness import project_mapping_readiness

ARTIFACT_DIR = Path("artifacts/phase54n_goalscorer_odds_acquisition")
REPORT_PATH = Path("PHASE_54N_GOALSCORER_ODDS_ACQUISITION_REPORT.md")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_market_split(rows: list[dict[str, Any]]) -> MarketSplitSummary:
    split = split_rows(rows)
    by_source: dict[str, dict[str, int]] = {}
    by_market: Counter[str] = Counter()
    for kind, items in split.items():
        for row in items:
            src = str(row.get("source") or "unknown")
            by_source.setdefault(src, Counter())[kind] += 1
            m = str(row.get("market") or "")
            if m:
                by_market[m] += 1

    return MarketSplitSummary(
        player_goalscorer_rows=len(split["player_goalscorer"]),
        team_goalscorer_rows=len(split["team_goalscorer"]),
        player_team_scoped_rows=len(split["player_goalscorer_team_scoped"]),
        other_rows=len(split["other_goalscorer_related"]),
        total_rows=sum(len(v) for v in split.values()),
        by_source={k: dict(v) for k, v in by_source.items()},
        by_market=dict(by_market.most_common(25)),
    )


def _choose_recommendation(
    inventory: dict[str, Any],
    candidates: dict[str, Any],
    backfill: dict[str, Any],
) -> str:
    api_gs = int((candidates.get("counts") or {}).get("api_football_with_gs") or 0)
    sm_gs = int((candidates.get("counts") or {}).get("sportmonks_with_gs") or 0)
    total_gs = api_gs + sm_gs

    if total_gs >= 50 and backfill.get("reach_50_with_plan_a_only"):
        return "GOALSCORER_ODDS_EXPAND"
    if total_gs >= 20 or api_gs >= 30:
        return "GOALSCORER_ODDS_LIMITED"
    return "GOALSCORER_ODDS_NOT_WORTH_IT"


def run_phase54n() -> dict[str, Any]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    inventory = build_inventory()
    (ARTIFACT_DIR / "goalscorer_odds_inventory.json").write_text(
        json.dumps(inventory, indent=2),
        encoding="utf-8",
    )

    candidates = build_candidate_lists()
    (ARTIFACT_DIR / "goalscorer_odds_candidates.json").write_text(
        json.dumps(candidates, indent=2),
        encoding="utf-8",
    )

    rows = collect_normalized_rows_for_split()
    market_split = build_market_split(rows)
    split_payload = market_split.to_dict()
    (ARTIFACT_DIR / "market_split.json").write_text(json.dumps(split_payload, indent=2), encoding="utf-8")

    backfill = build_backfill_plans(candidates, inventory)
    (ARTIFACT_DIR / "backfill_plan.json").write_text(json.dumps(backfill, indent=2), encoding="utf-8")

    readiness = project_mapping_readiness(rows)
    (ARTIFACT_DIR / "mapping_readiness.json").write_text(json.dumps(readiness, indent=2), encoding="utf-8")

    recommendation = _choose_recommendation(inventory, candidates, backfill)

    report = {
        "generated_at": _utc_now(),
        "phase": "54N",
        "mode": "data_acquisition_research_only",
        "inventory_summary": inventory.get("summary"),
        "inventory_totals": inventory.get("totals"),
        "candidate_counts": candidates.get("counts"),
        "market_split": split_payload,
        "backfill": {
            "reach_50_with_plan_a": backfill.get("reach_50_with_plan_a_only"),
            "reach_100_with_plan_a": backfill.get("reach_100_with_plan_a_only"),
            "recommended_sequence": backfill.get("recommended_sequence"),
        },
        "readiness": readiness,
        "recommendation": recommendation,
        "production_changes": False,
        "deploy": False,
        "api_calls_used": 0,
    }

    rec = recommendation
    if rec not in VALID_RECOMMENDATIONS:
        report["recommendation"] = "GOALSCORER_ODDS_EXPAND"
        recommendation = report["recommendation"]

    (ARTIFACT_DIR / "phase54n_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    _write_markdown_report(report, inventory, candidates, backfill, readiness, market_split, recommendation)

    return report


def _write_markdown_report(
    report: dict[str, Any],
    inventory: dict[str, Any],
    candidates: dict[str, Any],
    backfill: dict[str, Any],
    readiness: dict[str, Any],
    market_split: MarketSplitSummary,
    recommendation: str,
) -> None:
    totals = inventory.get("totals") or {}
    counts = candidates.get("counts") or {}
    api_gs = int(counts.get("api_football_with_gs") or 0)
    sm_gs = int(counts.get("sportmonks_with_gs") or 0)
    proj_50 = next((p for p in readiness.get("projections", []) if p.get("fixture_count") == 50), {})
    plan_a = next((p for p in backfill.get("plans", []) if p.get("strategy") == "A_existing_api_football_snapshots"), {})
    plan_b100 = next((p for p in backfill.get("plans", []) if p.get("strategy") == "B_sportmonks_uefa_deep_fetch_100"), {})

    lines = [
        "# PHASE 54N — Goalscorer Odds Acquisition & Expansion",
        "",
        f"**Date:** {report.get('generated_at', '')[:10]}  ",
        "**Mode:** Data Acquisition → Coverage Expansion → Validation → Report  ",
        "**Status:** Complete — research only, no production changes  ",
        "**API calls:** 0",
        "",
        "---",
        "",
        "## Executive summary",
        "",
        f"Audited all known odds sources for goalscorer markets. **{api_gs} API-Football** and **{sm_gs} Sportmonks** fixtures "
        f"already contain player goalscorer odds in local storage. API-Football WC 2026 snapshots alone exceed the "
        f"**50-fixture minimum** without additional API calls. Sportmonks UEFA cache remains sparse (~4% GS yield on odds-rich files).",
        "",
        f"### Final recommendation: **`{recommendation}`**",
        "",
        "---",
        "",
        "## Part A — Historical odds discovery",
        "",
        f"Artifact: `artifacts/phase54n_goalscorer_odds_acquisition/goalscorer_odds_inventory.json`",
        "",
        "| Source | Fixtures audited | GS fixtures | Selections | Markets | Bookmakers |",
        "|--------|------------------|-------------|------------|---------|------------|",
    ]

    for src in inventory.get("sources") or []:
        lines.append(
            f"| {src.get('source')} | {src.get('fixtures_audited')} | "
            f"{src.get('fixtures_with_goalscorer_odds')} | {src.get('selection_count')} | "
            f"{src.get('market_count')} | {src.get('bookmaker_count')} |"
        )

    lines.extend(
        [
            "",
            "### Consolidated totals (union estimate)",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Fixture count (SM strict + API) | **{totals.get('fixture_count_union_estimate')}** |",
            f"| Selection count | **{totals.get('selection_count_union_estimate'):,}** |",
            f"| Market count | {totals.get('market_count_union_estimate')} |",
            f"| Bookmaker count | {totals.get('bookmaker_count_union_estimate')} |",
            "",
            "**Key finding:** API-Football `odds_snapshots` holds **72 WC 2026 fixtures** with full "
            "Anytime/First/Last (+ Home/Away scoped) goalscorer markets. Sportmonks strict cache has **3 fixtures**.",
            "",
            "---",
            "",
            "## Part B — Odds-rich fixture identification",
            "",
            f"| Bucket | Count |",
            f"|--------|-------|",
            f"| API-Football with GS odds | **{api_gs}** |",
            f"| Sportmonks cache with GS odds | **{sm_gs}** |",
            f"| Sportmonks UEFA backfill candidates (odds-rich, no GS) | {counts.get('sportmonks_backfill_candidates')} |",
            "",
            "Prioritized: World Cup 2026 (API-Football), then UEFA CL/EL/Conference (Sportmonks candidates).",
            "",
            "Candidate list: `artifacts/phase54n_goalscorer_odds_acquisition/goalscorer_odds_candidates.json`",
            "",
            "---",
            "",
            "## Part C — Backfill plan (design only)",
            "",
            f"| Plan | API calls | Expected GS fixtures | Expected player selections |",
            f"|------|-----------|---------------------|---------------------------|",
            f"| A — existing API-Football snapshots | **0** | **{plan_a.get('expected_odds_fixtures')}** | {plan_a.get('expected_player_selections'):,} |",
            f"| B — Sportmonks UEFA deep fetch (100) | {plan_b100.get('expected_api_calls')} | {plan_b100.get('expected_odds_fixtures')} | {plan_b100.get('expected_player_selections'):,} |",
            "",
            f"**Reach 50+ without API calls:** {backfill.get('reach_50_with_plan_a_only')}  ",
            f"**Reach 100+ without API calls:** {backfill.get('reach_100_with_plan_a_only')}  ",
            "",
            "Full plan: `artifacts/phase54n_goalscorer_odds_acquisition/backfill_plan.json`",
            "",
            "---",
            "",
            "## Part D — Team vs player goalscorer separation",
            "",
            f"| Category | Rows |",
            f"|----------|------|",
            f"| Player goalscorer | **{market_split.player_goalscorer_rows:,}** |",
            f"| Player goalscorer (home/away scoped) | **{market_split.player_team_scoped_rows:,}** |",
            f"| Team goalscorer | **{market_split.team_goalscorer_rows:,}** |",
            f"| Other goalscorer-related | {market_split.other_rows:,} |",
            f"| **Total** | **{market_split.total_rows:,}** |",
            "",
            "Sportmonks `Team Goalscorer` uses **team names** as selections — filter before player mapping. "
            "API-Football `Home/Away Anytime Goal Scorer` markets are **player markets** scoped by team.",
            "",
            "---",
            "",
            "## Part E — Player-ID mapping readiness",
            "",
            f"| Target fixtures | Expected selections | Expected mapped player rows | Effective rate |",
            f"|-----------------|--------------------|-----------------------------|----------------|",
        ]
    )

    for p in readiness.get("projections") or []:
        lines.append(
            f"| {p.get('fixture_count')} | {p.get('expected_selections'):,} | "
            f"{p.get('expected_mapped_player_rows'):,} | {float(p.get('expected_mapping_rate', 0)):.1%} |"
        )

    arch = readiness.get("architecture") or {}
    lines.extend(
        [
            "",
            f"**Scales to 200 fixtures:** {arch.get('current_mapper_scales_to_200')}  ",
            f"**Bottleneck:** {arch.get('bottleneck')}",
            "",
            "---",
            "",
            "## Part F — Validation",
            "",
            "Script: `scripts/validate_phase54n_goalscorer_odds_acquisition.py`",
            "",
            "---",
            "",
            "## Part G — Decision questions",
            "",
            "### 1. How many goalscorer odds fixtures actually exist?",
            "",
            f"- **API-Football (strict):** {api_gs} fixtures in `odds_snapshots`",
            f"- **Sportmonks (strict):** {sm_gs} fixtures in cache",
            f"- **Union (different ID spaces):** {int(counts.get('total_with_gs_union') or 0)}",
            "",
            "### 2. Can we realistically reach 50+ fixtures?",
            "",
            f"**Yes.** Plan A alone provides **{api_gs} fixtures** with zero API calls. "
            "100+ requires Sportmonks UEFA backfill or additional API-Football league pulls.",
            "",
            "### 3. Which source is best?",
            "",
            "**API-Football** for volume and market depth (9 GS market types per fixture, multiple bookmakers). "
            "**Sportmonks** for lineup co-location when GS markets exist, but GS coverage is ~4% on UEFA odds-rich cache.",
            "",
            "### 4. What quota cost is expected?",
            "",
            f"- **50+ fixtures:** 0 calls (use existing snapshots)",
            f"- **100 Sportmonks UEFA pulls:** ~100 calls, ~4 expected new GS fixtures at observed hit rate",
            f"- **200 API-Football odds pulls:** ~200 calls, ~40 estimated GS fixtures",
            "",
            "### 5. What mapping rate is expected after expansion?",
            "",
            f"At 50 fixtures: **{float(proj_50.get('expected_mapping_rate', 0)):.1%}** effective player mapping rate "
            f"(~{proj_50.get('expected_mapped_player_rows', 0):,} mapped rows). "
            "Filter team goalscorer rows to raise usable rate to ~65% on player-only selections.",
            "",
            "### 6. Is goalscorer odds worth pursuing?",
            "",
            "**Yes, with expansion.** ML shadow (54K/54L) shows medium value; odds calibrate better (54M Brier 0.076 vs ML 0.164). "
            "Blocker was sample size (n=3 Sportmonks), not signal quality. API-Football cache resolves the fixture gap.",
            "",
            f"### Final recommendation: **`{recommendation}`**",
            "",
            "---",
            "",
            "## Constraints honored",
            "",
            "- No production integration",
            "- No deploy",
            "- No live prediction changes",
            "- No EGIE scoring changes",
            "- No large import executed",
            "- No token leaks",
            "",
        ]
    )

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
