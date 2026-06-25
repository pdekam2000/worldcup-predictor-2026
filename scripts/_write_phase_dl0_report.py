#!/usr/bin/env python3
"""Write PHASE_DL0_DATASET_READINESS_AUDIT_REPORT.md"""

from __future__ import annotations

from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "PHASE_DL0_DATASET_READINESS_AUDIT_REPORT.md"


def write_report(
    *,
    inventory: dict[str, Any],
    market_readiness: dict[str, Any],
    feature_coverage: dict[str, Any],
    suitability: dict[str, Any],
    architecture: dict[str, Any],
    thresholds: dict[str, Any],
    roadmap: dict[str, Any],
) -> Path:
    ds = inventory.get("datasets") or {}
    markets = market_readiness.get("markets") or {}
    features = feature_coverage.get("features") or {}
    ranked = suitability.get("ranked") or []
    checks = thresholds.get("checks") or {}
    options = roadmap.get("ranked_options") or []
    first = roadmap.get("recommended_first") or {}
    second = roadmap.get("recommended_second") or {}

    surv = ds.get("egie_survival", {})
    odds = ds.get("odds", {})
    xg = ds.get("xg", {})

    lines = [
        "# PHASE DL-0 — Deep Learning Dataset Readiness Audit",
        "",
        "**Mode:** Audit → Feasibility → Architecture → Report  ",
        "**Training:** NO  ",
        "**Production deploy:** NO  ",
        "",
        "---",
        "",
        "## Executive Answer",
        "",
        "**Is Deep Learning justified today?**",
        "",
        "**No.** Current datasets are too small, too sparse on xG/pressure/injuries, and recent audits show **parser fixes + sharp odds intelligence** deliver larger gains than ML. Classical survival (+3.2pp goal range) has not yet justified deep survival.",
        "",
        "**If only ONE system could be built next, what generates the largest improvement?**",
        "",
        f"**Option {second.get('option')} — {second.get('name')}** (score {second.get('score')}/100). "
        "Extend **Hybrid ML + Market Intelligence** (odds-primary routing, sharp MW enrichment) — measured **+28–29pp FG Team** on UEFA (API-K) vs baseline, vs survival shadow **−1.5pp FG** (Phase 52A).",
        "",
        "Do **not** build FT-Transformer or Deep Survival yet: survival parquet has **380 rows** (need 10,000+) and **0% first_goal_minute labels** populated.",
        "",
        "### Six key decisions",
        "",
        "1. **DL justified?** No — data pipeline first.",
        "2. **First DL market?** None yet; if forced: **Goal Range** via classical survival before deep survival.",
        "3. **Highest ROI architecture?** **Market Intelligence + LightGBM hybrid**, not neural.",
        "4. **Stay rule-based?** **Goal Minute** (3.4% exact), **Goalscorer** (no labels).",
        "5. **Stay odds-driven?** **First Goal Team**, **Match Winner** (sharp MW 78.7% FG).",
        "6. **Become neural?** **Nothing today** — thresholds fail on all neural options.",
        "",
        "---",
        "",
        "## STEP 1 — Dataset Inventory",
        "",
        "Artifact: `artifacts/dl_dataset_inventory.json`",
        "",
        "| Dataset | Rows | Features | Key gap |",
        "|---------|------|----------|---------|",
    ]

    summary_rows = [
        ("EGIE Survival", surv.get("row_count"), surv.get("feature_count"), "FG minute 100% null in parquet"),
        ("Goal Events", ds.get("goal_events", {}).get("row_count"), 8, "OK for events"),
        ("API-Football Historical", ds.get("api_football_historical", {}).get("row_count"), 12, "Odds enrichment 4.3%"),
        ("UEFA Club", ds.get("uefa_club", {}).get("row_count"), ds.get("uefa_club", {}).get("feature_count"), "xG 96.4% missing"),
        ("Odds", ds.get("odds", {}).get("row_count"), 15, "Strong in UEFA cache only"),
        ("Lineups", ds.get("lineups", {}).get("row_count"), 6, "EGIE provider 3.16%"),
        ("Injuries", 0, 4, "0% coverage"),
        ("Match Statistics", ds.get("match_statistics", {}).get("row_count"), 20, "91% enrichment coverage"),
        ("xG", ds.get("xg", {}).get("row_count"), 8, "Critical bottleneck"),
        ("Pressure", 0, 4, "0% in store"),
        ("Prediction History", ds.get("prediction_history", {}).get("row_count"), ds.get("prediction_history", {}).get("feature_count"), "Mostly live WC"),
        ("Accuracy Tracker", ds.get("accuracy_tracker", {}).get("row_count"), "—", "70 verified markets"),
    ]
    for name, rows, feats, gap in summary_rows:
        lines.append(f"| {name} | {rows} | {feats} | {gap} |")

    lines.extend(["", "## STEP 2 — Market Readiness", ""])
    for key, m in markets.items():
        lines.append(
            f"- **{key}**: **{m.get('readiness')}** — "
            f"samples={m.get('available_samples')}; {m.get('readiness_reason', '')}"
        )

    lines.extend(["", "## STEP 3 — Feature Coverage", ""])
    for fname, fdata in features.items():
        lines.append(
            f"- **{fname}**: coverage {fdata.get('coverage_pct')}%, "
            f"usable {fdata.get('usable_pct')}%"
            + (f" — {fdata.get('notes')}" if fdata.get("notes") else "")
        )

    lines.extend(["", "## STEP 4 — DL Suitability Ranking", ""])
    for row in ranked:
        lines.append(f"- **Tier {row.get('tier')}** — {row.get('market')}: {row.get('rationale')}")

    lines.extend(["", "## STEP 5 — Architecture Matching", ""])
    for market, match in (architecture.get("matches") or {}).items():
        rec = ", ".join(match.get("recommended") or [])
        lines.append(f"- **{market}**: {rec}")

    lines.extend(["", "## STEP 6 — Data Threshold Check", ""])
    for name, check in checks.items():
        status = "PASS" if check.get("passes") else "FAIL"
        lines.append(f"- **{name}**: {status}")

    lines.extend(["", "## STEP 7 — Roadmap Decision (ranked)", ""])
    for opt in options:
        lines.append(f"- **{opt.get('option')}. {opt.get('name')}** (score {opt.get('score')}): {opt.get('rationale')}")

    lines.extend(
        [
            "",
            "## Recommendation",
            "",
            f"**Primary:** Option **{first.get('option')}** — {first.get('name')}.",
            f"**Secondary:** Option **{second.get('option')}** — {second.get('name')}.",
            "",
            "Before any neural work:",
            "- Populate `first_goal_minute` in survival parquet from `fixture_goal_events`",
            "- Expand xG and odds coverage beyond UEFA/Bundesliga silos",
            "- Ingest injuries + player history for goalscorer markets",
            "",
            "---",
            "",
            "**STOP — No training. No deploy. No production changes.**",
        ]
    )

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return REPORT
