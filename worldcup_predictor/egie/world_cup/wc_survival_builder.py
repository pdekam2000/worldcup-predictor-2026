"""World Cup survival dataset rows — bypasses GOAL_TIMING_ALLOWED_LEAGUE_KEYS guard."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.egie.provider_features.store import EgieProviderFeatureStore
from worldcup_predictor.egie.world_cup.wc_feature_builder import build_wc_timing_features
from worldcup_predictor.goal_timing.data.stored_adapter import StoredGoalTimingAdapter


def _season_from_kickoff(kickoff: str | None) -> str:
    if not kickoff:
        return "unknown"
    try:
        dt = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
    except ValueError:
        return "unknown"
    y = dt.year
    return str(y)


def _is_scoreless(home_goals: Any, away_goals: Any) -> bool:
    try:
        return int(home_goals or 0) == 0 and int(away_goals or 0) == 0
    except (TypeError, ValueError):
        return False


def build_wc_survival_rows(
    *,
    competition_key: str,
    settings=None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.database.postgres.session import postgres_configured

    settings = settings or get_settings()
    stored = StoredGoalTimingAdapter(settings)
    skip_provider = True
    if postgres_configured(settings):
        try:
            from sqlalchemy import text
            from worldcup_predictor.database.postgres.session import session_scope

            with session_scope(settings) as sess:
                sess.execute(text("SELECT 1"))
            skip_provider = False
        except Exception:
            skip_provider = True
    provider_store = None if skip_provider else EgieProviderFeatureStore(settings)
    before = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    fixtures = stored.repo.list_finished_fixtures_before(
        before_kickoff=before,
        competition_keys=[competition_key],
        limit=limit,
    )
    rows: list[dict[str, Any]] = []
    for fx in reversed(fixtures):
        fixture_id = int(fx["fixture_id"])
        home_team = str(fx.get("home_team") or "")
        away_team = str(fx.get("away_team") or "")
        kickoff = str(fx.get("kickoff_utc") or "")
        comp = str(fx.get("competition_key") or competition_key)
        first_minute = fx.get("first_goal_minute")
        try:
            first_minute = int(first_minute) if first_minute is not None else None
        except (TypeError, ValueError):
            first_minute = None

        scoreless = _is_scoreless(fx.get("home_goals"), fx.get("away_goals"))
        censored = scoreless or first_minute is None

        kickoff_dt = stored.parse_kickoff(kickoff)
        ctx = {"home_team": home_team, "away_team": away_team, "match_date": kickoff_dt}
        features = build_wc_timing_features(
            fixture_id,
            competition_key=comp,
            stored=stored,
            provider_store=provider_store,
            as_of=kickoff_dt,
            context=ctx,
            skip_provider=skip_provider,
        )
        pf = features.get("provider_features") or {}
        hs = features.get("history_samples") or {}

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
                "home_goal_rate": float(
                    (features.get("first_goal_team_distribution") or {})
                    .get("home", {})
                    .get("scored_first")
                    or 0.33
                ),
                "away_goal_rate": float(
                    (features.get("first_goal_team_distribution") or {})
                    .get("away", {})
                    .get("scored_first")
                    or 0.33
                ),
                "dq": float(features.get("data_quality_score") or 0.0),
                "confidence": float(features.get("data_quality_score") or 0.0),
                "home_history_samples": int(hs.get("home_matches") or 0),
                "away_history_samples": int(hs.get("away_matches") or 0),
                "home_xg_for": pf.get("home_xg_for"),
                "away_xg_for": pf.get("away_xg_for"),
                "home_xg_against": pf.get("home_xg_against"),
                "away_xg_against": pf.get("away_xg_against"),
                "pressure_index_home": pf.get("pressure_index_home"),
                "pressure_index_away": pf.get("pressure_index_away"),
                "odds_implied_home": pf.get("odds_implied_home"),
                "odds_implied_away": pf.get("odds_implied_away"),
                "lineup_strength_home": pf.get("lineup_strength_home"),
                "lineup_strength_away": pf.get("lineup_strength_away"),
                "provider_coverage_xg": bool((pf.get("coverage") or {}).get("xg")),
                "provider_coverage_odds": bool((pf.get("coverage") or {}).get("odds")),
                "provider_coverage_pressure": bool((pf.get("coverage") or {}).get("pressure")),
                "provider_coverage_lineups": bool((pf.get("coverage") or {}).get("lineups")),
                "match_state_features": json.dumps(hs),
            }
        )
    return rows
