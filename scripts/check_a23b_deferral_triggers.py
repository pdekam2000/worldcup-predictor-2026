#!/usr/bin/env python3
"""Phase A23B — read-only deferral trigger check (no deploy, no writes)."""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))

ROOT = Path(__file__).resolve().parents[1]

EVALUATED_FIXTURES_MIN = 100
NATIONAL_TEAM_COVERAGE_MIN_PCT = 70.0


def main() -> int:
    from worldcup_predictor.database.repository import FootballIntelligenceRepository
    from worldcup_predictor.config.settings import get_settings

    repo = FootballIntelligenceRepository(get_settings().sqlite_path)
    conn = repo._conn

    evaluated = int(conn.execute("SELECT COUNT(1) FROM worldcup_prediction_evaluations").fetchone()[0])

    wc_rows = repo.goal_timing_league_coverage(["world_cup_2026"])
    wc = wc_rows[0] if wc_rows else {}
    finished = int(wc.get("finished_matches") or 0)
    with_events = int(wc.get("with_goal_events") or 0)
    with_fg = int(wc.get("with_first_goal_minute") or 0)
    event_pct = round(100.0 * with_events / finished, 1) if finished else 0.0
    fg_pct = round(100.0 * with_fg / finished, 1) if finished else 0.0

    # National-team timing proxy: goal-event coverage on WC fixtures
    nt_coverage_pct = event_pct

    predops = 0
    try:
        predops = int(conn.execute("SELECT COUNT(1) FROM predops_snapshots WHERE is_latest=1").fetchone()[0])
    except Exception:
        pass

    trigger_eval = evaluated >= EVALUATED_FIXTURES_MIN
    trigger_wc_dataset = finished >= 20 and with_events >= finished * 0.5 and with_fg >= 10
    trigger_nt_coverage = nt_coverage_pct > NATIONAL_TEAM_COVERAGE_MIN_PCT

    report = {
        "status": "DEFERRED",
        "a23b": "DEFERRED_READY",
        "triggers": {
            "evaluated_fixtures_gte_100": {
                "met": trigger_eval,
                "current": evaluated,
                "required": EVALUATED_FIXTURES_MIN,
            },
            "wc_historical_timing_dataset": {
                "met": trigger_wc_dataset,
                "finished_matches": finished,
                "with_goal_events": with_events,
                "with_first_goal_minute": with_fg,
                "note": "met when >=20 finished WC matches, >=50% with goal events, >=10 with FG minute",
            },
            "national_team_egie_coverage_gt_70pct": {
                "met": trigger_nt_coverage,
                "current_pct": nt_coverage_pct,
                "required_pct": NATIONAL_TEAM_COVERAGE_MIN_PCT,
                "proxy": "world_cup_2026 goal_event_coverage_pct",
            },
        },
        "context": {
            "predops_latest_snapshots": predops,
            "priority_note": "Model Center, certification, results, archive, evaluation, stability first",
        },
        "reopen_eligible": trigger_eval or trigger_wc_dataset or trigger_nt_coverage,
    }

    if report["reopen_eligible"]:
        report["status"] = "REOPEN_ELIGIBLE"

    out = ROOT / "artifacts" / "phase_a23b_deferral_triggers.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Phase A23B deferral check: {report['status']}")
    print(f"  evaluated fixtures: {evaluated}/{EVALUATED_FIXTURES_MIN} {'MET' if trigger_eval else 'not met'}")
    print(
        f"  WC timing dataset: finished={finished} events={with_events} fg_min={with_fg} "
        f"{'MET' if trigger_wc_dataset else 'not met'}"
    )
    print(
        f"  NT coverage proxy: {nt_coverage_pct}% (need >{NATIONAL_TEAM_COVERAGE_MIN_PCT}%) "
        f"{'MET' if trigger_nt_coverage else 'not met'}"
    )
    print(f"  predops latest snapshots: {predops}")
    print(f"  artifact: {out}")

    return 0 if report["reopen_eligible"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
