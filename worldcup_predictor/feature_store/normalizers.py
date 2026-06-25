"""Normalize Sportmonks fixture payloads into feature-store xG records."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.feature_store.models import SportmonksXgRecord
from worldcup_predictor.feature_store.xg_discovery.xg_fixture_parser import (
    classify_metric_key,
    coerce_fixture_xg_keys as _coerce_fixture_xg_keys,
    expected_rows_from_fixture as _expected_rows_from_fixture,
)
from worldcup_predictor.providers.sportmonks_xg_extraction import (
    _participant_side_map,
    _type_id_from_row,
    _type_label_from_row,
    _value_from_row,
    parse_sportmonks_xg_match,
)

_XG_TYPE_IDS = frozenset({5304, 5305, 7939, 7940, 7941, 7942, 7943, 7944, 7945, 9684, 9685, 9686, 9687})

_XG_METRIC_HINTS = frozenset(
    {
        "xg",
        "xga",
        "xgot",
        "npxg",
        "xpts",
        "xg_penalties",
        "xg_free_kicks",
        "xg_corners",
        "xg_set_play",
        "xg_open_play",
        "xgd",
        "shooting_performance",
        "xg_prevented",
    }
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def classify_metric_key(row: dict[str, Any]) -> str | None:
    """Canonical metric_key — delegates to shared xg_fixture_parser."""
    from worldcup_predictor.feature_store.xg_discovery.xg_fixture_parser import classify_metric_key as _cmk

    return _cmk(row)


def _rows_from_xg_block(block: Any) -> list[dict[str, Any]]:
    from worldcup_predictor.feature_store.xg_discovery.xg_fixture_parser import _rows_from_xg_block as _r

    return _r(block)


def _block_has_expected_goals_semantics(block: Any) -> bool:
    from worldcup_predictor.feature_store.xg_discovery.xg_fixture_parser import block_has_expected_goals_semantics

    return block_has_expected_goals_semantics(block)


def _coerce_fixture_xg_keys(raw: dict[str, Any]) -> dict[str, Any]:
    from worldcup_predictor.feature_store.xg_discovery.xg_fixture_parser import coerce_fixture_xg_keys

    return coerce_fixture_xg_keys(raw)


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
        from datetime import datetime as dt

        return dt.fromisoformat(str(text).replace(" ", "T")).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def normalize_fixture_xg_records(
    raw: dict[str, Any],
    *,
    sportmonks_fixture_id: int | None = None,
    fixture_id: int | None = None,
    source: str = "sportmonks_fixture",
    raw_reference: str | None = None,
    captured_at: datetime | None = None,
) -> list[SportmonksXgRecord]:
    """Expand a Sportmonks fixture `data` object into normalized xG records."""
    if not raw:
        return []

    raw = _coerce_fixture_xg_keys(raw)
    sm_fid = int(sportmonks_fixture_id or raw.get("id") or 0)
    if sm_fid <= 0:
        return []

    captured = captured_at or _utc_now()
    league_id = raw.get("league_id")
    season_id = raw.get("season_id")
    home_team_id, away_team_id = _team_ids_from_fixture(raw)
    id_to_side = _participant_side_map(raw)

    try:
        league_id = int(league_id) if league_id is not None else None
    except (TypeError, ValueError):
        league_id = None
    try:
        season_id = int(season_id) if season_id is not None else None
    except (TypeError, ValueError):
        season_id = None

    records: list[SportmonksXgRecord] = []
    base = {
        "sportmonks_fixture_id": sm_fid,
        "fixture_id": fixture_id,
        "league_id": league_id,
        "season_id": season_id,
        "home_team_id": home_team_id,
        "away_team_id": away_team_id,
        "captured_at": captured,
        "source": source,
        "raw_reference": raw_reference,
    }

    for row in _expected_rows_from_fixture(raw):
        if not isinstance(row, dict):
            continue
        metric = classify_metric_key(row)
        val = _value_from_row(row)
        type_block = row.get("type") if isinstance(row.get("type"), dict) else {}
        type_name_raw = str(type_block.get("name") or type_block.get("developer_name") or "")
        if metric is None or val is None:
            continue
        if metric not in _XG_METRIC_HINTS:
            continue

        loc = str(row.get("location") or "").lower()
        participant_id = row.get("participant_id")
        try:
            pid = int(participant_id) if participant_id is not None else None
        except (TypeError, ValueError):
            pid = None
        if not loc and pid is not None:
            loc = id_to_side.get(pid, "")

        type_block = row.get("type") if isinstance(row.get("type"), dict) else {}
        type_name = str(type_block.get("name") or type_block.get("developer_name") or metric)

        records.append(
            SportmonksXgRecord(
                **base,
                participant_id=pid,
                record_type="team_metric" if pid else "fixture_xg",
                metric_key=metric,
                type_id=_type_id_from_row(row),
                type_name=type_name,
                location=loc or None,
                xg_value=float(val),
                metadata={"row_id": row.get("id")},
            )
        )

    parsed = parse_sportmonks_xg_match(raw)
    team = parsed.get("team") or {}
    team_metrics = team.get("team_metrics") or {}
    for side in ("home", "away"):
        participant_id = home_team_id if side == "home" else away_team_id
        for metric_key, val in (team_metrics.get(side) or {}).items():
            if val is None or str(metric_key) not in _XG_METRIC_HINTS:
                continue
            records.append(
                SportmonksXgRecord(
                    **base,
                    participant_id=participant_id,
                    record_type="team_xg",
                    metric_key=str(metric_key),
                    location=side,
                    xg_value=float(val),
                    metadata={"derived_from": "parse_sportmonks_xg_match"},
                )
            )

    player_summary = parsed.get("player_xg_summary") or {}
    for player in player_summary.get("players") or []:
        if not isinstance(player, dict):
            continue
        metrics = player.get("metrics") or {}
        player_id = player.get("player_id")
        try:
            pl_id = int(player_id) if player_id is not None else None
        except (TypeError, ValueError):
            pl_id = None
        team_side = player.get("team_side")
        participant_id = home_team_id if team_side == "home" else away_team_id if team_side == "away" else None
        for metric_key, val in metrics.items():
            if val is None or str(metric_key) not in _XG_METRIC_HINTS:
                continue
            records.append(
                SportmonksXgRecord(
                    **base,
                    participant_id=participant_id,
                    player_id=pl_id,
                    record_type="player_xg",
                    metric_key=str(metric_key),
                    location=team_side,
                    xg_value=float(val),
                    metadata={"player_name": player.get("player_name")},
                )
            )

    return _dedupe_records(records)


def normalize_expected_endpoint_rows(
    rows: list[dict[str, Any]],
    *,
    sportmonks_fixture_id: int,
    league_id: int | None = None,
    season_id: int | None = None,
    source: str = "sportmonks_expected_endpoint",
    raw_reference: str | None = None,
) -> list[SportmonksXgRecord]:
    """Normalize rows from GET /expected/fixtures."""
    captured = _utc_now()
    records: list[SportmonksXgRecord] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        metric = classify_metric_key(row)
        val = _value_from_row(row)
        if metric is None or val is None or metric not in _XG_METRIC_HINTS:
            continue
        participant_id = row.get("participant_id")
        try:
            pid = int(participant_id) if participant_id is not None else None
        except (TypeError, ValueError):
            pid = None
        type_block = row.get("type") if isinstance(row.get("type"), dict) else {}
        records.append(
            SportmonksXgRecord(
                sportmonks_fixture_id=sportmonks_fixture_id,
                league_id=league_id,
                season_id=season_id,
                participant_id=pid,
                record_type="team_metric",
                metric_key=metric,
                type_id=_type_id_from_row(row),
                type_name=str(type_block.get("name") or metric),
                location=str(row.get("location") or "").lower() or None,
                xg_value=float(val),
                captured_at=captured,
                source=source,
                raw_reference=raw_reference,
            )
        )
    return _dedupe_records(records)


def _dedupe_records(records: list[SportmonksXgRecord]) -> list[SportmonksXgRecord]:
    seen: set[tuple[Any, ...]] = set()
    out: list[SportmonksXgRecord] = []
    for rec in records:
        key = (
            rec.sportmonks_fixture_id,
            rec.record_type,
            rec.metric_key,
            rec.participant_id,
            rec.player_id,
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(rec)
    return out


def build_fixture_summary_from_records(
    records: list[SportmonksXgRecord],
    *,
    sportmonks_fixture_id: int,
    match_started_at: datetime | None = None,
    rolling_features: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build fixture-level xG summary dict from normalized records."""
    if not records:
        return {"sportmonks_fixture_id": sportmonks_fixture_id}

    sample = records[0]
    home_xg = away_xg = home_xga = away_xga = home_npxg = away_npxg = None

    for rec in records:
        if rec.record_type not in ("team_xg", "team_metric", "fixture_xg"):
            continue
        if rec.metric_key == "xg":
            if rec.location == "home" or rec.participant_id == sample.home_team_id:
                home_xg = rec.xg_value
            elif rec.location == "away" or rec.participant_id == sample.away_team_id:
                away_xg = rec.xg_value
        elif rec.metric_key in ("xga", "xg_against"):
            if rec.location == "home" or rec.participant_id == sample.home_team_id:
                home_xga = rec.xg_value
            elif rec.location == "away" or rec.participant_id == sample.away_team_id:
                away_xga = rec.xg_value
        elif rec.metric_key == "npxg":
            if rec.location == "home" or rec.participant_id == sample.home_team_id:
                home_npxg = rec.xg_value
            elif rec.location == "away" or rec.participant_id == sample.away_team_id:
                away_npxg = rec.xg_value

    xg_total = None
    xg_diff = None
    if home_xg is not None or away_xg is not None:
        h = home_xg or 0.0
        a = away_xg or 0.0
        xg_total = round(h + a, 4)
        xg_diff = round(h - a, 4)

    rolling = rolling_features or {}
    home_recent_xg = rolling.get("home_team_recent_xg")
    away_recent_xg = rolling.get("away_team_recent_xg")
    home_recent_xga = rolling.get("home_team_recent_xga")
    away_recent_xga = rolling.get("away_team_recent_xga")

    attack_diff = None
    defense_diff = None
    momentum_diff = None
    if home_recent_xg is not None and away_recent_xg is not None:
        attack_diff = round(float(home_recent_xg) - float(away_recent_xg), 4)
    if home_recent_xga is not None and away_recent_xga is not None:
        defense_diff = round(float(away_recent_xga) - float(home_recent_xga), 4)
    if attack_diff is not None and defense_diff is not None:
        momentum_diff = round(attack_diff + defense_diff, 4)

    return {
        "sportmonks_fixture_id": sportmonks_fixture_id,
        "fixture_id": sample.fixture_id,
        "league_id": sample.league_id,
        "season_id": sample.season_id,
        "home_team_id": sample.home_team_id,
        "away_team_id": sample.away_team_id,
        "match_started_at": match_started_at,
        "home_xg": home_xg,
        "away_xg": away_xg,
        "home_xga": home_xga,
        "away_xga": away_xga,
        "home_npxg": home_npxg,
        "away_npxg": away_npxg,
        "xg_total": xg_total,
        "xg_difference": xg_diff,
        "home_team_recent_xg": home_recent_xg,
        "away_team_recent_xg": away_recent_xg,
        "home_team_recent_xga": home_recent_xga,
        "away_team_recent_xga": away_recent_xga,
        "attack_difference": attack_diff,
        "defense_difference": defense_diff,
        "momentum_difference": momentum_diff,
        "aggregation_window": rolling.get("window"),
        "features_json": rolling.get("features_json") or {},
        "captured_at": sample.captured_at,
        "source": sample.source,
    }
