"""STEP 1 — audit Sportmonks league coverage for UEFA club plan."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.egie.uefa_club.config import UEFA_CLUB_LEAGUES
from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider

_FINISHED_STATE_IDS = {5, 7, 8}  # FT / AET / PEN common Sportmonks state ids


def _participant_names(item: dict[str, Any]) -> tuple[str, str]:
    home = away = ""
    for p in item.get("participants") or []:
        if not isinstance(p, dict):
            continue
        loc = str((p.get("meta") or {}).get("location") or "").lower()
        name = str(p.get("name") or "")
        if loc == "home":
            home = name
        elif loc == "away":
            away = name
    return home, away


def audit_uefa_league_coverage(
    *,
    settings: Settings | None = None,
    max_pages_per_league: int = 3,
    per_page: int = 50,
) -> dict[str, Any]:
    settings = settings or get_settings()
    provider = SportmonksProvider(settings)
    api_calls = 0
    leagues_out: list[dict[str, Any]] = []

    for league in UEFA_CLUB_LEAGUES:
        # League metadata
        st_meta, meta_payload, meta_err = provider.safe_get(f"/leagues/{league.sportmonks_league_id}")
        api_calls += 1
        league_data = (meta_payload or {}).get("data") if isinstance(meta_payload, dict) else None
        seasons: list[dict[str, Any]] = []
        if isinstance(league_data, dict):
            for s in league_data.get("seasons") or []:
                if isinstance(s, dict):
                    seasons.append(
                        {
                            "season_id": s.get("id"),
                            "name": s.get("name"),
                            "finished": s.get("finished"),
                            "is_current": s.get("is_current"),
                        }
                    )

        fixtures: list[dict[str, Any]] = []
        accessible = st_meta == 200 and isinstance(league_data, dict)
        for page in range(1, max_pages_per_league + 1):
            st, payload, err = provider.safe_get(
                "/fixtures",
                params={
                    "filters": f"fixtureLeagues:{league.sportmonks_league_id}",
                    "include": "participants;state",
                    "per_page": per_page,
                    "page": page,
                },
            )
            api_calls += 1
            data = (payload or {}).get("data") if isinstance(payload, dict) else None
            if not isinstance(data, list) or not data:
                break
            for row in data:
                if not isinstance(row, dict):
                    continue
                home, away = _participant_names(row)
                fixtures.append(
                    {
                        "sportmonks_fixture_id": row.get("id"),
                        "season_id": row.get("season_id"),
                        "state_id": row.get("state_id"),
                        "starting_at": row.get("starting_at"),
                        "home_team": home,
                        "away_team": away,
                        "name": row.get("name"),
                    }
                )
            if len(data) < per_page:
                break

        finished = [f for f in fixtures if int(f.get("state_id") or 0) in _FINISHED_STATE_IDS]
        season_ids = sorted({int(f["season_id"]) for f in fixtures if f.get("season_id")})

        leagues_out.append(
            {
                "competition_key": league.key,
                "league_name": league.name,
                "league_id": league.sportmonks_league_id,
                "priority": league.priority,
                "league_endpoint_accessible": accessible,
                "league_meta_status": st_meta,
                "league_meta_error": meta_err,
                "seasons_listed": seasons[:20],
                "season_ids_observed_in_fixtures": season_ids,
                "fixtures_sampled": len(fixtures),
                "finished_fixtures_sampled": len(finished),
                "api_message": (meta_payload or {}).get("message") if isinstance(meta_payload, dict) else None,
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "plan_note": "Euro Club Tournaments — live probe",
        "api_calls_made": api_calls,
        "leagues": leagues_out,
        "total_fixtures_sampled": sum(lg["fixtures_sampled"] for lg in leagues_out),
    }
