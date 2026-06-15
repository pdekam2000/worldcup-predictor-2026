from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.clients.api_response import ApiCallResult
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.data_import.models import ImportResult, ImportStats, ImportedMatchRow

logger = logging.getLogger(__name__)

WORLD_CUP_LEAGUE_ID = 1
FINISHED_STATUSES = frozenset({"FT", "AET", "PEN"})


class ApiFootballHistoricalImporter:
    """Import real historical fixtures from API-Football into backtest CSV shape."""

    def __init__(
        self,
        settings: Settings | None = None,
        api_client: ApiFootballClient | None = None,
        *,
        fetch_odds: bool = True,
    ) -> None:
        self._settings = settings or get_settings()
        self._api = api_client or ApiFootballClient(self._settings)
        self._fetch_odds = fetch_odds
        self._stats = ImportStats()

    @property
    def is_configured(self) -> bool:
        return self._api.is_configured

    def import_fixtures(
        self,
        league_id: int,
        season: int,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> ImportResult:
        if not self.is_configured:
            return _api_key_required_result(
                requested=[f"league_id={league_id}"],
                seasons=[season],
            )

        result = ImportResult(
            requested_competitions=[f"league_id={league_id}"],
            requested_seasons=[season],
            source_label="api-football",
        )
        result.stats = self._stats

        api_result = self._api.get_historical_fixtures(
            league_id=league_id,
            season=season,
            from_date=from_date,
            to_date=to_date,
        )
        self._track_api_call(api_result)
        if not api_result.ok or not isinstance(api_result.data, list):
            result.api_errors.append(
                api_result.error or f"No fixtures returned for league {league_id} season {season}"
            )
            result.message = "Import failed — no fixture data from API-Football."
            return result

        competition_name = f"League {league_id} {season}"
        if league_id == WORLD_CUP_LEAGUE_ID:
            competition_name = f"FIFA World Cup {season}"

        for item in api_result.data:
            row = self._parse_fixture_item(item, competition_name)
            if row is None:
                result.skipped_count += 1
                continue
            if self._fetch_odds:
                self._attach_odds(row)
            result.rows.append(row)
            result.record_missing(row.missing_fields)

        result.imported_count = len(result.rows)
        result.success = result.imported_count > 0
        result.message = f"Imported {result.imported_count} fixtures (skipped {result.skipped_count})."
        result.data_quality_notes = _quality_notes(result)
        return result

    def import_world_cup_history(self, seasons: list[int] | None = None) -> ImportResult:
        active_seasons = seasons or [2014, 2018, 2022]
        if not self.is_configured:
            return _api_key_required_result(
                requested=["FIFA World Cup"],
                seasons=active_seasons,
            )

        combined = ImportResult(
            requested_competitions=["FIFA World Cup"],
            requested_seasons=active_seasons,
            source_label="api-football",
            stats=self._stats,
        )

        for season in active_seasons:
            partial = self.import_fixtures(league_id=WORLD_CUP_LEAGUE_ID, season=season)
            combined.rows.extend(partial.rows)
            combined.skipped_count += partial.skipped_count
            combined.api_errors.extend(partial.api_errors)
            for key, count in partial.missing_fields_summary.items():
                combined.missing_fields_summary[key] = (
                    combined.missing_fields_summary.get(key, 0) + count
                )

        combined.rows = _dedupe_rows(combined.rows)
        combined.imported_count = len(combined.rows)
        combined.success = combined.imported_count > 0
        combined.message = (
            f"World Cup import: {combined.imported_count} fixtures "
            f"from seasons {active_seasons} (skipped {combined.skipped_count})."
        )
        combined.data_quality_notes = _quality_notes(combined)
        return combined

    def import_international_matches(
        self,
        team_ids: list[int] | None = None,
        seasons: list[int] | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> ImportResult:
        active_teams = team_ids or []
        active_seasons = seasons or []
        if not self.is_configured:
            return _api_key_required_result(
                requested=[f"teams={active_teams}"],
                seasons=active_seasons,
            )
        if not active_teams or not active_seasons:
            result = ImportResult(
                requested_competitions=[f"teams={active_teams}"],
                requested_seasons=active_seasons,
                message="team_ids and seasons are required for international import.",
            )
            result.api_errors.append("Missing team_ids or seasons.")
            return result

        combined = ImportResult(
            requested_competitions=[f"international teams={active_teams}"],
            requested_seasons=active_seasons,
            source_label="api-football",
            stats=self._stats,
        )

        for team_id in active_teams:
            for season in active_seasons:
                api_result = self._api.get_historical_fixtures(
                    team_id=team_id,
                    season=season,
                    from_date=from_date,
                    to_date=to_date,
                )
                self._track_api_call(api_result)
                if not api_result.ok or not isinstance(api_result.data, list):
                    combined.api_errors.append(
                        api_result.error or f"No fixtures for team {team_id} season {season}"
                    )
                    continue

                for item in api_result.data:
                    league = item.get("league", {})
                    competition_name = league.get("name") or f"International {season}"
                    row = self._parse_fixture_item(item, str(competition_name))
                    if row is None:
                        combined.skipped_count += 1
                        continue
                    if self._fetch_odds:
                        self._attach_odds(row)
                    combined.rows.append(row)
                    combined.record_missing(row.missing_fields)

        combined.rows = _dedupe_rows(combined.rows)
        combined.imported_count = len(combined.rows)
        combined.success = combined.imported_count > 0
        combined.message = f"International import: {combined.imported_count} fixtures."
        combined.data_quality_notes = _quality_notes(combined)
        return combined

    def _track_api_call(self, result: ApiCallResult) -> None:
        if result.from_cache:
            self._stats.cache_hits += 1
        elif result.source == "live":
            self._stats.live_requests += 1

    def _parse_fixture_item(
        self,
        item: dict[str, Any],
        competition_name: str,
    ) -> ImportedMatchRow | None:
        fixture = item.get("fixture") or {}
        teams = item.get("teams") or {}
        league = item.get("league") or {}
        goals = item.get("goals") or {}
        score = item.get("score") or {}

        status = (fixture.get("status") or {}).get("short", "")
        if status not in FINISHED_STATUSES:
            return None

        home_goals = goals.get("home")
        away_goals = goals.get("away")
        if home_goals is None or away_goals is None:
            return None

        try:
            fixture_id = int(fixture.get("id", 0))
            if fixture_id <= 0:
                return None
        except (TypeError, ValueError):
            return None

        kickoff_raw = fixture.get("date", "")
        try:
            kickoff = datetime.fromisoformat(str(kickoff_raw).replace("Z", "+00:00"))
        except ValueError:
            return None

        venue_data = fixture.get("venue") or {}
        venue = venue_data.get("name") or "Unknown"
        referee_data = fixture.get("referee")
        referee = _parse_referee(referee_data)

        halftime = score.get("halftime") or {}
        ht_home = _optional_int(halftime.get("home"))
        ht_away = _optional_int(halftime.get("away"))

        home = teams.get("home") or {}
        away = teams.get("away") or {}
        missing: list[str] = []
        if ht_home is None or ht_away is None:
            missing.append("halftime_scores")
        if not referee:
            missing.append("referee")

        return ImportedMatchRow(
            fixture_id=fixture_id,
            date=kickoff.replace(tzinfo=None),
            competition=league.get("name") or competition_name,
            round=str(league.get("round") or "Unknown"),
            home_team=str(home.get("name") or "Unknown"),
            away_team=str(away.get("name") or "Unknown"),
            home_goals=int(home_goals),
            away_goals=int(away_goals),
            halftime_home_goals=ht_home,
            halftime_away_goals=ht_away,
            venue=venue,
            referee=referee,
            source="api-football",
            missing_fields=missing,
        )

    def _attach_odds(self, row: ImportedMatchRow) -> None:
        odds_result = self._api.get_odds(row.fixture_id)
        self._track_api_call(odds_result)
        if not odds_result.ok or not odds_result.data:
            row.missing_fields.extend(["odds_home", "odds_draw", "odds_away", "over_2_5_odds", "under_2_5_odds"])
            self._stats.odds_missing += 1
            return

        parsed = _parse_odds_payload(odds_result.data)
        if parsed["odds_home"] is not None:
            row.odds_home = parsed["odds_home"]
            row.odds_draw = parsed["odds_draw"]
            row.odds_away = parsed["odds_away"]
            row.over_2_5_odds = parsed["over_2_5_odds"]
            row.under_2_5_odds = parsed["under_2_5_odds"]
            self._stats.odds_fetched += 1
        else:
            row.missing_fields.extend(["odds_home", "odds_draw", "odds_away", "over_2_5_odds", "under_2_5_odds"])
            self._stats.odds_missing += 1


def _parse_odds_payload(data: list[dict[str, Any]]) -> dict[str, float | None]:
    result: dict[str, float | None] = {
        "odds_home": None,
        "odds_draw": None,
        "odds_away": None,
        "over_2_5_odds": None,
        "under_2_5_odds": None,
    }
    if not data:
        return result

    bookmakers = data[0].get("bookmakers") or []
    for bookmaker in bookmakers:
        for bet in bookmaker.get("bets", []):
            name = bet.get("name", "")
            if name == "Match Winner" and result["odds_home"] is None:
                for value in bet.get("values", []):
                    label = str(value.get("value", "")).lower()
                    odd = _optional_float(value.get("odd"))
                    if odd is None:
                        continue
                    if label == "home":
                        result["odds_home"] = odd
                    elif label == "draw":
                        result["odds_draw"] = odd
                    elif label == "away":
                        result["odds_away"] = odd
            if "over/under" in name.lower() and "2.5" in name and result["over_2_5_odds"] is None:
                for value in bet.get("values", []):
                    label = str(value.get("value", "")).lower()
                    odd = _optional_float(value.get("odd"))
                    if odd is None:
                        continue
                    if "over" in label:
                        result["over_2_5_odds"] = odd
                    elif "under" in label:
                        result["under_2_5_odds"] = odd
    return result


def _dedupe_rows(rows: list[ImportedMatchRow]) -> list[ImportedMatchRow]:
    seen: dict[int, ImportedMatchRow] = {}
    for row in sorted(rows, key=lambda r: (r.date, r.fixture_id)):
        seen[row.fixture_id] = row
    return list(seen.values())


def _api_key_required_result(
    *,
    requested: list[str],
    seasons: list[int],
) -> ImportResult:
    return ImportResult(
        requested_competitions=requested,
        requested_seasons=seasons,
        success=False,
        message="API_FOOTBALL_KEY is required for historical import. No fake data was created.",
        api_errors=[
            "API_FOOTBALL_KEY not configured — set it in .env to import real historical matches.",
            "Demo data remains at data/historical/worldcup_sample.csv (separate from imported data).",
        ],
        data_quality_notes=[
            "Import aborted — real historical data is never fabricated.",
        ],
    )


def _quality_notes(result: ImportResult) -> list[str]:
    notes = [
        "Source: API-Football (real completed fixtures only).",
        "Historical performance does not guarantee future results.",
    ]
    if result.stats.odds_missing:
        notes.append(
            f"Odds unavailable for {result.stats.odds_missing} fixtures — "
            "historical odds may require API plan access."
        )
    if result.missing_fields_summary.get("halftime_scores"):
        notes.append("Some matches missing halftime scores in API payload.")
    return notes


def _parse_referee(referee_data: Any) -> str | None:
    if referee_data is None:
        return None
    if isinstance(referee_data, str):
        return referee_data.strip() or None
    if isinstance(referee_data, dict):
        return referee_data.get("name") or None
    return str(referee_data)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
