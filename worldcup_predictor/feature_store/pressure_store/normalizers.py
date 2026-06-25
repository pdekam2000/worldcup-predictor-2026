"""Normalize Sportmonks fixture payloads into pressure feature-store records."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.feature_store.pressure_store.models import SportmonksPressureRecord

_GOAL_DEVELOPER_NAMES = frozenset({"GOAL", "OWN_GOAL", "PENALTY"})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _team_ids_from_fixture(raw: dict[str, Any]) -> tuple[int | None, int | None]:
    home_id = away_id = None
    for p in raw.get("participants") or []:
        if not isinstance(p, dict):
            continue
        loc = str((p.get("meta") or {}).get("location") or "").lower()
        pid = p.get("id")
        if pid is None:
            continue
        try:
            tid = int(pid)
        except (TypeError, ValueError):
            continue
        if loc == "home":
            home_id = tid
        elif loc == "away":
            away_id = tid
    return home_id, away_id


def _parse_started_at(raw: dict[str, Any]) -> datetime | None:
    text = raw.get("starting_at")
    if not text:
        return None
    try:
        return datetime.fromisoformat(str(text).replace(" ", "T")).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def first_goal_minute_from_events(raw: dict[str, Any]) -> int | None:
    """Return minute of first goal (excluding own goals if labeled separately)."""
    candidates: list[int] = []
    for ev in raw.get("events") or []:
        if not isinstance(ev, dict):
            continue
        t = ev.get("type") or {}
        dev = str(t.get("developer_name") or t.get("name") or "").upper()
        if "GOAL" not in dev:
            continue
        minute = ev.get("minute")
        if minute is None:
            continue
        try:
            candidates.append(int(minute))
        except (TypeError, ValueError):
            continue
    return min(candidates) if candidates else None


def normalize_fixture_pressure_records(
    raw: dict[str, Any],
    *,
    sportmonks_fixture_id: int,
    fixture_id: int | None = None,
    source: str = "sportmonks_fixture",
    raw_reference: str | None = None,
    captured_at: datetime | None = None,
) -> list[SportmonksPressureRecord]:
    """Extract minute-level pressure rows from a Sportmonks fixture payload."""
    captured = captured_at or _utc_now()
    league_id = raw.get("league_id")
    season_id = raw.get("season_id")
    home_id, away_id = _team_ids_from_fixture(raw)

    try:
        league_id = int(league_id) if league_id is not None else None
    except (TypeError, ValueError):
        league_id = None
    try:
        season_id = int(season_id) if season_id is not None else None
    except (TypeError, ValueError):
        season_id = None

    pressure = raw.get("pressure")
    if not isinstance(pressure, list) or not pressure:
        return []

    seen: set[tuple[int, int, int]] = set()
    records: list[SportmonksPressureRecord] = []

    for row in pressure:
        if not isinstance(row, dict):
            continue
        try:
            row_id = int(row.get("id") or 0)
            participant_id = int(row.get("participant_id") or 0)
            minute = int(row.get("minute") if row.get("minute") is not None else -1)
            pressure_val = float(row.get("pressure") if row.get("pressure") is not None else 0.0)
        except (TypeError, ValueError):
            continue
        if row_id <= 0 or participant_id <= 0 or minute < 0:
            continue

        key = (sportmonks_fixture_id, participant_id, minute)
        if key in seen:
            continue
        seen.add(key)

        team_id = participant_id
        records.append(
            SportmonksPressureRecord(
                sportmonks_fixture_id=sportmonks_fixture_id,
                pressure_row_id=row_id,
                participant_id=participant_id,
                team_id=team_id,
                minute=minute,
                pressure_value=round(pressure_val, 4),
                captured_at=captured,
                source=source,
                fixture_id=fixture_id,
                league_id=league_id,
                season_id=season_id,
                raw_reference=raw_reference,
                metadata={
                    "home_team_id": home_id,
                    "away_team_id": away_id,
                    "fixture_row_id": row.get("fixture_id"),
                },
            )
        )

    return records


def build_fixture_pressure_summary(
    records: list[SportmonksPressureRecord],
    *,
    sportmonks_fixture_id: int,
    raw: dict[str, Any] | None = None,
    match_started_at: datetime | None = None,
    aggregation_features: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build fixture summary dict from pressure records."""
    from worldcup_predictor.feature_store.pressure_store.aggregations import compute_fixture_pressure_features

    home_id = away_id = None
    if raw:
        home_id, away_id = _team_ids_from_fixture(raw)
    elif records:
        meta = records[0].metadata or {}
        home_id = meta.get("home_team_id")
        away_id = meta.get("away_team_id")

    first_goal = first_goal_minute_from_events(raw or {}) if raw else None
    minutes = {r.minute for r in records}

    features = aggregation_features
    if features is None and records and home_id and away_id:
        features = compute_fixture_pressure_features(
            records,
            home_participant_id=int(home_id),
            away_participant_id=int(away_id),
            first_goal_minute=first_goal,
        )

    league_id = records[0].league_id if records else (raw or {}).get("league_id")
    season_id = records[0].season_id if records else (raw or {}).get("season_id")
    fixture_id = records[0].fixture_id if records else None
    source = records[0].source if records else "sportmonks_fixture"
    captured = records[0].captured_at if records else _utc_now()

    return {
        "sportmonks_fixture_id": sportmonks_fixture_id,
        "fixture_id": fixture_id,
        "league_id": league_id,
        "season_id": season_id,
        "home_team_id": home_id,
        "away_team_id": away_id,
        "match_started_at": match_started_at or (_parse_started_at(raw) if raw else None),
        "pressure_row_count": len(records),
        "unique_minutes": len(minutes),
        "first_goal_minute": first_goal,
        "features_json": features or {},
        "captured_at": captured,
        "source": source,
    }
