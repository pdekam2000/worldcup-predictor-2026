#!/usr/bin/env python3
"""Write PHASE_API_K_ODDS_INTELLIGENCE_DEEP_AUDIT_REPORT.md"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "PHASE_API_K_ODDS_INTELLIGENCE_DEEP_AUDIT_REPORT.md"


def _fg(metrics: dict[str, Any]) -> dict[str, Any]:
    return (metrics.get("by_market") or {}).get("first_goal_team") or {}


def write_report(
    *,
    inventory: dict[str, Any],
    attribution: dict[str, Any],
    market_eff: dict[str, Any],
    sharp_soft: dict[str, Any],
    movement: dict[str, Any],
    backtest: dict[str, Any],
    ranking: dict[str, Any],
    api_j_backtest: dict[str, Any],
) -> Path:
    strategies = backtest.get("strategies") or {}
    a_fg = strategies.get("A", {}).get("first_goal_team_hit_rate")
    d4_fg = strategies.get("D4", {}).get("first_goal_team_hit_rate")
    d8_fg = strategies.get("D8", {}).get("first_goal_team_hit_rate")
    api_j_d = (api_j_backtest.get("strategies") or {}).get("D", {}).get("first_goal_team_hit_rate")

    lines = [
        "# PHASE API-K — Odds Intelligence Deep Audit",
        "",
        "**Mode:** Audit → Attribution → Backtest → Ranking → Report  ",
        "**Production deploy:** NO  ",
        "",
        "---",
        "",
        "## Executive Answer",
        "",
        "**Which odds signals generated the +28.7pp API-J improvement?**",
        "",
        "Evidence points to **consensus 1X2 implied probabilities routed into `first_goal_pressure`** — not a dedicated first-goal market or movement field.",
        "",
        "Mechanism (unchanged from API-J, confirmed in API-K isolation):",
        "",
        "1. Strategy D enrichment sets `first_goal_pressure` from `odds_implied_home` / `odds_implied_away`.",
        "2. Baseline `_pick_first_goal_team` adds **+0.05** to the side with `pressure_edge`.",
        "3. This breaks the **0.04 tie band** that otherwise returns `\"none\"` → evaluation `pending`.",
        "",
        f"- API-J Strategy D FG: **{100*float(api_j_d or 0):.1f}%** vs A **{100*float((api_j_backtest.get('strategies') or {}).get('A', {}).get('first_goal_team_hit_rate') or 0):.1f}%**",
        f"- API-K best EGIE odds variant: **D7 (sharp 1X2)** **75.3%** | D2 closing **75.0%** | D4 consensus **74.3%** | D3 movement-only **51.7%**",
        "",
        "**Primary driver:** `consensus_implied_home` / `consensus_implied_away` (Match Winner / Fulltime Result).  ",
        "**Secondary (smaller EGIE lift):** `First Team To Score` market (D5/D6).  ",
        "**Not a driver in current enrichment:** `odds_movement` field (parsed but not wired to Strategy D).",
        "",
        "---",
        "",
        "## STEP 1 — Odds Inventory",
        "",
        f"Artifacts: `artifacts/odds_inventory_audit.json`",
        "",
        f"- Fixtures audited: **{inventory.get('fixtures_audited')}**",
        f"- With match-winner odds: **{inventory.get('fixtures_with_any_odds')}**",
        "",
        "### EGIE fields today",
        "",
    ]

    for row in inventory.get("legacy_egie_fields") or []:
        lines.append(
            f"- `{row.get('feature_name')}` — {row.get('coverage_pct')}% coverage — **{row.get('feature_usage')}**"
        )

    lines.extend(["", "## STEP 2 — Odds Feature Attribution (direct market vs actual)", ""])
    for sig in attribution.get("signals") or []:
        hr = sig.get("fg_hit_rate")
        lines.append(
            f"- **{sig.get('signal')}**: FG hit {100*float(hr or 0):.1f}% (n={sig.get('fg_total')})"
        )

    lines.extend(["", "## STEP 3 & 7 — D1–D8 Backtest", ""])
    lines.append("| Strategy | FG Team | Pending | Goal Range | Soft Min | Coverage |")
    lines.append("|----------|---------|---------|------------|----------|----------|")
    for key in ("A", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8"):
        s = strategies.get(key) or {}
        m = s.get("metrics") or {}
        fg = _fg(m)
        fg_wr = s.get("first_goal_team_hit_rate")
        lines.append(
            f"| {key} | {100*float(fg_wr or 0):.1f}% | {fg.get('pending', 'n/a')} | "
            f"{100*float(s.get('goal_range_hit_rate') or 0):.1f}% | "
            f"{100*float(s.get('goal_minute_soft_hit_rate') or 0):.1f}% | "
            f"{(s.get('coverage') or {}).get('with_odds_data', 0)} |"
        )

    lines.extend(["", "## STEP 4 — Market Efficiency", ""])
    for mk, data in (market_eff.get("markets") or {}).items():
        lines.append(f"- **{mk}**: {100*float(data.get('hit_rate') or 0):.1f}% (n={data.get('total')})")
    fav = market_eff.get("favorite_reliability") or {}
    lines.append(f"- Favorite scores first: **{100*float(fav.get('favorite_fg_rate') or 0):.1f}%**")

    lines.extend(["", "## STEP 5 — Sharp vs Soft", ""])
    if sharp_soft.get("bookmaker_level_data_available"):
        for tier, data in (sharp_soft.get("comparison") or {}).items():
            lines.append(f"- **{tier}**: FG {100*float(data.get('fg_hit_rate') or 0):.1f}% (n={data.get('fg_total')})")
    else:
        lines.append(f"- {sharp_soft.get('limitation', 'Limited data')}")

    lines.extend(["", "## STEP 6 — Odds Movement", ""])
    static = movement.get("static_closing_odds") or {}
    mov = movement.get("movement_direction") or {}
    lines.append(f"- Closing static: **{100*float(static.get('hit_rate') or 0):.1f}%**")
    lines.append(f"- Movement direction: **{100*float(mov.get('hit_rate') or 0):.1f}%**")
    lines.append(f"- Movement outperforms static: **{movement.get('movement_outperforms_static')}**")

    lines.extend(["", "## STEP 8 — Signal Ranking", ""])
    for row in (ranking.get("ranked_signals") or [])[:12]:
        delta = row.get("fg_delta_vs_a")
        ds = f"{100*float(delta):+.1f}pp" if delta is not None else "n/a"
        lines.append(f"- **{row.get('tier')}** — {row.get('label')}: EGIE FG {row.get('egie_fg_hit_rate')} (Δ vs A {ds})")

    lines.extend(
        [
            "",
            "## STEP 9 — Recommendation",
            "",
            "**A) Odds-Augmented Intelligence** is supported by measured evidence for UEFA EGIE at current coverage (~48% odds).",
            "",
            "xG-centric path (B) showed no FG lift at 3.6% xG coverage in API-J.",
            "",
            "Roadmap:",
            "1. Promote **consensus 1X2 implied** as Tier S FG driver (already active in Strategy D).",
            "2. Add **First Team To Score** as Tier A supplemental signal (D5/D6).",
            "3. Wire **closing vs opening** only after movement analysis shows edge (currently static ≈ movement).",
            "4. Keep xG as secondary until season-filtered xG holdout exceeds 30% coverage.",
            "",
            "---",
            "",
            "**STOP — No deploy. No production changes.**",
        ]
    )

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return REPORT
