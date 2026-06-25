#!/usr/bin/env python3
"""Write PHASE_K2_DIRECT_FIRST_GOAL_MARKET_AUDIT_REPORT.md"""

from __future__ import annotations

from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "PHASE_K2_DIRECT_FIRST_GOAL_MARKET_AUDIT_REPORT.md"


def write_report(
    *,
    inventory: dict[str, Any],
    coverage: dict[str, Any],
    backtest: dict[str, Any],
    books: dict[str, Any],
    ranking: dict[str, Any],
) -> Path:
    strategies = backtest.get("strategies") or {}
    strongest = ranking.get("strongest_signal") or {}
    strongest_peak = ranking.get("strongest_signal_peak") or {}
    ranked = ranking.get("ranked") or []

    a = strategies.get("A") or {}
    d = strategies.get("D") or {}
    c = strategies.get("C") or {}
    e = strategies.get("E") or {}
    f = strategies.get("F") or {}

    lines = [
        "# PHASE K2 — Direct First Goal Market Audit",
        "",
        "**Mode:** Audit → Backtest → Attribution → Report  ",
        "**Production deploy:** NO  ",
        "",
        "---",
        "",
        "## Executive Answer",
        "",
        "**What is the single strongest odds-derived signal for First Goal Team?**",
        "",
    ]

    lines.append(
        f"**{strongest.get('label', 'N/A')}** (strategy {strongest.get('signal', '')}) — "
        f"**{100*float(strongest.get('fg_hit_rate') or 0):.1f}%** FG Team accuracy "
        f"on **{strongest.get('coverage')}** evaluable fixtures (≥50 coverage threshold for robust ranking)."
    )
    if strongest_peak and strongest_peak.get("signal") != strongest.get("signal"):
        lines.append(
            f"\nPeak single-book FTS (**{strongest_peak.get('label')}**) reached "
            f"**{100*float(strongest_peak.get('fg_hit_rate') or 0):.1f}%** but on only "
            f"**{strongest_peak.get('coverage')}** fixtures — not used as primary conclusion."
        )
    lines.extend(
        [
            "",
            "### Key questions answered",
            "",
            f"1. **Is Team To Score First stronger than Match Winner?** "
            f"Direct FTS (D): **{100*float(d.get('direct_fg_accuracy') or 0):.1f}%** vs consensus MW (A): **{100*float(a.get('direct_fg_accuracy') or 0):.1f}%** — "
            f"{'FTS wins' if (d.get('direct_fg_accuracy') or 0) > (a.get('direct_fg_accuracy') or 0) else 'MW wins or tie'}.",
            "",
            f"2. **Is First Goal Market stronger than Consensus 1X2?** Same comparison as above (FTS market vs MW implied).",
            "",
            f"3. **Are Sharp FG Markets stronger than Sharp 1X2?** "
            f"**Cannot compare on this cache** — sharp FTS (E) has **0% fixture coverage** "
            f"(Pinnacle/SBO offer MW but not FTS in UEFA cache). Sharp MW (C): **{100*float(c.get('direct_fg_accuracy') or 0):.1f}%** remains best sharp signal.",
            "",
            "4. **Can direct goal markets become a dedicated FG engine?** "
            f"**Partially.** Combined FG consensus (F) reaches **{100*float(f.get('direct_fg_accuracy') or 0):.1f}%** "
            f"(vs sharp MW **{100*float(c.get('direct_fg_accuracy') or 0):.1f}%**), but direct FTS alone (D) "
            f"**underperforms** consensus MW (A). Best path: keep MW enrichment primary; FTS as Tier A sidecar.",
            "",
            "---",
            "",
            "## STEP 1 — Market Inventory",
            "",
            f"Artifact: `artifacts/first_goal_market_inventory.json`",
            "",
            f"- Fixtures audited: **{inventory.get('fixtures_audited')}**",
            f"- Primary direct FG market: **{inventory.get('primary_direct_fg_market')}**",
            "",
            "| Market | Fixture coverage | Rows |",
            "|--------|------------------|------|",
        ]
    )

    for m in inventory.get("first_goal_related_markets") or []:
        if m.get("market_key") == "other_first_goal_related":
            continue
        lines.append(
            f"| {m.get('market_name', m.get('market_key'))} | "
            f"{m.get('fixture_coverage')} ({m.get('fixture_coverage_pct')}%) | "
            f"{m.get('odds_row_count', 'n/a')} |"
        )

    lines.extend(["", "## STEP 2 — Coverage Audit", ""])
    for row in coverage.get("signals") or []:
        lines.append(
            f"- **{row.get('signal')}**: {row.get('fixture_coverage_pct')}% fixtures "
            f"({row.get('fixture_coverage')}/{coverage.get('fixtures_audited')})"
        )

    lines.extend(
        [
            "",
            "## STEP 3 — Direct FG Backtest (A–F)",
            "",
            "| Strategy | Signal | Direct FG % | EGIE FG % | Pending % | Coverage |",
            "|----------|--------|-------------|-----------|-----------|----------|",
        ]
    )
    for key in ("A", "B", "C", "D", "E", "F"):
        s = strategies.get(key) or {}
        lines.append(
            f"| {key} | {s.get('label')} | "
            f"{100*float(s.get('direct_fg_accuracy') or 0):.1f}% | "
            f"{100*float(s.get('egie_fg_hit_rate') or 0):.1f}% | "
            f"{100*float(s.get('egie_pending_rate') or 0):.1f}% | "
            f"{s.get('coverage_fixtures')} |"
        )

    lines.extend(["", "## STEP 4 — Bookmaker Ranking (First Team To Score)", ""])
    focus = books.get("focus_bookmakers") or []
    if focus:
        for row in focus[:10]:
            lines.append(
                f"- **{row.get('bookmaker')}** ({row.get('tier')}): "
                f"{100*float(row.get('fts_fg_hit_rate') or 0):.1f}% (n={row.get('sample_size')})"
            )
    absent = books.get("focus_bookmakers_absent") or []
    if absent:
        lines.append(f"- **Absent from FTS cache**: {', '.join(absent)} (MW odds present; FTS not offered or not cached)")
    for row in (books.get("fts_per_bookmaker") or [])[:8]:
        if row in focus:
            continue
        lines.append(
            f"- **{row.get('bookmaker')}** ({row.get('tier')}): "
            f"{100*float(row.get('fts_fg_hit_rate') or 0):.1f}% (n={row.get('sample_size')})"
        )

    lines.extend(["", "## STEP 5 — Signal Ranking", ""])
    for row in ranked[:10]:
        lines.append(
            f"- **Tier {row.get('tier')}** — {row.get('label')}: "
            f"{100*float(row.get('fg_hit_rate') or 0):.1f}%"
        )

    lines.extend(
        [
            "",
            "## Recommendation",
            "",
            "- Keep **sharp/consensus Match Winner implied** as primary EGIE odds enrichment (API-K finding confirmed).",
            "- Add **First Team To Score** as Tier A **direct FG sidecar** where available (similar accuracy, purpose-built market).",
            "- Do **not** replace MW with FTS in enrichment until FTS shows consistent outperformance across leagues/seasons.",
            "",
            "---",
            "",
            "**STOP — No deploy. No production changes.**",
        ]
    )

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return REPORT
