"""STEP 5 — UEFA survival dataset with Sportmonks provider features."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.egie.provider_features.enrichment import enrich_agent_outputs
from worldcup_predictor.egie.uefa_club.config import SURVIVAL_DATASET_PATH
from worldcup_predictor.egie.uefa_club.feature_extractors import build_provider_vector_fields, parse_match_result
from worldcup_predictor.egie.uefa_club.feature_store import UefaClubFeatureStore
from worldcup_predictor.egie.uefa_club.sportmonks_ingest import cache_path, load_cache
from worldcup_predictor.goal_timing.agents.orchestrator import GoalTimingAgentOrchestrator
from worldcup_predictor.goal_timing.data.stored_adapter import StoredGoalTimingAdapter
from worldcup_predictor.goal_timing.features.builder import GoalTimingFeatureBuilder
from worldcup_predictor.goal_timing.models_stat.baseline import GoalTimingBaselineModel

logger = logging.getLogger(__name__)


class UefaSurvivalDatasetBuilder:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.stored = StoredGoalTimingAdapter(self.settings)
        self.feature_builder = GoalTimingFeatureBuilder(stored=self.stored, max_api_event_fetches=0)
        self.provider_store = UefaClubFeatureStore(self.settings)
        self.agents = GoalTimingAgentOrchestrator()
        self.baseline = GoalTimingBaselineModel()

    def build_rows(self, fixtures: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for fx in sorted(fixtures, key=lambda x: str(x.get("kickoff_utc") or "")):
            sm_id = int(fx.get("sportmonks_fixture_id") or 0)
            comp = str(fx.get("competition_key") or "champions_league")
            home = str(fx.get("home_team") or "")
            away = str(fx.get("away_team") or "")
            kickoff = str(fx.get("kickoff_utc") or "")
            try:
                kickoff_dt = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
            except ValueError:
                kickoff_dt = datetime.now(timezone.utc)

            cache = load_cache(cache_path(self.settings, sm_id))
            payload = (cache or {}).get("payload")
            sm_fields = build_provider_vector_fields(payload)
            result = parse_match_result(payload, home_team=home, away_team=away)

            ctx = {"home_team": home, "away_team": away, "match_date": kickoff_dt}
            features = self.feature_builder.build(
                sm_id,
                competition_key=comp,
                as_of=kickoff_dt.replace(tzinfo=None),
                context=ctx,
            )
            pf = self.provider_store.build(sm_id, competition_key=comp, home_team=home, away_team=away)
            features["provider_features"] = pf.to_dict()
            features["paid_provider_strategy"] = "F"

            agent_outputs = self.agents.run(sm_id, features=features, context=ctx)
            agent_outputs = enrich_agent_outputs(agent_outputs, pf, "F")
            pred = self.baseline.predict(features, agent_outputs)

            row: dict[str, Any] = {
                "sportmonks_fixture_id": sm_id,
                "fixture_id": sm_id,
                "competition_key": comp,
                "home_team": home,
                "away_team": away,
                "kickoff_utc": kickoff,
                "first_goal_minute": result.get("first_goal_minute"),
                "home_goals": result.get("home_goals"),
                "away_goals": result.get("away_goals"),
                "baseline_first_goal_team": pred.get("first_goal_team"),
                "baseline_goal_range": pred.get("first_goal_time_range"),
                "data_quality_score": features.get("data_quality_score"),
            }
            row.update({k: v for k, v in sm_fields.items() if k != "coverage"})
            cov = sm_fields.get("coverage") or {}
            for k, v in cov.items():
                row[f"provider_coverage_{k}"] = bool(v)
            rows.append(row)
        return rows

    def build_and_save(
        self,
        fixtures: list[dict[str, Any]],
        *,
        output_path: str | Path | None = None,
    ) -> Path:
        rows = self.build_rows(fixtures)
        out = Path.cwd() / "data" / "egie" / "uefa_club" / "uefa_survival_dataset.parquet"
        if output_path:
            out = Path(output_path)
            if not out.is_absolute():
                out = Path.cwd() / out
        out.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_parquet(out, index=False)
        return out
