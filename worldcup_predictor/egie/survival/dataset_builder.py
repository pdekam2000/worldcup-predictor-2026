"""Build survival-ready dataset from stored fixture intelligence."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.egie.survival.config import SURVIVAL_DATASET_PATH
from worldcup_predictor.egie.provider_features.enrichment import enrich_agent_outputs
from worldcup_predictor.egie.provider_features.store import EgieProviderFeatureStore
from worldcup_predictor.goal_timing.agents.orchestrator import GoalTimingAgentOrchestrator
from worldcup_predictor.goal_timing.data.stored_adapter import StoredGoalTimingAdapter
from worldcup_predictor.goal_timing.features.builder import GoalTimingFeatureBuilder
from worldcup_predictor.goal_timing.leagues import GOAL_TIMING_ALLOWED_LEAGUE_KEYS
from worldcup_predictor.goal_timing.models_stat.baseline import GoalTimingBaselineModel

logger = logging.getLogger(__name__)


def _season_from_kickoff(kickoff: str | None) -> str:
    if not kickoff:
        return "unknown"
    try:
        dt = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
    except ValueError:
        return "unknown"
    y = dt.year
    return f"{y}/{y + 1}" if dt.month >= 8 else f"{y - 1}/{y}"


def _is_scoreless(home_goals: Any, away_goals: Any) -> bool:
    try:
        return int(home_goals or 0) == 0 and int(away_goals or 0) == 0
    except (TypeError, ValueError):
        return False


def _compute_rates(features: dict[str, Any], agent_outputs: dict[str, Any]) -> tuple[float, float]:
    home_fg = (features.get("first_goal_team_distribution") or {}).get("home") or {}
    away_fg = (features.get("first_goal_team_distribution") or {}).get("away") or {}
    home_rate = float(home_fg.get("scored_first") or 0.33)
    away_rate = float(away_fg.get("scored_first") or 0.33)
    pressure = agent_outputs.get("first_goal_pressure")
    if pressure and pressure.signals.get("pressure_edge") == "home":
        home_rate += 0.05
    elif pressure and pressure.signals.get("pressure_edge") == "away":
        away_rate += 0.05
    threat = agent_outputs.get("player_goal_threat")
    if threat:
        share = float(threat.signals.get("home_scoring_share") or 0.5)
        home_rate += (share - 0.5) * 0.15
        away_rate += (0.5 - share) * 0.15
    tactical = agent_outputs.get("tactical_goal_flow")
    if tactical:
        flow = float(tactical.signals.get("combined_flow_edge") or 0.0)
        if flow > 0:
            home_rate += 0.04
        elif flow < 0:
            away_rate += 0.04
    return round(home_rate, 6), round(away_rate, 6)


class SurvivalDatasetBuilder:
    """Generate survival_dataset.parquet from SQLite fixture history."""

    def __init__(self, *, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.stored = StoredGoalTimingAdapter(self.settings)
        self.feature_builder = GoalTimingFeatureBuilder(stored=self.stored, max_api_event_fetches=0)
        self.agents = GoalTimingAgentOrchestrator()
        self.baseline = GoalTimingBaselineModel()
        self.provider_store = EgieProviderFeatureStore(self.settings)

    def build_rows(
        self,
        *,
        competition_keys: list[str] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        keys = competition_keys or list(GOAL_TIMING_ALLOWED_LEAGUE_KEYS)
        before = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        fixtures = self.stored.repo.list_finished_fixtures_before(
            before_kickoff=before,
            competition_keys=keys,
            limit=limit,
        )
        rows: list[dict[str, Any]] = []
        for fx in reversed(fixtures):
            fixture_id = int(fx["fixture_id"])
            home_team = str(fx.get("home_team") or "")
            away_team = str(fx.get("away_team") or "")
            kickoff = str(fx.get("kickoff_utc") or "")
            comp = str(fx.get("competition_key") or keys[0])
            first_minute = fx.get("first_goal_minute")
            try:
                first_minute = int(first_minute) if first_minute is not None else None
            except (TypeError, ValueError):
                first_minute = None

            scoreless = _is_scoreless(fx.get("home_goals"), fx.get("away_goals"))
            censored = scoreless or first_minute is None

            kickoff_dt = self.stored.parse_kickoff(kickoff)
            ctx = {"home_team": home_team, "away_team": away_team, "match_date": kickoff_dt}
            features = self.feature_builder.build(
                fixture_id, competition_key=comp, as_of=kickoff_dt, context=ctx
            )
            pf_vec = self.provider_store.build(
                fixture_id,
                competition_key=comp,
                home_team=home_team,
                away_team=away_team,
            )
            agent_outputs = self.agents.run(fixture_id, features=features, context=ctx)
            enriched_outputs = enrich_agent_outputs(agent_outputs, pf_vec, "F")
            home_rate, away_rate = _compute_rates(features, enriched_outputs)
            raw = self.baseline.predict(features, enriched_outputs)
            hs = features.get("history_samples") or {}
            pf = pf_vec.to_dict()

            rows.append(
                {
                    "fixture_id": fixture_id,
                    "league": comp,
                    "season": _season_from_kickoff(kickoff),
                    "home_team": home_team,
                    "away_team": away_team,
                    "kickoff_utc": kickoff,
                    "first_goal_minute": first_minute,
                    "censored_match": censored,
                    "home_goal_rate": home_rate,
                    "away_goal_rate": away_rate,
                    "dq": float(features.get("data_quality_score") or 0.0),
                    "confidence": float(raw.get("raw_confidence") or 0.0),
                    "home_history_samples": int(hs.get("home_matches") or 0),
                    "away_history_samples": int(hs.get("away_matches") or 0),
                    "home_xg_for": pf.get("home_xg_for"),
                    "away_xg_for": pf.get("away_xg_for"),
                    "home_xg_against": pf.get("home_xg_against"),
                    "away_xg_against": pf.get("away_xg_against"),
                    "pressure_index_home": pf.get("pressure_index_home"),
                    "pressure_index_away": pf.get("pressure_index_away"),
                    "home_shots": pf.get("home_shots"),
                    "away_shots": pf.get("away_shots"),
                    "home_shots_on_target": pf.get("home_shots_on_target"),
                    "away_shots_on_target": pf.get("away_shots_on_target"),
                    "odds_implied_home": pf.get("odds_implied_home"),
                    "odds_implied_away": pf.get("odds_implied_away"),
                    "odds_movement_home": pf.get("odds_movement_home"),
                    "lineup_strength_home": pf.get("lineup_strength_home"),
                    "lineup_strength_away": pf.get("lineup_strength_away"),
                    "injuries_impact_home": pf.get("injuries_impact_home"),
                    "injuries_impact_away": pf.get("injuries_impact_away"),
                    "provider_coverage_xg": bool((pf.get("coverage") or {}).get("xg")),
                    "provider_coverage_odds": bool((pf.get("coverage") or {}).get("odds")),
                    "provider_coverage_pressure": bool((pf.get("coverage") or {}).get("pressure")),
                    "provider_coverage_lineups": bool((pf.get("coverage") or {}).get("lineups")),
                    "match_state_features": json.dumps(
                        {
                            "home_with_goal_minutes": hs.get("home_with_goal_minutes"),
                            "away_with_goal_minutes": hs.get("away_with_goal_minutes"),
                            "league_matches": hs.get("league_matches"),
                        }
                    ),
                }
            )
        return rows

    def build_and_save(
        self,
        *,
        output_path: Path | None = None,
        competition_keys: list[str] | None = None,
        limit: int | None = None,
    ) -> Path:
        output_path = output_path or SURVIVAL_DATASET_PATH
        output_path.parent.mkdir(parents=True, exist_ok=True)
        rows = self.build_rows(competition_keys=competition_keys, limit=limit)
        df = pd.DataFrame(rows)
        try:
            df.to_parquet(output_path, index=False)
        except Exception as exc:
            logger.warning("parquet write failed (%s); falling back to JSON", exc)
            fallback = output_path.with_suffix(".json")
            fallback.write_text(json.dumps(rows, indent=2), encoding="utf-8")
            return fallback
        return output_path
