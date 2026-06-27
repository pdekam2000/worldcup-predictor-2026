#!/usr/bin/env python3
"""Phase 62B — Sportmonks WC xG + lineups completion."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT = ROOT / "data" / "validation" / "phase62b_sportmonks_wc_completion.json"
REPORT = ROOT / "PHASE_62B_SPORTMONKS_WC_XG_LINEUPS_COMPLETION_REPORT.md"


def _pct(v: float) -> str:
    return f"{100.0 * float(v):.1f}%"


def write_report(payload: dict) -> None:
    before = payload.get("coverage_before") or {}
    after = payload.get("coverage_after") or {}
    rec = payload.get("recommendation") or "NEED_MORE_IMPORTS"
    steps = payload.get("steps") or {}
    sm = steps.get("sportmonks_xg_lineups") or {}
    mapping = steps.get("mapping_audit") or {}
    features = steps.get("feature_rebuild") or {}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "# PHASE 62B — Sportmonks WC xG + Lineups Completion Report",
        "",
        f"**Generated:** {now}",
        f"**Recommendation:** `{rec}`",
        "",
        "## Scope",
        "",
        "- Data completion only — no model, UI, or public flag changes",
        "- Extended WC seasons: 1998–2026 finals tournaments",
        "",
        "## Fixture expansion",
        "",
        f"| Metric | Before | After |",
        f"|--------|--------|-------|",
        f"| Total WC fixtures | {payload.get('fixture_count_before', 0)} | {payload.get('fixture_count_after', 0)} |",
        f"| Usable finals (goal events) | {payload.get('usable_finals_before', 0)} | {payload.get('usable_finals_after', 0)} |",
        "",
        "## Coverage",
        "",
        f"| Signal | Before | After | Target |",
        f"|--------|--------|-------|--------|",
        f"| xG | {_pct(before.get('xg_coverage', 0))} | {_pct(after.get('xg_coverage', 0))} | 70% |",
        f"| Lineups | {_pct(before.get('lineup_coverage', 0))} | {_pct(after.get('lineup_coverage', 0))} | 80% |",
        f"| Goal events | {_pct(before.get('goal_event_coverage', 0))} | {_pct(after.get('goal_event_coverage', 0))} | 90% |",
        f"| Odds | {_pct(before.get('odds_coverage', 0))} | {_pct(after.get('odds_coverage', 0))} | 80% |",
        "",
        "## Mapping quality",
        "",
        f"- Mapped: **{mapping.get('mapped_fixtures', 0)}**",
        f"- Unmapped: **{mapping.get('unmapped_fixtures', 0)}**",
        f"- Mapping rate: **{_pct(mapping.get('mapping_rate', 0))}**",
        f"- Avg confidence: **{mapping.get('avg_confidence', 0)}**",
        f"- Blocked duplicates: **{mapping.get('blocked_mappings', 0)}**",
        "",
        "## Sportmonks import",
        "",
        f"- API calls: **{sm.get('api_calls', 0)}**",
        f"- Cache hits: **{sm.get('cache_hits', 0)}**",
        f"- Cache hit ratio: **{_pct(sm.get('cache_hit_ratio', 0))}**",
        f"- xG snapshots saved: **{sm.get('xg_saved', 0)}**",
        f"- Lineups saved: **{sm.get('lineup_saved', 0)}**",
        "",
        "## Feature rebuild",
        "",
        f"- Rows rebuilt: **{features.get('rebuilt', 0)}**",
        f"- With xG: **{features.get('with_xg', 0)}**",
        f"- With lineups: **{features.get('with_lineup', 0)}**",
        f"- With goal events: **{features.get('with_goal_events', 0)}**",
        "",
        "## Provider limitations",
        "",
    ]
    if payload.get("fixture_count_after", 0) < 500:
        lines.append(
            "- API-Football league 1 historical finals pool appears capped near ~330–400 fixtures across 1998–2026."
        )
    if sm.get("configured") is False:
        lines.append("- Sportmonks token not configured in this environment.")
    if sm.get("errors"):
        lines.append(f"- Sample errors: `{json.dumps(sm.get('errors')[:5])}`")

    lines.extend(
        [
            "",
            "## Success criteria",
            "",
            f"- 500+ usable fixtures: **{payload.get('usable_finals_after', 0) >= 500}**",
            f"- xG target (70%): **{after.get('meets_xg_target', False)}**",
            f"- Lineup target (80%): **{after.get('meets_lineup_target', False)}**",
            f"- Goal event target (90%): **{after.get('meets_goal_event_target', False)}**",
            "",
            f"## Recommendation: **`{rec}`**",
            "",
            "---",
            "*Phase 62B — data only. Phase 61B not rerun unless READY_FOR_PHASE_61B_RERUN.*",
        ]
    )
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 62B Sportmonks WC xG + lineups")
    parser.add_argument("--skip-fixture-import", action="store_true")
    parser.add_argument("--max-sm-calls", type=int, default=120)
    parser.add_argument("--no-resume", action="store_true", help="Ignore checkpoint and reprocess all")
    parser.add_argument("--progress-every", type=int, default=5)
    args = parser.parse_args()

    import logging
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
        force=True,
    )
    sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, "reconfigure") else None

    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.egie.world_cup.pipeline_62b import run_phase62b_pipeline
    from worldcup_predictor.egie.world_cup.progress_log import log_progress

    log_progress(f"[phase62b] starting max_sm_calls={args.max_sm_calls} resume={not args.no_resume}")
    payload = run_phase62b_pipeline(
        settings=get_settings(),
        skip_fixture_import=args.skip_fixture_import,
        max_sm_calls=args.max_sm_calls,
        resume=not args.no_resume,
        progress_every=max(1, args.progress_every),
    )
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    write_report(payload)
    print(json.dumps({"recommendation": payload.get("recommendation"), "report": str(REPORT)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
