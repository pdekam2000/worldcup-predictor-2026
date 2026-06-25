"""Phase 58C — Elite Orchestrator shadow runtime configuration."""

from __future__ import annotations

from pathlib import Path

MODEL_VERSION = "elite_orchestrator_shadow_v1.0.58c"
PHASE = "58C"

PREDICTIONS_PATH = Path("data/shadow/elite_orchestrator_predictions.jsonl")
EVALUATIONS_PATH = Path("data/shadow/elite_orchestrator_evaluations.jsonl")
ARTIFACT_DIR = Path("artifacts/phase58c_elite_shadow_runtime")

# Sportmonks league_id → competition label
LEAGUE_MAP: dict[int, str] = {
    2: "champions_league",
    5: "europa_league",
    848: "conference_league",
    732: "world_cup",
    8: "premier_league",
    82: "bundesliga",
}

DEFAULT_COMPETITIONS: tuple[str, ...] = ("world_cup_2026",)
UEFA_LEAGUE_IDS: tuple[int, ...] = (2, 5, 848)

MARKETS: tuple[str, ...] = (
    "1x2",
    "first_goal_team",
    "team_to_score_first",
    "anytime_goalscorer",
    "first_goalscorer",
    "goal_timing",
)
