"""Phase API-J — classify remaining UEFA pending / unresolved fixtures."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.egie.uefa_club.feature_extractors import parse_match_result, parse_uefa_goal_events
from worldcup_predictor.egie.uefa_club.sportmonks_ingest import cache_path, load_cache


def audit_pending_fixtures(
    fixtures: list[dict[str, Any]],
    *,
    settings: Settings | None = None,
    backtest_path: Path | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    backtest_path = backtest_path or Path.cwd() / "artifacts" / "uefa_club_backtest_full.json"
    pending_ids: set[int] = set()
    if backtest_path.is_file():
        bt = json.loads(backtest_path.read_text(encoding="utf-8"))
        for row in (bt.get("per_strategy_results") or {}).get("A") or []:
            if str(row.get("first_goal_team_status") or "") == "pending" and row.get("fixture_id"):
                pending_ids.add(int(row["fixture_id"]))

    categories: Counter[str] = Counter()
    details: list[dict[str, Any]] = []
    reingest_candidates: list[int] = []

    for fx in fixtures:
        sm_id = int(fx.get("sportmonks_fixture_id") or 0)
        if sm_id <= 0:
            continue
        cache = load_cache(cache_path(settings, sm_id))
        payload = (cache or {}).get("payload")
        home = str(fx.get("home_team") or "")
        away = str(fx.get("away_team") or "")
        result = parse_match_result(payload, home_team=home, away_team=away)
        goals = parse_uefa_goal_events(payload)
        total = int(result.get("home_goals") or 0) + int(result.get("away_goals") or 0)
        side = result.get("first_goal_team_side")
        state_id = int(fx.get("state_id") or 0)

        if total == 0:
            reason = "no_goal_scored"
        elif not goals:
            reason = "missing_events"
            reingest_candidates.append(sm_id)
        elif side is None:
            reason = "participant_mapping_missing"
            reingest_candidates.append(sm_id)
        elif len(goals) < total:
            reason = "incomplete_events"
            reingest_candidates.append(sm_id)
        elif state_id not in (5, 7, 8):
            reason = "fixture_not_finished"
        elif sm_id in pending_ids:
            reason = "baseline_predicted_none"
        else:
            reason = "resolved"

        categories[reason] += 1
        if reason not in ("resolved", "baseline_predicted_none", "no_goal_scored"):
            details.append(
                {
                    "fixture_id": sm_id,
                    "competition_key": fx.get("competition_key"),
                    "home_team": home,
                    "away_team": away,
                    "home_goals": result.get("home_goals"),
                    "away_goals": result.get("away_goals"),
                    "goal_events": len(goals),
                    "first_goal_side": side,
                    "backtest_fg_pending": sm_id in pending_ids,
                    "reason": reason,
                }
            )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fixtures_audited": len(fixtures),
        "backtest_pending_fg_count": len(pending_ids),
        "summary": dict(categories),
        "reingest_candidates": sorted(set(reingest_candidates)),
        "reingest_candidate_count": len(set(reingest_candidates)),
        "fixture_details": details,
    }
