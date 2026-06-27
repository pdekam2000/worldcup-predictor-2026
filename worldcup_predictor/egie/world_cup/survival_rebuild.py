"""Rebuild survival dataset and team profiles for World Cup — no model changes."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.egie.survival.team_survival_profiles import TeamSurvivalProfileStore
from worldcup_predictor.egie.world_cup.wc_survival_builder import build_wc_survival_rows
from worldcup_predictor.goal_timing.data.stored_adapter import StoredGoalTimingAdapter
from worldcup_predictor.egie.world_cup.config import (
    CONFEDERATION_PROFILES_OUTPUT,
    SURVIVAL_OUTPUT,
    TEAM_PROFILES_OUTPUT,
    WORLD_CUP_COMPETITION_KEY,
)

logger = logging.getLogger(__name__)

# Lightweight confederation hints for national teams (data labels only)
CONFEDERATION_HINTS = {
    "Brazil": "CONMEBOL",
    "Argentina": "CONMEBOL",
    "Germany": "UEFA",
    "France": "UEFA",
    "Spain": "UEFA",
    "England": "UEFA",
    "USA": "CONCACAF",
    "Mexico": "CONCACAF",
    "Japan": "AFC",
    "South Korea": "AFC",
    "Australia": "AFC",
    "Morocco": "CAF",
    "Senegal": "CAF",
}


def rebuild_survival_artifacts(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    keys = [WORLD_CUP_COMPETITION_KEY]
    stored = StoredGoalTimingAdapter(settings)
    rows = build_wc_survival_rows(competition_key=WORLD_CUP_COMPETITION_KEY, settings=settings)

    out_path = Path(SURVIVAL_OUTPUT)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        import pandas as pd

        pd.DataFrame(rows).to_parquet(out_path, index=False)
    else:
        out_path.write_text("[]", encoding="utf-8")

    before = datetime.now(timezone.utc).isoformat()
    profiles = TeamSurvivalProfileStore(stored=stored).build_profiles(
        before_kickoff=before,
        competition_keys=keys,
    )
    team_path = Path(TEAM_PROFILES_OUTPUT)
    team_path.parent.mkdir(parents=True, exist_ok=True)
    team_path.write_text(json.dumps(profiles, indent=2, default=str), encoding="utf-8")

    confed: dict[str, Any] = {}
    for team, prof in (profiles or {}).items() if isinstance(profiles, dict) else []:
        if not isinstance(prof, dict):
            continue
        c = CONFEDERATION_HINTS.get(team, "OTHER")
        confed.setdefault(c, {"teams": [], "sample_fixtures": 0})
        confed[c]["teams"].append(team)
        confed[c]["sample_fixtures"] += int((prof.get("scoring_timing_profile") or {}).get("samples") or 0)

    conf_path = Path(CONFEDERATION_PROFILES_OUTPUT)
    conf_path.write_text(json.dumps(confed, indent=2), encoding="utf-8")

    return {
        "survival_rows": len(rows),
        "survival_path": str(out_path),
        "team_profiles_path": str(team_path),
        "confederation_profiles_path": str(conf_path),
        "team_count": len(profiles) if isinstance(profiles, dict) else 0,
    }
