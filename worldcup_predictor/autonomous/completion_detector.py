"""Detect completed fixtures ready for evaluation — Phase 61."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from worldcup_predictor.autonomous.fixture_discovery import list_completed_fixtures
from worldcup_predictor.autonomous.store import AutonomousStore
from worldcup_predictor.config.settings import Settings, get_settings

FINISHED_STATUSES = frozenset({"FT", "AET", "PEN", "FINISHED"})


@dataclass
class CompletionDetectionResult:
    scanned: int = 0
    completed: int = 0
    already_evaluated: int = 0
    ready_for_evaluation: list[dict[str, Any]] = field(default_factory=list)
    missing_score: int = 0
    api_calls_used: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "completed": self.completed,
            "already_evaluated": self.already_evaluated,
            "ready_count": len(self.ready_for_evaluation),
            "missing_score": self.missing_score,
            "api_calls_used": self.api_calls_used,
            "ready_for_evaluation": self.ready_for_evaluation[:50],
        }


def detect_completed_fixtures(
    *,
    settings: Settings | None = None,
    limit: int = 100,
) -> CompletionDetectionResult:
    settings = settings or get_settings()
    store = AutonomousStore(settings)
    result = CompletionDetectionResult()

    finished = list_completed_fixtures(settings=settings, limit=limit)
    result.scanned = len(finished)

    for row in finished:
        status = str(row.get("status") or "").upper()
        if status not in FINISHED_STATUSES:
            continue
        result.completed += 1
        fid = int(row["fixture_id"])
        home_goals = row.get("home_goals")
        away_goals = row.get("away_goals")
        if home_goals is None or away_goals is None:
            result.missing_score += 1
            continue

        snapshots = store.list_snapshots(fixture_id=fid, limit=500)
        unevaluated = [s for s in snapshots if not store.get_evaluation_for_snapshot(int(s["id"]))]
        if not unevaluated:
            result.already_evaluated += 1
            continue

        result.ready_for_evaluation.append(
            {
                "fixture_id": fid,
                "competition_key": row.get("competition_key"),
                "home_team": row.get("home_team"),
                "away_team": row.get("away_team"),
                "final_score": f"{home_goals}-{away_goals}",
                "status": status,
                "snapshots_pending": len(unevaluated),
                "first_goal_team": row.get("first_goal_team"),
                "first_goal_minute": row.get("first_goal_minute"),
            }
        )

    return result
