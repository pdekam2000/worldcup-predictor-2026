"""Audit paid-provider utilization for EGIE pipelines."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.egie.provider_features.store import EgieProviderFeatureStore
from worldcup_predictor.goal_timing.features.builder import GoalTimingFeatureBuilder
from worldcup_predictor.goal_timing.data.stored_adapter import StoredGoalTimingAdapter


def audit_egie_paid_provider_utilization(
    *,
    competition_key: str = "premier_league",
    limit: int | None = 400,
) -> dict[str, Any]:
    """Compare what is stored vs what enters EGIE feature builder and backtest."""
    stored = StoredGoalTimingAdapter()
    store = EgieProviderFeatureStore()
    fb = GoalTimingFeatureBuilder(stored=stored, max_api_event_fetches=0)

    fixtures = stored.repo.list_finished_fixtures_before(
        before_kickoff=__import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        .replace(tzinfo=None)
        .isoformat(),
        competition_keys=[competition_key],
        limit=limit,
    )
    fixture_ids = [int(f["fixture_id"]) for f in fixtures]

    provider_audit = store.audit_utilization(fixture_ids, competition_key=competition_key)

    # Sample feature builder manifest flags
    manifest_hits = {
        "has_reliable_goal_odds": 0,
        "sportmonks_xg_in_sample": 0,
        "stored_goal_events": 0,
        "provider_features_attached": 0,
    }
    for fid in fixture_ids[: min(50, len(fixture_ids))]:
        fx = stored.get_target_fixture(fid) or {}
        feats = fb.build(fid, competition_key=competition_key)
        manifest = feats.get("provider_manifest") or {}
        if manifest.get("stored_goal_events"):
            manifest_hits["stored_goal_events"] += 1
        if manifest.get("sportmonks_xg_in_sample"):
            manifest_hits["sportmonks_xg_in_sample"] += 1
        if feats.get("has_reliable_goal_odds"):
            manifest_hits["has_reliable_goal_odds"] += 1
        if feats.get("provider_features"):
            manifest_hits["provider_features_attached"] += 1

    n_sample = min(50, len(fixture_ids))
    manifest_pct = {k: round(100 * v / n_sample, 2) if n_sample else 0 for k, v in manifest_hits.items()}

    return {
        "competition_key": competition_key,
        "fixtures_audited": len(fixture_ids),
        "provider_feature_store": provider_audit,
        "egie_feature_builder_sample_n": n_sample,
        "egie_feature_builder_flags_pct": manifest_pct,
        "pipeline_gaps": _pipeline_gaps(provider_audit, manifest_pct),
    }


def _pipeline_gaps(provider_audit: dict[str, Any], manifest_pct: dict[str, float]) -> list[str]:
    gaps: list[str] = []
    cov = provider_audit.get("coverage_pct") or {}
    if cov.get("xg", 0) < 10:
        gaps.append("Sportmonks xG stored but not reaching EGIE features for most fixtures")
    if cov.get("pressure", 0) < 10:
        gaps.append("Pressure Index not available in stored raw data")
    if cov.get("odds", 0) > 50 and manifest_pct.get("has_reliable_goal_odds", 0) < 50:
        gaps.append("Odds stored in SQLite but EGIE has_reliable_goal_odds not set")
    if cov.get("lineups", 0) < 5:
        gaps.append("Lineups barely ingested into EGIE raw store")
    if cov.get("injuries", 0) < 5:
        gaps.append("Injuries barely ingested into EGIE raw store")
    if cov.get("advanced_stats", 0) < 5:
        gaps.append("API-Football fixture statistics rarely in EGIE raw store")
    return gaps
