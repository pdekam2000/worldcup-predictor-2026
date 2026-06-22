"""Goal timing prediction service — build, predict, persist (Phase 51D)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.goal_timing.config import GOAL_TIMING_PREDICTION_LEAGUE_KEYS
from worldcup_predictor.goal_timing.data.fixture_ids import is_valid_fixture_id
from worldcup_predictor.goal_timing.data.stored_adapter import StoredGoalTimingAdapter
from worldcup_predictor.goal_timing.engine import EliteGoalTimingEngine
from worldcup_predictor.goal_timing.features.builder import GoalTimingFeatureBuilder
from worldcup_predictor.goal_timing.leagues import is_goal_timing_prediction_league
from worldcup_predictor.goal_timing.storage.repository import GoalTimingRepository


class GoalTimingPredictionService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.stored = StoredGoalTimingAdapter(self.settings)
        self.repository = GoalTimingRepository(self.settings)
        self.engine = EliteGoalTimingEngine(
            feature_builder=GoalTimingFeatureBuilder(
                stored=self.stored,
                max_api_event_fetches=0,
            )
        )

    def predict_fixture(
        self,
        fixture_id: int,
        *,
        persist: bool = True,
        competition_key: str | None = None,
    ) -> dict[str, Any]:
        if not is_valid_fixture_id(fixture_id):
            return {
                "fixture_id": fixture_id,
                "error": "invalid_fixture_id",
                "persisted": False,
            }

        target = self.stored.get_target_fixture(int(fixture_id))
        comp_key = str(competition_key or (target or {}).get("competition_key") or "")

        if not is_goal_timing_prediction_league(comp_key):
            return {
                "fixture_id": fixture_id,
                "competition_key": comp_key,
                "error": "league_not_enabled_for_predictions",
                "enabled_leagues": list(GOAL_TIMING_PREDICTION_LEAGUE_KEYS),
                "persisted": False,
            }

        kickoff = (target or {}).get("kickoff_utc")
        match_date = self.stored.parse_kickoff(kickoff) if kickoff else None
        context = {
            "home_team": (target or {}).get("home_team"),
            "away_team": (target or {}).get("away_team"),
            "match_date": match_date,
        }

        features = self.engine.feature_builder.build(
            int(fixture_id),
            competition_key=comp_key,
            context=context,
        )
        feature_snapshot_id = None
        if persist:
            feature_snapshot_id = self.repository.save_feature_snapshot(
                fixture_id=int(fixture_id),
                as_of=features.get("as_of") or datetime.now(timezone.utc).isoformat(),
                features=features,
                source_manifest=features.get("provider_manifest") or {},
                competition_key=comp_key,
            )

        result = self.engine.predict_from_features(
            int(fixture_id),
            features=features,
            competition_key=comp_key,
            context=context,
        )

        prediction_id = None
        if persist:
            prediction_id = self.repository.save_prediction(
                result,
                feature_snapshot_id=feature_snapshot_id,
            )

        return {
            "fixture_id": fixture_id,
            "competition_key": comp_key,
            "prediction_id": str(prediction_id) if prediction_id else None,
            "feature_snapshot_id": feature_snapshot_id,
            "persisted": bool(prediction_id),
            "prediction": result.to_dict(),
        }

    def list_today_picks(self, *, limit: int = 20) -> dict[str, Any]:
        picks: list[dict[str, Any]] = []
        for comp_key in GOAL_TIMING_PREDICTION_LEAGUE_KEYS:
            rows = self.stored.repo.list_upcoming_fixtures(comp_key, limit=limit)
            for row in rows:
                fid = int(row["fixture_id"])
                if not is_valid_fixture_id(fid):
                    continue
                existing = self.repository.get_prediction_by_fixture(fid)
                if existing and not existing.get("no_prediction_flag"):
                    picks.append(self._serialize_prediction_row(existing))
                    continue
                generated = self.predict_fixture(fid, persist=True, competition_key=comp_key)
                pred = generated.get("prediction")
                if pred and not pred.get("no_prediction_flag"):
                    picks.append(pred)
                if len(picks) >= limit:
                    break
            if len(picks) >= limit:
                break

        return {
            "competition_keys": list(GOAL_TIMING_PREDICTION_LEAGUE_KEYS),
            "picks": picks[:limit],
            "count": len(picks[:limit]),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _serialize_prediction_row(row: dict[str, Any]) -> dict[str, Any]:
        display_minute = row.get("display_estimated_first_goal_minute")
        if display_minute is None and row.get("estimated_first_goal_minute") is not None:
            display_minute = row.get("estimated_first_goal_minute")
        display_minute_f = float(display_minute) if display_minute is not None else None
        return {
            "fixture_id": row.get("fixture_id"),
            "competition_key": row.get("competition_key"),
            "home_team": row.get("home_team"),
            "away_team": row.get("away_team"),
            "match_date": row.get("match_date").isoformat() if row.get("match_date") else None,
            "first_goal_team": row.get("first_goal_team"),
            "first_goal_time_range": row.get("first_goal_time_range"),
            "display_estimated_first_goal_minute": display_minute_f,
            "estimated_first_goal_minute": display_minute_f,
            "confidence_score": float(row.get("confidence_score") or 0),
            "data_quality_score": float(row.get("data_quality_score") or 0),
            "explanation": row.get("explanation"),
            "no_prediction_flag": bool(row.get("no_prediction_flag")),
            "no_bet_flag": bool(row.get("no_bet_flag")),
            "model_version": row.get("model_version"),
        }
