"""Provider fallback policy — cache-first, no blind API calls."""

from __future__ import annotations

from typing import Any

# Primary → fallback → cache key pattern → freshness (hours) → min completeness
FALLBACK_POLICIES: dict[str, dict[str, Any]] = {
    "fixtures": {
        "primary": "sqlite.fixtures",
        "fallback": "api_football.fixtures",
        "cache_key_prefix": "api_football:fixtures:",
        "freshness_hours": 24,
        "min_completeness": 0.9,
        "conflict_policy": "prefer_canonical_sqlite",
    },
    "results": {
        "primary": "sqlite.fixture_results",
        "fallback": "api_football.fixtures",
        "cache_key_prefix": "api_football:fixtures:",
        "freshness_hours": 168,
        "min_completeness": 0.9,
        "conflict_policy": "prefer_canonical_sqlite",
    },
    "recent_form": {
        "primary": "last8_team_form.profile_builder",
        "fallback": "api_football.fixtures?team=&last=10",
        "cache_key_prefix": "api_football:fixtures:",
        "freshness_hours": 12,
        "min_completeness": 0.5,
        "conflict_policy": "prefer_primary_unless_empty",
    },
    "h2h": {
        "primary": "sqlite.fixtures+fixture_results",
        "fallback": "api_football.fixtures/headtohead",
        "cache_key_prefix": "api_football:fixtures/headtohead:",
        "freshness_hours": 168,
        "min_completeness": 0.3,
        "conflict_policy": "merge_with_provenance",
    },
    "standings": {
        "primary": "sqlite.standings",
        "fallback": "sportmonks.standings",
        "cache_key_prefix": "sportmonks:standings:",
        "freshness_hours": 24,
        "min_completeness": 0.7,
        "conflict_policy": "prefer_fresher_timestamp",
    },
    "xg": {
        "primary": "prematch_feature_snapshots.xg",
        "fallback": "sportmonks.xgfixture",
        "cache_key_prefix": "sportmonks:xg:",
        "freshness_hours": 6,
        "min_completeness": 0.5,
        "conflict_policy": "surface_conflict",
    },
    "lineups": {
        "primary": "prematch_feature_snapshots.lineup",
        "fallback": "api_football.fixtures/lineups",
        "cache_key_prefix": "api_football:lineups:",
        "freshness_hours": 2,
        "min_completeness": 0.6,
        "conflict_policy": "surface_conflict",
    },
    "injuries": {
        "primary": "prematch_feature_snapshots.injury",
        "fallback": "api_football.injuries",
        "cache_key_prefix": "api_football:injuries:",
        "freshness_hours": 6,
        "min_completeness": 0.4,
        "conflict_policy": "surface_conflict",
    },
    "odds": {
        "primary": "frozen_predictions.odds",
        "fallback": "canonical_snapshot.1x2",
        "cache_key_prefix": "odds:1x2:",
        "freshness_hours": 4,
        "min_completeness": 0.8,
        "conflict_policy": "prefer_freeze_snapshot",
    },
}
