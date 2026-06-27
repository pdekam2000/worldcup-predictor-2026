#!/usr/bin/env python3
"""Phase 62 — World Cup EGIE data expansion (ingest + feature store + survival rebuild)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT = ROOT / "data" / "validation" / "phase62_world_cup_egie_expansion.json"
REPORT = ROOT / "PHASE_62_WORLD_CUP_EGIE_DATA_EXPANSION_REPORT.md"


def _pct_label(value: float) -> str:
    return f"{100.0 * float(value):.1f}%"


def write_report(payload: dict) -> None:
    cov = payload.get("coverage") or {}
    rec = payload.get("recommendation") or "NEED_MORE_IMPORTS"
    steps = payload.get("steps") or {}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "# PHASE 62 — World Cup EGIE Data Expansion Report",
        "",
        f"**Generated:** {now}",
        f"**Recommendation:** `{rec}`",
        "",
        "## Scope",
        "",
        "- Data expansion only — no model, UI, or public flag changes",
        "- Target competitions: FIFA World Cup 2010, 2014, 2018, 2022, 2026",
        "",
        "## Pipeline steps",
        "",
    ]
    for name, step in steps.items():
        lines.append(f"### {name}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(step, indent=2, default=str)[:4000])
        lines.append("```")
        lines.append("")

    lines.extend(
        [
            "## Coverage summary",
            "",
            f"| Metric | Value | Target |",
            f"|--------|-------|--------|",
            f"| Total WC fixtures | {cov.get('total_fixtures', 0)} | {cov.get('targets', {}).get('fixtures', 500)}+ |",
            f"| Finished fixtures | {cov.get('finished_fixtures', 0)} | — |",
            f"| Goal event coverage | {_pct_label(cov.get('goal_event_coverage', 0))} | {_pct_label(cov.get('targets', {}).get('goal_events', 0.9))} |",
            f"| xG coverage | {_pct_label(cov.get('xg_coverage', 0))} | {_pct_label(cov.get('targets', {}).get('xg', 0.7))} |",
            f"| Lineup coverage | {_pct_label(cov.get('lineup_coverage', 0))} | {_pct_label(cov.get('targets', {}).get('lineups', 0.8))} |",
            f"| Odds coverage | {_pct_label(cov.get('odds_coverage', 0))} | {_pct_label(cov.get('targets', {}).get('odds', 0.8))} |",
            f"| Pressure coverage | {_pct_label(cov.get('pressure_coverage', 0))} | — |",
            f"| Usable EGIE fixtures | {cov.get('usable_egie_fixtures', 0)} | 500+ |",
            "",
            "## PostgreSQL EGIE rows",
            "",
            f"```json",
            json.dumps(cov.get("postgresql") or {}, indent=2),
            "```",
            "",
            "## Success criteria",
            "",
            f"- Fixtures target met: **{cov.get('meets_fixture_target', False)}**",
            f"- xG target met: **{cov.get('meets_xg_target', False)}**",
            f"- Lineup target met: **{cov.get('meets_lineup_target', False)}**",
            f"- Odds target met: **{cov.get('meets_odds_target', False)}**",
            f"- Goal event target met: **{cov.get('meets_goal_event_target', False)}**",
            f"- All targets met: **{cov.get('all_targets_met', False)}**",
            "",
            "## Recommendation",
            "",
            f"**`{rec}`**",
            "",
        ]
    )
    if rec == "READY_FOR_PHASE_61B_RERUN":
        lines.append("Phase 61B production validation may be rerun with `scripts/validate_phase61b_production_egie_unified.py`.")
    elif rec == "PROVIDER_LIMITED":
        lines.append("Provider returned insufficient World Cup history — check API plan limits and Sportmonks league 732 access.")
    else:
        lines.append("Continue bulk imports (API-Football historical + Sportmonks xG/pressure) before Phase 61B rerun.")

    lines.append("")
    lines.append("---")
    lines.append("*Phase 62 — data only. No model or public rollout changes.*")
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 62 World Cup EGIE data expansion")
    parser.add_argument("--skip-api-import", action="store_true", help="Skip API-Football historical import")
    parser.add_argument("--coverage-only", action="store_true", help="Measure coverage and write report only")
    parser.add_argument("--max-af-calls", type=int, default=120)
    parser.add_argument("--max-sm-calls", type=int, default=60)
    parser.add_argument("--max-goal-backfill", type=int, default=80)
    parser.add_argument("--max-xg-calls", type=int, default=80)
    args = parser.parse_args()

    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.egie.world_cup.coverage import measure_coverage, recommend_phase
    from worldcup_predictor.egie.world_cup.pipeline import run_phase62_pipeline

    settings = get_settings()

    if args.coverage_only:
        payload = {
            "mode": "coverage_only",
            "coverage": measure_coverage(settings=settings),
        }
        payload["recommendation"] = recommend_phase(payload["coverage"])
    else:
        payload = run_phase62_pipeline(
            settings=settings,
            skip_api_import=args.skip_api_import,
            max_af_calls=args.max_af_calls,
            max_sm_calls=args.max_sm_calls,
            max_goal_backfill_calls=args.max_goal_backfill,
            max_xg_calls=args.max_xg_calls,
        )

    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    write_report(payload)
    print(json.dumps({"recommendation": payload.get("recommendation"), "artifact": str(ARTIFACT), "report": str(REPORT)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
