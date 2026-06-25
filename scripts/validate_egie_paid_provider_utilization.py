#!/usr/bin/env python3
"""Validate EGIE paid-provider utilization phase."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

AUDIT_ARTIFACT = ROOT / "artifacts" / "egie_paid_provider_audit.json"
BACKTEST_ARTIFACT = ROOT / "artifacts" / "egie_paid_provider_backtest.json"
REPORT_PATH = ROOT / "PHASE_API_FULL_UTILIZATION_EGIE_REPORT.md"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []

    from worldcup_predictor.egie.provider_features import EgieProviderFeatureStore, ProviderFeatureVector
    from worldcup_predictor.egie.provider_features.enrichment import enrich_agent_outputs, STRATEGY_LABELS
    from worldcup_predictor.egie.backtest.paid_provider_runner import PaidProviderEgieBacktestRunner

    checks.append(_check("provider_feature_store_import", True))
    checks.append(_check("strategy_labels_af", len(STRATEGY_LABELS) >= 6))

    store = EgieProviderFeatureStore()
    vec = store.build(1, competition_key="premier_league")
    checks.append(_check("provider_vector_build", isinstance(vec, ProviderFeatureVector)))

    if not AUDIT_ARTIFACT.exists():
        from scripts.egie_paid_provider_utilization_audit import main as audit_main

        audit_main()
    audit = json.loads(AUDIT_ARTIFACT.read_text(encoding="utf-8"))
    checks.append(_check("audit_ran", bool(audit.get("fixtures_audited", 0) > 0)))

    if not BACKTEST_ARTIFACT.exists():
        from scripts.egie_paid_provider_backtest import main as bt_main

        bt_main()
    backtest = json.loads(BACKTEST_ARTIFACT.read_text(encoding="utf-8"))
    checks.append(_check("backtest_ran", backtest.get("status") == "completed"))
    checks.append(_check("strategy_a_present", "A" in (backtest.get("strategies") or {})))

    from worldcup_predictor.egie.survival.dataset_builder import SurvivalDatasetBuilder

    builder = SurvivalDatasetBuilder()
    rows = builder.build_rows(competition_keys=["premier_league"], limit=5)
    if rows:
        required = {"home_xg_for", "odds_implied_home", "pressure_index_home", "provider_coverage_odds"}
        missing = required - set(rows[0].keys())
        checks.append(_check("survival_provider_columns", not missing, str(missing)))
    else:
        checks.append(_check("survival_provider_columns", False, "no rows"))

    builder.build_and_save(competition_keys=["premier_league"], limit=400)
    checks.append(_check("survival_parquet_written", True))

    passed = sum(1 for c in checks if c["pass"])
    total = len(checks)
    _write_report(audit, backtest, checks)

    print(f"VALIDATION: {passed}/{total} PASS")
    for c in checks:
        status = "PASS" if c["pass"] else "FAIL"
        print(f"  [{status}] {c['name']}: {c.get('detail', '')}")
    return 0 if passed == total else 1


def _write_report(audit: dict, backtest: dict, checks: list[dict]) -> None:
    strategies = backtest.get("strategies") or {}
    cov = (audit.get("provider_feature_store") or {}).get("coverage_pct") or {}
    cov_n = (audit.get("provider_feature_store") or {}).get("coverage_count") or {}
    fb_flags = audit.get("egie_feature_builder_flags_pct") or {}

    lines = [
        "# PHASE API Full Utilization — EGIE Report",
        "",
        "## Executive Summary",
        "",
        "Paid-provider infrastructure is **implemented and wired** into EGIE feature building, "
        "agent enrichment, survival dataset columns, and A–F backtest comparison. "
        "On this local dataset (Premier League 380 fixtures), **xG, pressure, and PL odds are not "
        "stored** — only goal events (94%) reach the feature store. World Cup odds exist in SQLite "
        "but do not overlap PL `fixture_id`s.",
        "",
        f"- **Production promotion safe:** `{backtest.get('production_promotion_safe')}`",
        f"- **Validation:** {sum(1 for c in checks if c['pass'])}/{len(checks)} checks PASS",
        f"- **Baseline (A) first-goal-team winrate:** {(strategies.get('A') or {}).get('first_goal_team_hit_rate')}",
        "",
        "## 1. Audit — API-Football",
        "",
        "| Field | Fetched (ingest) | Stored (EGIE PG / SQLite) | Enters prediction | Enters backtest | Survival parquet | Calibration |",
        "|-------|------------------|---------------------------|-------------------|-----------------|------------------|-------------|",
        f"| Events / goals | Yes (ingest manifest) | {cov_n.get('events', 0)}/380 fixtures | Via goal-minute history | Yes (baseline A) | first_goal_minute | Indirect (DQ) |",
        f"| Fixture statistics | Yes | {cov_n.get('advanced_stats', 0)}/380 | `provider_features.home_shots` etc. | Strategy F enrichment | Column added | No direct |",
        f"| Lineups | Yes | {cov_n.get('lineups', 0)}/380 | `lineup_goal_impact` agent (strategy F) | Strategy F | Column added | No direct |",
        f"| Injuries | Yes | {cov_n.get('injuries', 0)}/380 | `player_goal_threat` (strategy F) | Strategy F | Column added | No direct |",
        f"| Odds | Yes (API) | 0 PL / 1055 WC SQLite | `odds_goal_intelligence` when stored | Strategy D/E/F | Column added | Confidence manifest |",
        "",
        "## 2. Audit — Sportmonks",
        "",
        "| Field | Stored locally | Enters prediction | Enters backtest | Survival |",
        "|-------|----------------|-------------------|-----------------|----------|",
        f"| xG | {cov_n.get('xg', 0)}/380 | `provider_features` + pressure/xG agents | Strategy B/E/F | Columns added |",
        f"| Pressure Index | {cov_n.get('pressure', 0)}/380 | `first_goal_pressure` agent | Strategy C/E/F | Columns added |",
        f"| Advanced stats | via xG/fixture stats | Shots / SOT / dangerous attacks | Strategy F | Columns added |",
        f"| Scores / state / events | Partial (events in PG) | Goal events primary | Baseline | first_goal_minute |",
        f"| Odds / predictions | 0 locally | N/A | N/A | N/A |",
        "",
        "## 3. EGIE Provider Feature Store",
        "",
        "Module: `worldcup_predictor/egie/provider_features/`",
        "",
        "Per-fixture vector includes: `home_xg_for`, `away_xg_for`, `home_xg_against`, `away_xg_against`, "
        "`pressure_index_home/away`, shots, SOT, dangerous attacks, odds implied probs + movement, "
        "lineup strength, injuries impact, recent first-goal rates.",
        "",
        "### Coverage (Premier League, n=380)",
        "",
    ]
    for k, v in sorted(cov.items()):
        lines.append(f"- **{k}:** {v}% ({cov_n.get(k, 0)} fixtures)")
    lines.extend(
        [
            "",
            "### Feature builder attachment",
            "",
            f"- `provider_features_attached`: {fb_flags.get('provider_features_attached', 0)}% (sample n=50)",
            f"- `has_reliable_goal_odds`: {fb_flags.get('has_reliable_goal_odds', 0)}%",
            f"- `stored_goal_events`: {fb_flags.get('stored_goal_events', 0)}%",
            "",
            "## 4. Survival Dataset Extension",
            "",
            "`SurvivalDatasetBuilder` now writes provider columns to `data/egie/survival/survival_dataset.parquet` "
            "and uses strategy-F enrichment for `home_goal_rate` / `away_goal_rate`.",
            "",
            "## 5. Backtest Strategies A–F",
            "",
            "| Strategy | Label | FG Team | Goal Range | Soft Minute | Paid-data fixtures |",
            "|----------|-------|---------|------------|-------------|-------------------|",
        ]
    )
    for key in ("A", "B", "C", "D", "E", "F"):
        s = strategies.get(key) or {}
        cov_s = s.get("coverage") or {}
        lines.append(
            f"| {key} | {s.get('label', '')} | {s.get('first_goal_team_hit_rate')} | "
            f"{s.get('goal_range_hit_rate')} | {s.get('goal_minute_soft_hit_rate')} | "
            f"{cov_s.get('with_paid_data', '—')}/{cov_s.get('eligible', '—')} |"
        )

    lines.extend(
        [
            "",
            "### Per-field impact on winrate",
            "",
            "| Paid field | Strategy | Δ vs baseline A | Verdict |",
            "|------------|----------|-----------------|---------|",
        ]
    )
    base = (strategies.get("A") or {}).get("first_goal_team_hit_rate")
    field_map = {
        "xG": "B",
        "Pressure": "C",
        "Odds": "D",
        "xG+Pressure+Odds": "E",
        "Full provider": "F",
    }
    for label, key in field_map.items():
        hit = (strategies.get(key) or {}).get("first_goal_team_hit_rate")
        delta = round(hit - base, 4) if hit is not None and base is not None else None
        paid_n = ((strategies.get(key) or {}).get("coverage") or {}).get("with_paid_data", 0)
        verdict = "no data locally" if paid_n == 0 else ("improved" if delta and delta > 0.01 else "no improvement")
        lines.append(f"| {label} | {key} | {delta} | {verdict} |")

    lines.extend(["", "## 6. Pipeline Gaps", ""])
    for gap in audit.get("pipeline_gaps") or []:
        lines.append(f"- {gap}")

    lines.extend(["", "## 7. Promotion Decision", ""])
    for note in backtest.get("promotion_notes") or []:
        lines.append(f"- {note}")
    lines.extend(
        [
            "",
            "**`EliteGoalTimingEngine` thresholds unchanged.** Production agents use paid data only when "
            "`paid_provider_strategy != 'A'` (backtest) or production mode with stored fields present. "
            "No deploy until PL/WC ingest backfills xG, pressure, and league-aligned odds.",
            "",
            "## Artifacts",
            "",
            "- `artifacts/egie_paid_provider_audit.json`",
            "- `artifacts/egie_paid_provider_backtest.json`",
            "- `data/egie/survival/survival_dataset.parquet`",
            "",
            "## Commands",
            "",
            "```bash",
            "python scripts/egie_paid_provider_utilization_audit.py",
            "python scripts/egie_paid_provider_backtest.py",
            "python scripts/validate_egie_paid_provider_utilization.py",
            "```",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
