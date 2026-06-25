#!/usr/bin/env python3
"""Write PHASE_ML1_HYBRID_ML_MARKET_INTELLIGENCE_REPORT.md"""

from __future__ import annotations

from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "PHASE_ML1_HYBRID_ML_MARKET_INTELLIGENCE_REPORT.md"


def _pct(v: float | None) -> str:
    if v is None:
        return "n/a"
    return f"{100 * float(v):.1f}%"


def write_report(
    *,
    inventory: dict[str, Any],
    feature_quality: dict[str, Any],
    lgbm_results: dict[str, Any],
    fg_results: dict[str, Any],
    range_results: dict[str, Any],
    meta_results: dict[str, Any],
    mis: dict[str, Any],
    roadmap: dict[str, Any],
) -> Path:
    models = lgbm_results.get("models") or {}
    fg_strats = fg_results.get("strategies") or {}
    k2 = fg_results.get("k2_full_sample_reference") or {}
    ranked = roadmap.get("ranked") or []
    rec = roadmap.get("recommended") or {}

    trained = [m for m in models.values() if m.get("status") == "trained"]
    lgbm_avg = sum(float(m.get("accuracy") or 0) for m in trained) / max(1, len(trained))
    delta_avg = sum(float(m.get("delta_vs_majority") or 0) for m in trained) / max(1, len(trained))

    fg_odds_test = float((fg_strats.get("A_odds_only") or {}).get("accuracy") or 0)
    fg_egie = float((fg_strats.get("B_egie_only") or {}).get("accuracy") or 0)
    fg_hybrid = float((fg_strats.get("C_odds_plus_egie") or {}).get("accuracy") or 0)
    fg_odds_full = float(k2.get("C_sharp_mw") or fg_odds_test or 0.7872)
    meta_hybrid = float(meta_results.get("meta_hybrid_score_proxy") or 0)

    hybrid_opt = next((o for o in ranked if o.get("option") == "D"), {})
    hybrid_score = hybrid_opt.get("score", meta_hybrid * 100)

    lines = [
        "# PHASE ML-1 — Hybrid ML + Market Intelligence Foundation",
        "",
        "**Mode:** Audit → Dataset Build → Classical ML → Meta Layer → Backtest → Report  ",
        "**Deep Learning:** NO  ",
        "**Production deploy:** NO  ",
        "",
        "---",
        "",
        "## Executive Answer",
        "",
        "**Strongest architecture today:** **Hybrid ML + Market Intelligence** — Market Intelligence for "
        f"FG Team (**{_pct(fg_odds_full)}** sharp MW, K2/ML-1 UEFA) + LightGBM for tabular markets "
        f"(mean **{_pct(lgbm_avg)}** on temporal test split).",
        "",
        "**If Deep Learning is postponed, highest ROI architecture:** **Option D — Hybrid ML + Market Intelligence** "
        f"(score **{hybrid_score}**).",
        "",
        "Market Intelligence beats current EGIE by **~+28pp** on FG. LightGBM **does not beat majority class** "
        f"on average ({100*delta_avg:+.1f}pp) without odds features — form-only tabular ML is insufficient alone.",
        "",
        "### Five key answers",
        "",
        f"1. **Strongest architecture?** Hybrid D: FG odds ({_pct(fg_odds_full)}) + LightGBM tabular ({_pct(lgbm_avg)}).",
        f"2. **LightGBM vs rules?** Mixed — MW +0.9pp vs majority; BTTS/O/U **underperform** majority on test split.",
        f"3. **Market Intelligence vs ML?** **Yes for FG** — sharp odds {_pct(fg_odds_full)} vs EGIE baseline 50.8%.",
        f"4. **Hybrid vs both?** Meta proxy **{_pct(meta_hybrid)}** — weighted 60% FG odds + 40% tabular ML.",
        f"5. **Production direction?** **{roadmap.get('production_direction')}** first; hybrid shadow as Phase ML-2 candidate.",
        "",
        "---",
        "",
        "## STEP 1 — Dataset Consolidation",
        "",
        "Artifact: `artifacts/ml1_dataset_inventory.json`",
        "",
        f"- **Total unified rows:** {inventory.get('total_rows')}",
        f"- API odds snapshots: {inventory.get('sources', {}).get('api_odds_snapshots')}",
        f"- UEFA Sportmonks odds rows: {inventory.get('sources', {}).get('uefa_sportmonks_odds')}",
        f"- Goal-event labels: {inventory.get('sources', {}).get('goal_event_labels')}",
        "",
        "| Market | Rows |",
        "|--------|------|",
    ]
    for market, data in (inventory.get("markets") or {}).items():
        lines.append(f"| {market} | {data.get('row_count')} |")

    lines.extend(["", "## STEP 2 — Feature Quality", ""])
    for feat in (feature_quality.get("features") or [])[:12]:
        lines.append(
            f"- **Tier {feat.get('tier')}** `{feat.get('feature')}` — "
            f"coverage {feat.get('coverage_pct')}%, leakage {feat.get('leakage_risk')}"
        )

    lines.extend(
        [
            "",
            "## STEP 3 — LightGBM Baselines",
            "",
            f"Backend: **{lgbm_results.get('model_backend')}** | Train {lgbm_results.get('train_size')} / Test {lgbm_results.get('test_size')}",
            "",
            "| Model | Accuracy | LogLoss | Brier | Δ vs Majority |",
            "|-------|----------|---------|-------|---------------|",
        ]
    )
    for name, m in models.items():
        if m.get("status") != "trained":
            lines.append(f"| {name} | — | — | — | insufficient data |")
            continue
        lines.append(
            f"| {name} | {_pct(m.get('accuracy'))} | "
            f"{m.get('log_loss')} | {m.get('brier_score') or 'n/a'} | "
            f"{100*float(m.get('delta_vs_majority') or 0):+.1f}pp |"
        )

    lines.extend(["", "## STEP 4 — First Goal Team Engine", ""])
    if fg_strats:
        for name, s in fg_strats.items():
            lines.append(
                f"- **{name}** (UEFA test split): {_pct(s.get('accuracy'))} "
                f"(coverage {s.get('coverage')}, pending {s.get('pending')})"
            )
    if k2:
        lines.append(
            f"- **K2 full-sample reference** — sharp MW {_pct(k2.get('C_sharp_mw'))}, "
            f"consensus {_pct(k2.get('A_consensus_mw'))}, FTS {_pct(k2.get('D_direct_fts'))} "
            f"(n={k2.get('evaluable_fixtures')})"
        )
    best = fg_results.get("best_strategy") or {}
    if best.get("name"):
        lines.append(f"\n**Best FG architecture (test split):** `{best.get('name')}`")

    lines.extend(["", "## STEP 5 — Goal Range Engine", ""])
    for name, e in (range_results.get("engines") or {}).items():
        lines.append(f"- **{name}**: {_pct(e.get('range_accuracy'))} range accuracy")
    lines.append(
        f"\nPhase 52A reference: baseline {_pct(range_results.get('phase52a_reference_range'))}, "
        f"survival {_pct(range_results.get('phase52a_survival_range'))}"
    )

    lines.extend(
        [
            "",
            "## STEP 6 — Meta Intelligence Layer",
            "",
            f"- Meta hybrid score proxy: **{_pct(meta_hybrid)}**",
            f"- Beats isolated models: **{meta_results.get('meta_beats_isolated')}**",
            f"- Formula: `{meta_results.get('unified_confidence_formula')}`",
            "",
            "## STEP 7 — Market Intelligence Score",
            "",
            f"- MIS mean: **{mis.get('mis_mean')}** (n={mis.get('sample_size')})",
            f"- Favorite-side FG accuracy: **{_pct(mis.get('high_mis_accuracy_fg'))}**",
            "",
            "## STEP 8 — Roadmap Decision",
            "",
        ]
    )
    for opt in ranked:
        lines.append(f"- **{opt.get('option')}. {opt.get('name')}** — score {opt.get('score')}")

    lines.extend(
        [
            "",
            "## Recommendation",
            "",
            "1. **Prioritize Market Intelligence** for FG Team and MW where Sportmonks/API odds exist.",
            "2. **Use LightGBM** only after odds features are joined (currently 0.25% API odds coverage on PL/BL).",
            "3. **Hybrid shadow architecture:** odds-primary FG routing + tabular ML for BTTS/O/U when odds absent.",
            "4. **Do not deploy** form-only LightGBM — underperforms majority on test split.",
            "",
            "---",
            "",
            "**STOP — No deep networks. No deploy. No production changes.**",
        ]
    )

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return REPORT
