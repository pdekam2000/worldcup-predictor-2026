"""Unified A+B fixture discovery for forward evaluation."""

from __future__ import annotations

from datetime import date
from typing import Any

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.forward_evaluation.constants import DEFAULT_TIMEZONE
from worldcup_predictor.forward_evaluation.fixture_model import enrich_unified_fixture


def discover_forward_evaluation_fixtures(
    *,
    target_date: str | date,
    timezone: str = DEFAULT_TIMEZONE,
) -> dict[str, Any]:
    """Discover Tier A + Tier B owner-eligible fixtures (no friendlies)."""
    from worldcup_predictor.gpt_actions.delegation import discover_today_matches

    d = target_date.isoformat() if isinstance(target_date, date) else str(target_date)
    payload = discover_today_matches(target_date=d, timezone=timezone, scope="owner")
    fixtures: list[dict[str, Any]] = []
    for match in payload.get("matches") or []:
        unified = enrich_unified_fixture(
            fixture_id=int(match["fixture_id"]),
            home_team=str(match.get("home_team") or ""),
            away_team=str(match.get("away_team") or ""),
            competition_key=str(match.get("competition_raw") or match.get("competition") or ""),
            kickoff_utc=str(match.get("kickoff_utc") or match.get("kickoff") or ""),
            status=str(match.get("status") or "NS"),
            scope="owner",
        )
        fixtures.append({**match, **unified})
    tier_a = sum(1 for f in fixtures if f.get("validation_tier") == "A")
    tier_b = sum(1 for f in fixtures if f.get("validation_tier") == "B")
    return {
        "date": d,
        "timezone": timezone,
        "scope": "owner",
        "discovered_count": len(fixtures),
        "fixtures": fixtures,
        "tier_a_count": tier_a,
        "tier_b_count": tier_b,
    }


def discover_broad_listing_fixtures(
    *,
    target_date: str | date,
    timezone: str = DEFAULT_TIMEZONE,
) -> dict[str, Any]:
    """Broad listing discovery — all fixtures with classification, not prediction-gated."""
    from worldcup_predictor.gpt_actions.delegation import list_today_matches_broad

    d = target_date.isoformat() if isinstance(target_date, date) else str(target_date)
    return list_today_matches_broad(target_date=d, timezone=timezone)


def fixture_row(conn, fixture_id: int) -> dict | None:
    row = conn.execute(
        """SELECT fixture_id, competition_key, home_team, away_team, kickoff_utc, status, season
           FROM fixtures WHERE fixture_id=? AND is_placeholder=0 LIMIT 1""",
        (int(fixture_id),),
    ).fetchone()
    return dict(row) if row else None


def production_conn():
    settings = get_settings()
    return connect(settings.sqlite_path)
