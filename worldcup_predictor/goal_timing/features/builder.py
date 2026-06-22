"""Build leakage-safe goal timing feature vectors (Phase 51C)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.goal_timing.config import GOAL_TIMING_MINUTE_RANGES
from worldcup_predictor.goal_timing.data.api_football_fallback import ApiFootballGoalTimingFallback
from worldcup_predictor.goal_timing.data.fixture_ids import is_valid_fixture_id
from worldcup_predictor.goal_timing.data.sportmonks_coverage import probe_sportmonks_goal_timing_coverage
from worldcup_predictor.goal_timing.data.stored_adapter import StoredGoalTimingAdapter
from worldcup_predictor.goal_timing.features.aggregates import (
    accumulate_team_timing,
    league_baseline_timing,
    opponent_adjusted_features,
    recent_form_timing,
)
from worldcup_predictor.goal_timing.leagues import (
    GOAL_TIMING_ALLOWED_LEAGUE_KEYS,
    is_goal_timing_allowed_league,
)

FEATURE_VERSION = "v0.2_phase51c"


class GoalTimingFeatureBuilder:
    """Builds point-in-time features from stored data (SQLite + EGIE PG). No live API."""

    def __init__(
        self,
        *,
        stored: StoredGoalTimingAdapter | None = None,
        api_fallback: ApiFootballGoalTimingFallback | None = None,
        max_api_event_fetches: int = 0,
    ) -> None:
        self.stored = stored or StoredGoalTimingAdapter()
        self.api_fallback = api_fallback or ApiFootballGoalTimingFallback()
        self.max_api_event_fetches = max(0, int(max_api_event_fetches))
        self._api_budget_remaining = self.max_api_event_fetches

    def build(
        self,
        fixture_id: int,
        *,
        competition_key: str | None = None,
        as_of: datetime | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ctx = context or {}
        self._api_budget_remaining = self.max_api_event_fetches

        if not is_valid_fixture_id(fixture_id):
            return self._empty_features(
                int(fixture_id or 0),
                competition_key,
                as_of,
                reason="invalid_fixture_id",
            )

        target = self.stored.get_target_fixture(fixture_id)
        if target is None and self.api_fallback._settings.api_football_configured:
            meta = self.api_fallback.get_fixture_metadata(fixture_id)
            if meta:
                target = self._fixture_from_api_item(meta, fixture_id)

        if not target:
            return self._empty_features(fixture_id, competition_key, as_of, reason="fixture_not_found")

        comp_key = str(competition_key or target.get("competition_key") or "")
        if not is_goal_timing_allowed_league(comp_key):
            return self._empty_features(
                fixture_id,
                comp_key,
                as_of,
                reason="league_not_in_goal_timing_scope",
                home_team=target.get("home_team"),
                away_team=target.get("away_team"),
            )

        kickoff_raw = target.get("kickoff_utc")
        as_of_dt = as_of or self.stored.parse_kickoff(kickoff_raw) or datetime.now(timezone.utc)
        before_iso = kickoff_raw or as_of_dt.isoformat()
        home_team = str(target.get("home_team") or ctx.get("home_team") or "Home")
        away_team = str(target.get("away_team") or ctx.get("away_team") or "Away")

        home_history = self._enriched_team_history(home_team, before_iso, comp_key)
        away_history = self._enriched_team_history(away_team, before_iso, comp_key)
        league_history = self._enriched_league_history(comp_key, before_iso)

        home_feats = accumulate_team_timing(home_history, home_team)
        away_feats = accumulate_team_timing(away_history, away_team)
        home_recent = recent_form_timing(home_history, home_team)
        away_recent = recent_form_timing(away_history, away_team)
        league_base = league_baseline_timing(league_history)
        home_adj = opponent_adjusted_features(home_feats, away_feats)
        away_adj = opponent_adjusted_features(away_feats, home_feats)

        sportmonks = probe_sportmonks_goal_timing_coverage(
            sample_fixture_ids=[fixture_id, *[m.fixture_id for m in home_history[:5]]],
        )

        provider_manifest = {
            "stored_fixtures": bool(target),
            "stored_goal_events": (home_feats.get("samples_with_goal_minute_data", 0) > 0)
            or (away_feats.get("samples_with_goal_minute_data", 0) > 0),
            "api_football_fallback_used": self.api_fallback.api_calls_made > 0,
            "api_football_calls": self.api_fallback.api_calls_made,
            "sportmonks_configured": sportmonks.get("sportmonks_configured"),
            "sportmonks_xg_in_sample": sportmonks.get("xg_snapshots_in_sample", 0) > 0,
            "postgres_historical": True,
        }

        data_quality = self._compute_data_quality(
            home_feats,
            away_feats,
            league_base,
            provider_manifest,
        )

        return {
            "fixture_id": fixture_id,
            "competition_key": comp_key,
            "as_of": as_of_dt.isoformat(),
            "home_team": home_team,
            "away_team": away_team,
            "match_date": kickoff_raw,
            "minute_ranges": list(GOAL_TIMING_MINUTE_RANGES),
            "feature_version": FEATURE_VERSION,
            "team_goals_scored_by_range": {
                "home": home_feats.get("goals_scored_by_range"),
                "away": away_feats.get("goals_scored_by_range"),
            },
            "team_goals_conceded_by_range": {
                "home": home_feats.get("goals_conceded_by_range"),
                "away": away_feats.get("goals_conceded_by_range"),
            },
            "first_goal_team_distribution": {
                "home": home_feats.get("first_goal_team_distribution"),
                "away": away_feats.get("first_goal_team_distribution"),
            },
            "first_goal_minute_distribution": {
                "home": home_feats.get("first_goal_minute_distribution"),
                "away": away_feats.get("first_goal_minute_distribution"),
                "league": league_base.get("first_goal_minute_distribution"),
            },
            "home_away_split": {
                "home_team_home_scoring": home_feats.get("home_goals_scored_by_range"),
                "home_team_away_scoring": home_feats.get("away_goals_scored_by_range"),
                "away_team_home_scoring": away_feats.get("home_goals_scored_by_range"),
                "away_team_away_scoring": away_feats.get("away_goals_scored_by_range"),
            },
            "recent_form_timing": {
                "home": home_recent,
                "away": away_recent,
            },
            "goals_before_minute": {
                "home": home_feats.get("goals_before_minute_rates"),
                "away": away_feats.get("goals_before_minute_rates"),
            },
            "no_goal_before_minute_probability": {
                "home": home_feats.get("no_goal_before_minute_probability"),
                "away": away_feats.get("no_goal_before_minute_probability"),
                "league": league_base.get("no_goal_before_minute_probability"),
            },
            "opponent_adjusted": {
                "home_perspective": home_adj,
                "away_perspective": away_adj,
            },
            "league_baseline_timing": league_base,
            "data_quality_score": data_quality,
            "history_samples": {
                "home_matches": home_feats.get("samples", 0),
                "away_matches": away_feats.get("samples", 0),
                "league_matches": league_base.get("samples", 0),
                "home_with_goal_minutes": home_feats.get("samples_with_goal_minute_data", 0),
                "away_with_goal_minutes": away_feats.get("samples_with_goal_minute_data", 0),
            },
            "provider_manifest": provider_manifest,
            "sportmonks_coverage": sportmonks,
            "has_historical_goal_events": provider_manifest["stored_goal_events"],
            "has_reliable_goal_odds": False,
        }

    def _enriched_team_history(self, team_name: str, before_iso: str, comp_key: str):
        history = self.stored.team_history_before(
            team_name,
            before_kickoff=before_iso,
            competition_keys=list(GOAL_TIMING_ALLOWED_LEAGUE_KEYS),
        )
        return self._maybe_fill_missing_events(history, comp_key)

    def _enriched_league_history(self, comp_key: str, before_iso: str):
        history = self.stored.league_history_before(
            before_kickoff=before_iso,
            competition_key=comp_key,
            limit=120,
        )
        return self._maybe_fill_missing_events(history, comp_key)

    def _maybe_fill_missing_events(self, history, comp_key: str):
        """Fill missing goal events from SQLite or EGIE PostgreSQL only — no live API."""
        for match in history:
            if not is_valid_fixture_id(match.fixture_id):
                continue
            if match.goal_events:
                continue
            events, source = self.api_fallback.ensure_goal_events(
                match.fixture_id,
                home_team=match.home_team,
                away_team=match.away_team,
                competition_key=match.competition_key or comp_key,
                persist=True,
            )
            match.goal_events = events
            match.has_goal_minute_data = bool(events) or match.first_goal_minute is not None
        return history

    @staticmethod
    def _compute_data_quality(
        home_feats: dict[str, Any],
        away_feats: dict[str, Any],
        league_base: dict[str, Any],
        manifest: dict[str, Any],
    ) -> float:
        home_n = int(home_feats.get("samples") or 0)
        away_n = int(away_feats.get("samples") or 0)
        home_ev = int(home_feats.get("samples_with_goal_minute_data") or 0)
        away_ev = int(away_feats.get("samples_with_goal_minute_data") or 0)
        event_cov = (home_ev + away_ev) / max(home_n + away_n, 1)
        sample_cov = min(1.0, (home_n + away_n) / 30.0)
        league_cov = min(1.0, int(league_base.get("samples") or 0) / 100.0)
        manifest_cov = sum(1 for v in manifest.values() if v) / max(len(manifest), 1)
        score = 0.45 * event_cov + 0.25 * sample_cov + 0.2 * league_cov + 0.1 * manifest_cov
        return round(min(1.0, max(0.0, score)), 4)

    @staticmethod
    def _fixture_from_api_item(item: dict[str, Any], fixture_id: int) -> dict[str, Any]:
        fixture = item.get("fixture") or {}
        teams = item.get("teams") or {}
        league = item.get("league") or {}
        home = teams.get("home") or {}
        away = teams.get("away") or {}
        from worldcup_predictor.config.league_registry import resolve_competition_by_league_id

        league_id = int(league.get("id") or 0)
        comp = resolve_competition_by_league_id(league_id)
        comp_key = comp.key if comp else str(league.get("name") or "unknown")
        return {
            "fixture_id": fixture_id,
            "competition_key": comp_key,
            "home_team": home.get("name") or "Home",
            "away_team": away.get("name") or "Away",
            "kickoff_utc": fixture.get("date"),
            "status": (fixture.get("status") or {}).get("short") or "NS",
            "is_placeholder": 0,
        }

    @staticmethod
    def _empty_features(
        fixture_id: int,
        competition_key: str | None,
        as_of: datetime | None,
        *,
        reason: str,
        home_team: str | None = None,
        away_team: str | None = None,
    ) -> dict[str, Any]:
        empty_range = {k: 0.0 for k in GOAL_TIMING_MINUTE_RANGES}
        empty_dist = {"scored_first": 0.0, "conceded_first": 0.0, "no_first_goal_data": 1.0}
        return {
            "fixture_id": fixture_id,
            "competition_key": competition_key,
            "as_of": (as_of or datetime.now(timezone.utc)).isoformat(),
            "home_team": home_team,
            "away_team": away_team,
            "feature_version": FEATURE_VERSION,
            "minute_ranges": list(GOAL_TIMING_MINUTE_RANGES),
            "data_quality_score": 0.0,
            "team_goals_scored_by_range": {"home": empty_range, "away": empty_range},
            "team_goals_conceded_by_range": {"home": empty_range, "away": empty_range},
            "first_goal_team_distribution": {"home": empty_dist, "away": empty_dist},
            "first_goal_minute_distribution": {"home": empty_range, "away": empty_range, "league": empty_range},
            "home_away_split": {},
            "recent_form_timing": {},
            "goals_before_minute": {},
            "no_goal_before_minute_probability": {"home": {}, "away": {}, "league": {}},
            "opponent_adjusted": {},
            "league_baseline_timing": {"samples": 0, "first_goal_minute_distribution": empty_range},
            "history_samples": {},
            "provider_manifest": {"error": reason},
            "has_historical_goal_events": False,
        }
