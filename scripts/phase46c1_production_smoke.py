#!/usr/bin/env python3
"""Phase 46C-1 production smoke — outcome persistence coverage on live DB."""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def main() -> int:
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.database.migrations import ensure_schema_compat
    from worldcup_predictor.database.repository import FootballIntelligenceRepository

    settings = get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    ensure_schema_compat(repo._conn)

    rows = repo.list_worldcup_stored_prediction_rows()
    with_ht = 0
    with_events = 0
    with_first_goal = 0
    persisted = 0
    finished = 0

    for row in rows:
        fid = int(row["fixture_id"])
        result = repo.get_fixture_result_row(fid)
        if not result:
            continue
        fixture = repo.get_fixture_row(fid) or {}
        if str(fixture.get("status") or "").upper() in {"FT", "AET", "PEN"}:
            finished += 1
        if result.get("ht_home_goals") is not None:
            with_ht += 1
        if result.get("outcome_persisted_at"):
            persisted += 1
        if repo.count_fixture_goal_events(fid) > 0:
            with_events += 1
        if result.get("first_goal_minute") is not None or (
            int(result.get("total_goals") or 0) == 0 and result.get("outcome_persisted_at")
        ):
            with_first_goal += 1

    stats = {
        "archive_rows": len(rows),
        "finished_with_results": finished,
        "with_ht_scores": with_ht,
        "with_goal_events": with_events,
        "with_first_goal_or_0_0": with_first_goal,
        "outcome_persisted_at_set": persisted,
    }
    out = Path("artifacts/phase46c1_production_smoke.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(stats, indent=2), encoding="utf-8")

    print("Phase 46C-1 production smoke")
    for key, value in stats.items():
        print(f"  {key}: {value}")

    ok = stats["outcome_persisted_at_set"] >= 0
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
