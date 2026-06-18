"""Local-first lookups before API-Football calls — Phase 40A."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.database.repository import FootballIntelligenceRepository


def fixture_exists(repo: FootballIntelligenceRepository, fixture_id: int) -> bool:
    return repo.fixture_exists(fixture_id)


def load_fixture_api_item_from_db(
    repo: FootballIntelligenceRepository,
    fixture_id: int,
) -> list[Any] | None:
    """Build API-shaped fixture response from SQLite (for cache/local hit)."""
    row = repo.get_fixture_row(fixture_id)
    if row is None:
        return None
    kickoff = row.get("kickoff_utc") or ""
    item = {
        "fixture": {
            "id": fixture_id,
            "date": kickoff if "T" in kickoff else f"{kickoff}T00:00:00+00:00",
            "status": {"short": row.get("status") or "NS"},
            "venue": {"name": row.get("venue"), "city": row.get("city")},
        },
        "teams": {
            "home": {"name": row.get("home_team"), "id": row.get("home_team_id")},
            "away": {"name": row.get("away_team"), "id": row.get("away_team_id")},
        },
        "league": {
            "id": row.get("league_id"),
            "season": row.get("season"),
            "round": row.get("round_name"),
        },
        "goals": {},
    }
    result_row = repo.get_fixture_result_row(fixture_id)
    if result_row:
        item["goals"] = {
            "home": result_row.get("home_goals"),
            "away": result_row.get("away_goals"),
        }
        ht = result_row.get("halftime_score")
        if ht and "-" in str(ht):
            parts = str(ht).split("-", 1)
            try:
                item["score"] = {"halftime": {"home": int(parts[0]), "away": int(parts[1])}}
            except ValueError:
                pass
    return [item]


def load_match_enrichment_from_db(
    repo: FootballIntelligenceRepository,
    fixture_id: int,
    *,
    max_age_seconds: int = 1800,
) -> dict[str, Any] | None:
    row = repo.get_fixture_enrichment_row(fixture_id)
    if not row:
        return None
    updated = row.get("updated_at")
    if updated and max_age_seconds > 0:
        try:
            ts = datetime.fromisoformat(str(updated))
            age = (datetime.now(timezone.utc).replace(tzinfo=None) - ts).total_seconds()
            if age > max_age_seconds:
                return None
        except ValueError:
            pass
    out: dict[str, Any] = {}
    for key, col in (
        ("events", "events_json"),
        ("lineups", "lineups_json"),
        ("statistics", "statistics_json"),
        ("odds", "odds_json"),
    ):
        raw = row.get(col)
        if raw:
            try:
                out[key] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                pass
    return out if out else None


def team_stats_fresh_in_db(
    repo: FootballIntelligenceRepository,
    *,
    team_name: str,
    competition_key: str,
    max_age_hours: int = 24,
) -> bool:
    form = repo.team_form_summary(
        competition_key=competition_key,
        team_name=team_name,
        limit=3,
    )
    return bool(form.get("matches"))
