"""Build pre-match and in-play pressure shadow datasets for EGIE backtest."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.egie.guards import backtest_mode
from worldcup_predictor.egie.pressure_backtest.pressure_feature_builder import (
    MINUTE_ONLY_FEATURES,
    PRESSURE_FEATURE_NAMES,
    PressureFeatureBuilder,
)
from worldcup_predictor.egie.uefa_club.feature_extractors import parse_match_result, parse_uefa_goal_events
from worldcup_predictor.egie.uefa_club.sportmonks_ingest import cache_path, load_cache
from worldcup_predictor.egie.xg_backtest.egie_xg_dataset_builder import BASELINE_COLS, GOAL_RANGE_BUCKETS, _minute_to_range
from worldcup_predictor.goal_timing.agents.orchestrator import GoalTimingAgentOrchestrator
from worldcup_predictor.goal_timing.data.stored_adapter import StoredGoalTimingAdapter
from worldcup_predictor.goal_timing.features.builder import GoalTimingFeatureBuilder
from worldcup_predictor.goal_timing.models_stat.baseline import GoalTimingBaselineModel

logger = logging.getLogger(__name__)

ARTIFACT_DIR = Path("artifacts/phase54h1_pressure_shadow_backtest")
ARTIFACT_DIR_H2 = Path("artifacts/phase54h2_pressure_expansion_proxy_audit")
ARTIFACT_DIR_H7 = Path("artifacts/phase54h7_expanded_pressure_backtest")

_CACHE_META_ROOTS = (
    Path("data/egie/uefa_club/raw"),
    Path("data/data/egie/uefa_club/raw"),
    Path("data/feature_store/sportmonks_pressure/raw"),
    Path("data/feature_store/sportmonks_xg/raw"),
)

_LEAGUE_COMP = {
    2: "champions_league",
    5: "europa_league",
    2286: "conference_league",
    732: "world_cup",
}


def _load_pressure_fixture_meta(settings: Settings) -> list[dict[str, Any]]:
    fixtures_by_id: dict[int, dict[str, Any]] = {}
    for root in _CACHE_META_ROOTS:
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*.json"))[:3000]:
            try:
                blob = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            data = (blob.get("payload") or {}).get("data")
            if not isinstance(data, dict):
                continue
            sm_id = int(blob.get("sportmonks_fixture_id") or data.get("id") or path.stem)
            if sm_id in fixtures_by_id:
                continue
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
            comp = _LEAGUE_COMP.get(league_id, "uefa_club")
            fixtures_by_id[sm_id] = {
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
    return list(fixtures_by_id.values())


def _meta_from_summary(summary: dict[str, Any]) -> dict[str, Any]:
    league_id = int(summary.get("league_id") or 0)
    return {
        "sportmonks_fixture_id": int(summary.get("sportmonks_fixture_id") or 0),
        "competition_key": _LEAGUE_COMP.get(league_id, "uefa_club"),
        "league_id": league_id,
        "season_id": summary.get("season_id"),
        "kickoff_utc": summary.get("match_started_at"),
        "home_team": summary.get("home_team_name") or "",
        "away_team": summary.get("away_team_name") or "",
        "home_team_id": summary.get("home_team_id"),
        "away_team_id": summary.get("away_team_id"),
    }


def _minute_proxy_row_features(
    *,
    before_minute: int,
    goal_index: int,
    goals_before_home: int,
    goals_before_away: int,
) -> dict[str, Any]:
    return {
        "current_minute": before_minute,
        "elapsed_minute": before_minute,
        "minute_normalized": round(before_minute / 90.0, 4) if before_minute >= 0 else 0.0,
        "goals_before_home": goals_before_home,
        "goals_before_away": goals_before_away,
        "score_diff": goals_before_home - goals_before_away,
        "goal_index": goal_index,
    }


def _load_fixture_payload(settings: Settings, sm_id: int) -> Any:
    cache = load_cache(cache_path(settings, sm_id))
    if cache:
        return (cache or {}).get("payload")
    for root in _CACHE_META_ROOTS:
        path = root / f"{sm_id}.json"
        if not path.is_file():
            continue
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        payload = blob.get("payload")
        if payload:
            return payload
    return None


def _coverage_breakdown(df: pd.DataFrame, col: str) -> dict[str, int]:
    if df.empty or col not in df.columns:
        return {}
    return {str(k): int(v) for k, v in df[col].value_counts().to_dict().items()}


class PressureDatasetBuilder:
    """Produce pre-match rolling and in-play pressure datasets."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.pressure_builder = PressureFeatureBuilder(self.settings)
        self.stored = StoredGoalTimingAdapter(self.settings)
        self.feature_builder = GoalTimingFeatureBuilder(stored=self.stored, max_api_event_fetches=0)
        self.agents = GoalTimingAgentOrchestrator()
        self.baseline_model = GoalTimingBaselineModel()

    def _baseline_features(
        self,
        sm_id: int,
        fx: dict[str, Any],
        kickoff_dt: datetime,
    ) -> dict[str, Any]:
        ctx = {
            "home_team": str(fx.get("home_team") or ""),
            "away_team": str(fx.get("away_team") or ""),
            "match_date": kickoff_dt,
        }
        features = self.feature_builder.build(
            sm_id,
            competition_key=str(fx.get("competition_key") or "champions_league"),
            as_of=kickoff_dt,
            context=ctx,
        )
        hs = features.get("history_samples") or {}
        home_dist = (features.get("first_goal_team_distribution") or {}).get("home") or {}
        away_dist = (features.get("first_goal_team_distribution") or {}).get("away") or {}
        return {
            "home_goal_rate_proxy": float(home_dist.get("scored_first") or 0.33),
            "away_goal_rate_proxy": float(away_dist.get("scored_first") or 0.33),
            "data_quality_score": float(features.get("data_quality_score") or 0.0),
            "home_history_samples": int(hs.get("home_matches") or 0),
            "away_history_samples": int(hs.get("away_matches") or 0),
        }

    def build_prematch_rows(self, pressure_fixture_ids: set[int]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        summaries = self.pressure_builder.load_ordered_summaries()
        prematch_feats = self.pressure_builder.build_prematch_chronological_features(summaries)
        meta_by_id = {int(f["sportmonks_fixture_id"]): f for f in _load_pressure_fixture_meta(self.settings)}
        rows: list[dict[str, Any]] = []
        unusable: list[dict[str, Any]] = []

        with backtest_mode():
            for summary in summaries:
                sm_id = int(summary.get("sportmonks_fixture_id") or 0)
                if sm_id not in pressure_fixture_ids:
                    continue
                fx = meta_by_id.get(sm_id) or _meta_from_summary(summary)
                payload = _load_fixture_payload(self.settings, sm_id)
                if not payload:
                    unusable.append(
                        {
                            "sportmonks_fixture_id": sm_id,
                            "reason": "missing_cache_or_meta",
                        }
                    )
                    continue

                result = parse_match_result(
                    payload, home_team=fx.get("home_team"), away_team=fx.get("away_team")
                )
                kickoff = str(fx.get("kickoff_utc") or summary.get("match_started_at") or "")
                try:
                    kickoff_dt = datetime.fromisoformat(kickoff.replace("Z", "+00:00")).replace(tzinfo=None)
                except ValueError:
                    kickoff_dt = datetime.now(timezone.utc).replace(tzinfo=None)

                first_minute = result.get("first_goal_minute")
                first_side = result.get("first_goal_team_side")
                home_goals = int(result.get("home_goals") or 0)
                away_goals = int(result.get("away_goals") or 0)
                total_goals = home_goals + away_goals

                pressure = prematch_feats.get(sm_id, {"pressure_available": False})
                baseline = self._baseline_features(sm_id, fx, kickoff_dt)

                row: dict[str, Any] = {
                    "dataset_type": "prematch",
                    "sportmonks_fixture_id": sm_id,
                    "competition_key": fx.get("competition_key"),
                    "league_id": fx.get("league_id"),
                    "season_id": fx.get("season_id"),
                    "kickoff_utc": kickoff,
                    "home_team": fx.get("home_team"),
                    "away_team": fx.get("away_team"),
                    "label_first_goal_team": first_side if first_side in ("home", "away") else None,
                    "label_goal_range": _minute_to_range(
                        int(first_minute) if first_minute is not None else None
                    ),
                    "label_home_goals": home_goals,
                    "label_away_goals": away_goals,
                    "label_total_goals": total_goals,
                    "pressure_available": bool(pressure.get("pressure_available")),
                }
                row.update(baseline)
                for name in PRESSURE_FEATURE_NAMES:
                    row[name] = pressure.get(name)
                row["pressure_history_matches_home"] = pressure.get("pressure_history_matches_home")
                row["pressure_history_matches_away"] = pressure.get("pressure_history_matches_away")
                rows.append(row)
        return rows, unusable

    def build_inplay_rows(self, pressure_fixture_ids: set[int]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        summaries = self.pressure_builder.load_ordered_summaries()
        meta_by_id = {int(f["sportmonks_fixture_id"]): f for f in _load_pressure_fixture_meta(self.settings)}
        rows: list[dict[str, Any]] = []
        unusable: list[dict[str, Any]] = []

        with backtest_mode():
            for summary in summaries:
                sm_id = int(summary.get("sportmonks_fixture_id") or 0)
                if sm_id not in pressure_fixture_ids:
                    continue
                fx = meta_by_id.get(sm_id) or _meta_from_summary(summary)
                payload = _load_fixture_payload(self.settings, sm_id)
                if not payload:
                    continue

                home_id = int(fx.get("home_team_id") or summary.get("home_team_id") or 0)
                away_id = int(fx.get("away_team_id") or summary.get("away_team_id") or 0)
                if home_id <= 0 or away_id <= 0:
                    unusable.append({"sportmonks_fixture_id": sm_id, "reason": "missing_team_ids"})
                    continue

                goals = parse_uefa_goal_events(payload)
                if not goals:
                    continue

                kickoff = str(fx.get("kickoff_utc") or summary.get("match_started_at") or "")
                baseline = self._baseline_features(
                    sm_id,
                    fx,
                    datetime.fromisoformat(kickoff.replace("Z", "+00:00")).replace(tzinfo=None)
                    if kickoff
                    else datetime.now(timezone.utc).replace(tzinfo=None),
                )

                goals_before_home = 0
                goals_before_away = 0
                for idx, goal in enumerate(goals):
                    minute = goal.get("minute")
                    if minute is None:
                        continue
                    before = max(0, int(minute))
                    side = goal.get("scoring_side")
                    if side not in ("home", "away"):
                        continue

                    pressure = self.pressure_builder.build_inplay_features_before_minute(
                        sm_id,
                        before_minute=before,
                        home_team_id=home_id,
                        away_team_id=away_id,
                    )
                    prev_minute = goals[idx - 1].get("minute") if idx > 0 else 0
                    window = int(minute) - int(prev_minute or 0) if idx > 0 else int(minute)
                    row: dict[str, Any] = {
                        "dataset_type": "inplay",
                        "sportmonks_fixture_id": sm_id,
                        "goal_index": idx,
                        "league_id": fx.get("league_id"),
                        "season_id": fx.get("season_id"),
                        "kickoff_utc": kickoff,
                        "competition_key": fx.get("competition_key"),
                        "inplay_before_minute": before,
                        "label_next_goal_team": side,
                        "label_goal_minute_bucket": _minute_to_range(int(minute)),
                        "label_next_goal_within_10": int(window <= 10) if idx > 0 else int(int(minute) <= 10),
                        "pressure_available": bool(pressure.get("pressure_available")),
                    }
                    row.update(
                        _minute_proxy_row_features(
                            before_minute=before,
                            goal_index=idx,
                            goals_before_home=goals_before_home,
                            goals_before_away=goals_before_away,
                        )
                    )
                    row.update(baseline)
                    for name in PRESSURE_FEATURE_NAMES:
                        row[name] = pressure.get(name)
                    rows.append(row)
                    if side == "home":
                        goals_before_home += 1
                    else:
                        goals_before_away += 1
        return rows, unusable

    def build_datasets(
        self,
        *,
        phase: str = "54H-1",
    ) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], list[dict[str, Any]]]:
        summaries = self.pressure_builder.load_ordered_summaries()
        pressure_ids = {int(s["sportmonks_fixture_id"]) for s in summaries if s.get("sportmonks_fixture_id")}

        prematch_rows, un1 = self.build_prematch_rows(pressure_ids)
        inplay_rows, un2 = self.build_inplay_rows(pressure_ids)
        unusable = un1 + un2

        prematch_df = pd.DataFrame(prematch_rows)
        inplay_df = pd.DataFrame(inplay_rows)

        summary = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "phase": phase,
            "backtest_only": True,
            "fixtures_with_pressure": len(pressure_ids),
            "prematch_rows": len(prematch_df),
            "inplay_rows": len(inplay_df),
            "prematch_pressure_available": int(prematch_df["pressure_available"].sum()) if len(prematch_df) else 0,
            "inplay_pressure_available": int(inplay_df["pressure_available"].sum()) if len(inplay_df) else 0,
            "leagues": sorted(prematch_df["competition_key"].dropna().unique().tolist()) if len(prematch_df) else [],
            "by_league": {
                "prematch": _coverage_breakdown(prematch_df, "competition_key"),
                "inplay": _coverage_breakdown(inplay_df, "competition_key"),
            },
            "by_season": {
                "prematch": _coverage_breakdown(prematch_df, "season_id"),
                "inplay": _coverage_breakdown(inplay_df, "season_id"),
            },
            "labels": {
                "prematch_first_goal_team": int(prematch_df["label_first_goal_team"].notna().sum())
                if len(prematch_df)
                else 0,
                "prematch_goal_range": int(prematch_df["label_goal_range"].notna().sum()) if len(prematch_df) else 0,
                "inplay_next_goal_team": int(inplay_df["label_next_goal_team"].notna().sum()) if len(inplay_df) else 0,
                "inplay_goal_minute_bucket": int(inplay_df["label_goal_minute_bucket"].notna().sum())
                if len(inplay_df)
                else 0,
            },
            "unusable_fixtures": len(unusable),
        }
        return prematch_df, inplay_df, summary, unusable

    def save(self, output_dir: Path | None = None, *, phase: str = "54H-1") -> dict[str, Any]:
        if output_dir is not None:
            out_dir = output_dir
        elif phase == "54H-7":
            out_dir = ARTIFACT_DIR_H7
        elif phase == "54H-2":
            out_dir = ARTIFACT_DIR_H2
        else:
            out_dir = ARTIFACT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        prematch_df, inplay_df, summary, unusable = self.build_datasets(phase=phase)
        prematch_path = out_dir / "pressure_prematch_dataset.parquet"
        inplay_path = out_dir / "pressure_inplay_dataset.parquet"
        prematch_df.to_parquet(prematch_path, index=False)
        inplay_df.to_parquet(inplay_path, index=False)
        (out_dir / "pressure_dataset_summary.json").write_text(
            json.dumps(summary, indent=2, default=str), encoding="utf-8"
        )
        if unusable:
            pd.DataFrame(unusable).to_csv(out_dir / "unusable_pressure_fixtures.csv", index=False)
        else:
            (out_dir / "unusable_pressure_fixtures.csv").write_text(
                "sportmonks_fixture_id,reason\n", encoding="utf-8"
            )
        return summary
