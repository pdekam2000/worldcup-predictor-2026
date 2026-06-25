"""Build baseline and baseline+xG datasets for EGIE xG backtest."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.egie.guards import backtest_mode
from worldcup_predictor.egie.uefa_club.feature_extractors import parse_match_result
from worldcup_predictor.egie.uefa_club.sportmonks_ingest import cache_path, load_cache
from worldcup_predictor.egie.xg_backtest.xg_feature_builder import XG_FEATURE_NAMES, XgFeatureBuilder
from worldcup_predictor.goal_timing.agents.orchestrator import GoalTimingAgentOrchestrator
from worldcup_predictor.goal_timing.data.stored_adapter import StoredGoalTimingAdapter
from worldcup_predictor.goal_timing.features.builder import GoalTimingFeatureBuilder
from worldcup_predictor.goal_timing.models_stat.baseline import GoalTimingBaselineModel

logger = logging.getLogger(__name__)

ARTIFACT_DIR = Path("artifacts/phase54f_egie_xg_backtest")
BASELINE_COLS = (
    "home_goal_rate_proxy",
    "away_goal_rate_proxy",
    "data_quality_score",
    "home_history_samples",
    "away_history_samples",
)

GOAL_RANGE_BUCKETS = ("0-15", "16-30", "31-45+")


def _minute_to_range(minute: int | None) -> str | None:
    if minute is None:
        return None
    if minute <= 15:
        return "0-15"
    if minute <= 30:
        return "16-30"
    return "31-45+"


def _load_fixtures_from_cache(settings: Settings) -> list[dict[str, Any]]:
    root = Path.cwd() / "data" / "egie" / "uefa_club" / "raw"
    fixtures: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        data = (blob.get("payload") or {}).get("data")
        if not isinstance(data, dict):
            continue
        sm_id = int(blob.get("sportmonks_fixture_id") or data.get("id") or path.stem)
        home = away = ""
        home_id = away_id = None
        for p in data.get("participants") or []:
            if not isinstance(p, dict):
                continue
            loc = str((p.get("meta") or {}).get("location") or "").lower()
            if loc == "home":
                home = str(p.get("name") or "")
                home_id = p.get("id")
            elif loc == "away":
                away = str(p.get("name") or "")
                away_id = p.get("id")
        league_id = int(data.get("league_id") or 0)
        comp = {2: "champions_league", 5: "europa_league", 2286: "conference_league"}.get(
            league_id, "uefa_club"
        )
        fixtures.append(
            {
                "sportmonks_fixture_id": sm_id,
                "competition_key": comp,
                "league_id": league_id,
                "season_id": data.get("season_id"),
                "kickoff_utc": data.get("starting_at"),
                "home_team": home,
                "away_team": away,
                "home_team_id": home_id,
                "away_team_id": away_id,
            }
        )
    return fixtures


class EgieXgDatasetBuilder:
    """Produce baseline and baseline+xG enriched rows for backtest."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.xg_builder = XgFeatureBuilder(self.settings)
        self.stored = StoredGoalTimingAdapter(self.settings)
        self.feature_builder = GoalTimingFeatureBuilder(stored=self.stored, max_api_event_fetches=0)
        self.agents = GoalTimingAgentOrchestrator()
        self.baseline_model = GoalTimingBaselineModel()

    def build_rows(self, fixtures: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        fixtures = fixtures or _load_fixtures_from_cache(self.settings)
        xg_feats = self.xg_builder.build_chronological_features()
        rows: list[dict[str, Any]] = []

        with backtest_mode():
            for fx in sorted(fixtures, key=lambda x: str(x.get("kickoff_utc") or "")):
                sm_id = int(fx.get("sportmonks_fixture_id") or 0)
                if sm_id <= 0:
                    continue
                cache = load_cache(cache_path(self.settings, sm_id))
                payload = (cache or {}).get("payload")
                result = parse_match_result(payload, home_team=fx.get("home_team"), away_team=fx.get("away_team"))
                kickoff = str(fx.get("kickoff_utc") or "")
                try:
                    kickoff_dt = datetime.fromisoformat(kickoff.replace("Z", "+00:00")).replace(tzinfo=None)
                except ValueError:
                    kickoff_dt = datetime.now(timezone.utc).replace(tzinfo=None)

                first_minute = result.get("first_goal_minute")
                first_team = result.get("first_goal_team_side")
                home_goals = int(result.get("home_goals") or 0)
                away_goals = int(result.get("away_goals") or 0)
                total_goals = home_goals + away_goals

                ctx = {
                    "home_team": str(fx.get("home_team") or ""),
                    "away_team": str(fx.get("away_team") or ""),
                    "match_date": kickoff_dt,
                }
                features = self.feature_builder.build(
                    sm_id, competition_key=str(fx.get("competition_key") or "champions_league"),
                    as_of=kickoff_dt, context=ctx,
                )
                agent_outputs = self.agents.run(sm_id, features=features, context=ctx)
                baseline_pred = self.baseline_model.predict(features, agent_outputs)
                hs = features.get("history_samples") or {}
                home_dist = (features.get("first_goal_team_distribution") or {}).get("home") or {}
                away_dist = (features.get("first_goal_team_distribution") or {}).get("away") or {}

                xg = xg_feats.get(sm_id, {"xg_available": False})

                row: dict[str, Any] = {
                    "sportmonks_fixture_id": sm_id,
                    "competition_key": fx.get("competition_key"),
                    "league_id": fx.get("league_id"),
                    "season_id": fx.get("season_id"),
                    "kickoff_utc": kickoff,
                    "home_team": fx.get("home_team"),
                    "away_team": fx.get("away_team"),
                    "label_first_goal_team": first_team,
                    "label_goal_range": _minute_to_range(int(first_minute) if first_minute is not None else None),
                    "label_total_goals": total_goals,
                    "label_over_25": int(total_goals > 2),
                    "label_home_goals": home_goals,
                    "label_away_goals": away_goals,
                    "baseline_first_goal_team": baseline_pred.get("first_goal_team"),
                    "baseline_goal_range": baseline_pred.get("first_goal_time_range"),
                    "home_goal_rate_proxy": float(home_dist.get("scored_first") or 0.33),
                    "away_goal_rate_proxy": float(away_dist.get("scored_first") or 0.33),
                    "data_quality_score": float(features.get("data_quality_score") or 0.0),
                    "home_history_samples": int(hs.get("home_matches") or 0),
                    "away_history_samples": int(hs.get("away_matches") or 0),
                    "xg_available": bool(xg.get("xg_available")),
                }
                for name in XG_FEATURE_NAMES:
                    row[name] = xg.get(name)
                rows.append(row)
        return rows

    def build_datasets(
        self,
        fixtures: list[dict[str, Any]] | None = None,
    ) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
        rows = self.build_rows(fixtures)
        df = pd.DataFrame(rows)
        baseline_df = df.copy()
        xg_df = df.copy()

        coverage = {
            "fixtures_total": len(df),
            "fixtures_with_xg": int(df["xg_available"].sum()) if "xg_available" in df.columns else 0,
            "xg_coverage_pct": round(100 * float(df["xg_available"].mean()), 2) if len(df) else 0.0,
            "leagues": sorted(df["competition_key"].dropna().unique().tolist()) if len(df) else [],
            "seasons": sorted({str(x) for x in df["season_id"].dropna().unique()}) if len(df) else [],
            "labels": {
                "first_goal_team_non_null": int(df["label_first_goal_team"].notna().sum()) if len(df) else 0,
                "goal_range_non_null": int(df["label_goal_range"].notna().sum()) if len(df) else 0,
                "over_25_labeled": int(df["label_over_25"].notna().sum()) if len(df) else 0,
            },
        }
        return baseline_df, xg_df, coverage

    def save(self, output_dir: Path | None = None) -> dict[str, Any]:
        out_dir = output_dir or ARTIFACT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        baseline_df, xg_df, coverage = self.build_datasets()
        baseline_path = out_dir / "egie_baseline_dataset.parquet"
        xg_path = out_dir / "egie_baseline_plus_xg_dataset.parquet"
        baseline_df.to_parquet(baseline_path, index=False)
        xg_df.to_parquet(xg_path, index=False)
        meta = {"coverage": coverage, "baseline_path": str(baseline_path), "xg_path": str(xg_path)}
        (out_dir / "dataset_coverage.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
        return meta
