"""Leakage-safe Last-8 team goal profile builder."""

from __future__ import annotations

import statistics
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Sequence

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.research.last8_team_form.constants import (
    COVERAGE_FULL,
    COVERAGE_INSUFFICIENT,
    COVERAGE_LIMITED_3_4,
    COVERAGE_MAPPING_BLOCKED,
    COVERAGE_PARTIAL_5_7,
    COVERAGE_RESULT_MISSING,
    DEFAULT_RECENCY_WEIGHTS,
    MATCHES_REQUESTED,
)
from worldcup_predictor.research.last8_team_form.match_record import (
    Last8MatchRecord,
    classify_competition_quality,
    is_friendly_competition,
    regulation_goals_from_row,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coverage_status(matches_found: int) -> str:
    if matches_found >= 8:
        return COVERAGE_FULL
    if matches_found >= 5:
        return COVERAGE_PARTIAL_5_7
    if matches_found >= 3:
        return COVERAGE_LIMITED_3_4
    if matches_found > 0:
        return COVERAGE_INSUFFICIENT
    return COVERAGE_RESULT_MISSING


def _weighted_mean(values: list[float], weights: list[float]) -> float | None:
    if not values or not weights or len(values) != len(weights):
        return None
    denom = sum(weights)
    if denom <= 0:
        return None
    return sum(v * w for v, w in zip(values, weights)) / denom


def _rows_to_records(
    rows: Sequence[dict[str, Any]],
    *,
    team_name: str,
    target_competition: str,
    source: str,
) -> list[Last8MatchRecord]:
    out: list[Last8MatchRecord] = []
    for row in rows:
        comp = str(row.get("competition_key") or row.get("league") or "")
        if is_friendly_competition(comp):
            continue
        parsed = regulation_goals_from_row(row, team_name=team_name)
        if not parsed:
            continue
        gf, ga, is_home = parsed
        home = str(row.get("home_team") or "")
        away = str(row.get("away_team") or "")
        total = gf + ga
        out.append(
            Last8MatchRecord(
                fixture_id=int(row["fixture_id"]) if row.get("fixture_id") is not None else None,
                kickoff_utc=str(row.get("kickoff_utc") or row.get("eventDate") or ""),
                competition_key=comp,
                home_team=home,
                away_team=away,
                goals_for=gf,
                goals_against=ga,
                is_home=is_home,
                opponent=away if is_home else home,
                total_goals=total,
                btts=gf > 0 and ga > 0,
                over_2_5=total > 2,
                clean_sheet=ga == 0,
                source=source,
                competition_tier=classify_competition_quality(comp, target_competition),
            )
        )
    return out


def _aggregate_profile(
    *,
    team_id: int | None,
    team_name: str,
    target_fixture_id: int | None,
    cutoff_time_utc: str,
    competition_context: str,
    matches: list[Last8MatchRecord],
    recency_weights: tuple[float, ...],
    provider_mix: dict[str, int],
    warnings: list[str],
) -> dict[str, Any]:
    n = len(matches)
    status = _coverage_status(n)
    weights = list(recency_weights[:n])
    if len(weights) < n:
        weights.extend([recency_weights[-1]] * (n - len(weights)))

    gf_vals = [float(m.goals_for) for m in matches]
    ga_vals = [float(m.goals_against) for m in matches]
    total_vals = [float(m.total_goals) for m in matches]

    scored_counts = Counter(m.goals_for for m in matches)
    conceded_counts = Counter(m.goals_against for m in matches)
    total_dist = Counter(m.total_goals for m in matches)
    team_goal_dist = Counter(m.goals_for for m in matches)

    home_matches = [m for m in matches if m.is_home]
    away_matches = [m for m in matches if not m.is_home]

    friendly_excluded = sum(1 for _ in warnings if "friendly" in _.lower())
    same_league = sum(1 for m in matches if m.competition_tier == "same_league")
    competition_mismatch = n - same_league if n else 0

    venue_for = home_matches if any(m.is_home for m in matches[:1]) else away_matches
    venue_against = home_matches if venue_for is home_matches else away_matches
    # venue_relevant: use upcoming venue if known from first match context — caller may override
    venue_relevant_for = _weighted_mean(gf_vals, weights) if gf_vals else None
    venue_relevant_against = _weighted_mean(ga_vals, weights) if ga_vals else None

    return {
        "identity": {
            "team_id": team_id,
            "team_name": team_name,
            "target_fixture_id": target_fixture_id,
            "cutoff_time_utc": cutoff_time_utc,
            "matches_requested": MATCHES_REQUESTED,
            "matches_found": n,
            "coverage_status": status,
            "competition_context": competition_context,
        },
        "goal_output": {
            "total_goals_scored_last8": sum(m.goals_for for m in matches),
            "total_goals_conceded_last8": sum(m.goals_against for m in matches),
            "avg_goals_scored_last8": round(sum(gf_vals) / n, 4) if n else None,
            "avg_goals_conceded_last8": round(sum(ga_vals) / n, 4) if n else None,
            "weighted_avg_goals_scored": round(_weighted_mean(gf_vals, weights) or 0, 4) if n else None,
            "weighted_avg_goals_conceded": round(_weighted_mean(ga_vals, weights) or 0, 4) if n else None,
            "median_goals_scored": statistics.median(gf_vals) if n else None,
            "median_goals_conceded": statistics.median(ga_vals) if n else None,
            "max_goals_scored": max(gf_vals) if n else None,
            "scoreless_matches_count": sum(1 for m in matches if m.goals_for == 0),
            "scored_in_match_count": sum(1 for m in matches if m.goals_for > 0),
            "scored_2plus_count": sum(1 for m in matches if m.goals_for >= 2),
            "scored_3plus_count": sum(1 for m in matches if m.goals_for >= 3),
            "scored_goal_distribution": dict(sorted(scored_counts.items())),
        },
        "defensive_output": {
            "clean_sheets_count": sum(1 for m in matches if m.clean_sheet),
            "conceded_in_match_count": sum(1 for m in matches if m.goals_against > 0),
            "conceded_2plus_count": sum(1 for m in matches if m.goals_against >= 2),
            "conceded_3plus_count": sum(1 for m in matches if m.goals_against >= 3),
            "conceded_goal_distribution": dict(sorted(conceded_counts.items())),
        },
        "market_shape": {
            "BTTS_yes_count": sum(1 for m in matches if m.btts),
            "BTTS_no_count": sum(1 for m in matches if not m.btts),
            "over_2_5_count": sum(1 for m in matches if m.over_2_5),
            "under_2_5_count": sum(1 for m in matches if not m.over_2_5),
            "total_goal_distribution": dict(sorted(total_dist.items())),
            "team_goal_distribution": dict(sorted(team_goal_dist.items())),
        },
        "venue_split": {
            "home_matches_count": len(home_matches),
            "away_matches_count": len(away_matches),
            "home_goals_for": sum(m.goals_for for m in home_matches),
            "home_goals_against": sum(m.goals_against for m in home_matches),
            "away_goals_for": sum(m.goals_for for m in away_matches),
            "away_goals_against": sum(m.goals_against for m in away_matches),
            "venue_relevant_avg_goals_for": venue_relevant_for,
            "venue_relevant_avg_goals_against": venue_relevant_against,
        },
        "recency": {
            "weights_applied": weights,
            "weight_version": "DEFAULT_RECENCY_WEIGHTS_v1",
        },
        "opponent_quality": {
            "annotated": False,
            "note": "Opponent league position/strength not fabricated; available only when standings data present.",
        },
        "competition_quality": {
            "same_league_count": same_league,
            "competition_mismatch_count": competition_mismatch,
            "friendly_excluded_count": friendly_excluded,
            "tier_mix": dict(Counter(m.competition_tier for m in matches)),
        },
        "data_quality": {
            "provider_source_mix": provider_mix,
            "missing_result_count": 0,
            "warnings": warnings,
            "generated_at_utc": _utc_now(),
        },
        "matches": [
            {
                "fixture_id": m.fixture_id,
                "kickoff_utc": m.kickoff_utc,
                "opponent": m.opponent,
                "is_home": m.is_home,
                "goals_for": m.goals_for,
                "goals_against": m.goals_against,
                "competition_key": m.competition_key,
                "competition_tier": m.competition_tier,
                "source": m.source,
            }
            for m in matches
        ],
    }


def build_team_last8_goal_profile(
    *,
    team_id: int | None = None,
    team_name: str,
    fixture_kickoff_utc: str,
    competition_context: str,
    target_fixture_id: int | None = None,
    competition_keys: list[str] | None = None,
    match_records: list[dict[str, Any]] | None = None,
    recency_weights: tuple[float, ...] = DEFAULT_RECENCY_WEIGHTS,
    settings: Settings | None = None,
    prefer_same_league: bool = True,
) -> dict[str, Any]:
    """
    Build leakage-safe Last-8 goal profile using only matches completed before kickoff.

    Sources (priority):
    1. Explicit match_records (for CSV backtest / forensic)
    2. SQLite fixtures + fixture_results via FootballIntelligenceRepository
    """
    if not team_name or not fixture_kickoff_utc:
        return {
            "identity": {
                "team_id": team_id,
                "team_name": team_name,
                "target_fixture_id": target_fixture_id,
                "cutoff_time_utc": fixture_kickoff_utc,
                "matches_requested": MATCHES_REQUESTED,
                "matches_found": 0,
                "coverage_status": COVERAGE_MAPPING_BLOCKED,
                "competition_context": competition_context,
            },
            "data_quality": {"warnings": ["missing team_name or kickoff"]},
        }

    warnings: list[str] = []
    provider_mix: dict[str, int] = {}

    if match_records is not None:
        rows = [r for r in match_records if str(r.get("kickoff_utc") or r.get("eventDate") or "") < fixture_kickoff_utc]
        rows.sort(key=lambda r: str(r.get("kickoff_utc") or r.get("eventDate") or ""), reverse=True)
        source = "injected_records"
        provider_mix[source] = len(rows)
    else:
        settings = settings or get_settings()
        repo = FootballIntelligenceRepository(settings.sqlite_path or None)
        keys = competition_keys or ([competition_context] if competition_context else [])
        if not keys:
            return {
                "identity": {
                    "team_id": team_id,
                    "team_name": team_name,
                    "target_fixture_id": target_fixture_id,
                    "cutoff_time_utc": fixture_kickoff_utc,
                    "matches_requested": MATCHES_REQUESTED,
                    "matches_found": 0,
                    "coverage_status": COVERAGE_MAPPING_BLOCKED,
                    "competition_context": competition_context,
                },
                "data_quality": {"warnings": ["no competition_keys for DB lookup"]},
            }
        rows = repo.list_team_finished_fixtures_before(
            team_name=team_name,
            before_kickoff=fixture_kickoff_utc,
            competition_keys=keys,
            limit=40,
        )
        source = "sqlite_fixtures_results"
        provider_mix[source] = len(rows)

    records = _rows_to_records(rows, team_name=team_name, target_competition=competition_context, source=source)

    if prefer_same_league and competition_context:
        same = [r for r in records if r.competition_tier == "same_league"]
        if len(same) >= 3:
            records = same
        elif len(same) < len(records):
            warnings.append(f"partial_same_league_only:{len(same)}/{len(records)}")

    records = records[:MATCHES_REQUESTED]

    if not records:
        return _aggregate_profile(
            team_id=team_id,
            team_name=team_name,
            target_fixture_id=target_fixture_id,
            cutoff_time_utc=fixture_kickoff_utc,
            competition_context=competition_context,
            matches=[],
            recency_weights=recency_weights,
            provider_mix=provider_mix,
            warnings=warnings + ["no_completed_matches_before_kickoff"],
        )

    return _aggregate_profile(
        team_id=team_id,
        team_name=team_name,
        target_fixture_id=target_fixture_id,
        cutoff_time_utc=fixture_kickoff_utc,
        competition_context=competition_context,
        matches=records,
        recency_weights=recency_weights,
        provider_mix=provider_mix,
        warnings=warnings,
    )
