"""Generate PHASE_API_H report from pipeline artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "PHASE_API_H_UEFA_CLUB_EGIE_SPORTMONKS_REPORT.md"


def _impact_tier(backtest: dict[str, Any]) -> list[dict[str, str]]:
    strategies = backtest.get("strategies") or {}
    base = float((strategies.get("A") or {}).get("first_goal_team_hit_rate") or 0)
    tiers: list[dict[str, str]] = []
    for key, label, feature in [
        ("B", "xG", "xg"),
        ("C", "Pressure", "pressure"),
        ("D", "Odds", "odds"),
        ("E", "Combined xG+Pressure+Odds", "combo"),
        ("F", "Full Sportmonks", "full"),
    ]:
        rate = float((strategies.get(key) or {}).get("first_goal_team_hit_rate") or 0)
        delta = round((rate - base) * 100, 2)
        if delta >= 2:
            tier = "S"
        elif delta >= 0.5:
            tier = "A"
        else:
            tier = "B"
        tiers.append({"strategy": key, "feature": label, "fg_delta_pp": f"{delta:+.2f}", "tier": tier})
    return tiers


def write_report(
    *,
    coverage: dict[str, Any],
    mapping: dict[str, Any],
    ingest: dict[str, Any],
    utilization: dict[str, Any],
    backtest: dict[str, Any],
    survival_path: str,
) -> None:
    strategies = backtest.get("strategies") or {}
    lines = [
        "# PHASE API-H — UEFA Club EGIE Sportmonks Dataset",
        "",
        "**Mode:** Audit → Ingest → Validate → Backtest → Report",
        "**Production deploy:** NO",
        "",
        "## Executive Summary",
        "",
        f"- **Fixtures mapped:** {mapping.get('fixture_count', 0)}",
        f"- **Survival dataset:** `{survival_path}`",
        f"- **Winning strategy:** {backtest.get('winning_strategy', 'A')}",
        f"- **Promotion safe:** {backtest.get('production_promotion_safe')}",
        "",
        "## STEP 1 — League Coverage",
        "",
        "| Competition | league_id | Fixtures sampled | Finished sampled |",
        "|-------------|-----------|------------------|------------------|",
    ]
    for lg in coverage.get("leagues") or []:
        lines.append(
            f"| {lg.get('league_name')} | {lg.get('league_id')} | "
            f"{lg.get('fixtures_sampled')} | {lg.get('finished_fixtures_sampled')} |"
        )

    lines.extend(
        [
            "",
            f"API calls (coverage audit): {coverage.get('api_calls_made')}",
            "",
            "## STEP 2 — Fixture Mapping",
            "",
            f"Total fixtures: **{mapping.get('fixture_count')}**",
            f"By competition: `{mapping.get('by_competition_key')}`",
            "",
            "## STEP 3 — Sportmonks Ingest",
            "",
            f"```json\n{ingest}\n```",
            "",
            "## STEP 4 — Provider Coverage",
            "",
            f"```json\n{utilization}\n```",
            "",
            "## STEP 6 — A–F Backtest",
            "",
            "| Strategy | FG Team | Goal Range | Soft Minute | Paid-data fixtures |",
            "|----------|---------|------------|-------------|-------------------|",
        ]
    )
    for key in ("A", "B", "C", "D", "E", "F"):
        s = strategies.get(key) or {}
        cov = s.get("coverage") or {}
        lines.append(
            f"| {key} | {s.get('first_goal_team_hit_rate')} | {s.get('goal_range_hit_rate')} | "
            f"{s.get('goal_minute_soft_hit_rate')} | {cov.get('with_paid_data')}/{cov.get('eligible')} |"
        )

    lines.extend(["", "## STEP 7 — Feature Impact Ranking", ""])
    for row in _impact_tier(backtest):
        lines.append(
            f"- **Tier {row['tier']}** — Strategy {row['strategy']} ({row['feature']}): "
            f"FG delta {row['fg_delta_pp']} pp vs baseline"
        )

    lines.extend(
        [
            "",
            "## Recommendation",
            "",
            "Use UEFA club competitions (CL/EL/Conference/Super Cup) for Sportmonks-enriched EGIE research. "
            "Do not deploy to production until a strategy beats baseline A by >1pp with stable calibration.",
            "",
            "**STOP — no production deploy.**",
        ]
    )
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report -> {REPORT}")
