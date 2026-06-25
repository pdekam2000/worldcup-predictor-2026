"""Normalize Sportmonks fixture payloads into player match-stat records."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.feature_store.player_store.models import PlayerMatchStatRecord

_STARTER_TYPE = 11
_BENCH_TYPE = 12

_POSITION_GROUPS = {
    1: "GK",
    2: "DEF",
    3: "MID",
    4: "FWD",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_started_at(raw: dict[str, Any]) -> datetime | None:
    text = raw.get("starting_at")
    if not text:
        return None
    try:
        return datetime.fromisoformat(str(text).replace(" ", "T")).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _detail_value(det: dict[str, Any]) -> float | None:
    val = det.get("value")
    if val is None and isinstance(det.get("data"), dict):
        val = det["data"].get("value")
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _detail_name(det: dict[str, Any]) -> str:
    return str((det.get("type") or {}).get("name") or "").strip().lower()


def position_group_from_formation_position(formation_position: int | None) -> str | None:
    if formation_position is None:
        return None
    try:
        pos = int(formation_position)
    except (TypeError, ValueError):
        return None
    if pos == 1:
        return "GK"
    if pos <= 5:
        return "DEF"
    if pos <= 8:
        return "MID"
    return "FWD"


def extract_lineup_context(raw: dict[str, Any]) -> dict[str, Any]:
    """Fixture-level lineup summary used for rolling feature enrichment."""
    lineups = [lu for lu in (raw.get("lineups") or []) if isinstance(lu, dict)]
    starters: list[int] = []
    bench: list[int] = []
    goalkeeper_id: int | None = None
    captain_id: int | None = None

    for lu in lineups:
        try:
            pid = int(lu.get("player_id") or 0)
        except (TypeError, ValueError):
            continue
        if pid <= 0:
            continue
        type_id = int(lu.get("type_id") or 0)
        if type_id == _STARTER_TYPE:
            starters.append(pid)
        elif type_id == _BENCH_TYPE:
            bench.append(pid)
        if int(lu.get("formation_position") or 0) == 1:
            goalkeeper_id = pid
        for det in lu.get("details") or []:
            if not isinstance(det, dict):
                continue
            if "captain" in _detail_name(det):
                captain_id = pid

    formations = raw.get("formations") or []
    formation_str: str | None = None
    if isinstance(formations, list):
        parts = [str(f.get("formation") or "").strip() for f in formations if isinstance(f, dict)]
        parts = [p for p in parts if p]
        if parts:
            formation_str = " vs ".join(parts[:2])

    xi_ok = len(starters) >= 20
    bench_ok = len(bench) >= 5
    formation_ok = formation_str is not None
    quality = 0.0
    if xi_ok:
        quality += 0.5
    if bench_ok:
        quality += 0.2
    if formation_ok:
        quality += 0.2
    if goalkeeper_id:
        quality += 0.1

    return {
        "starting_xi": starters,
        "bench": bench,
        "formation": formation_str,
        "goalkeeper_player_id": goalkeeper_id,
        "captain_player_id": captain_id,
        "lineup_available": xi_ok,
        "lineup_quality_score": round(min(1.0, quality), 3),
    }


def _extract_xg_xa(lu: dict[str, Any]) -> tuple[float | None, float | None]:
    xg = xa = None
    blocks: list[Any] = []
    for key in ("xGLineup", "xgLineup", "xglineup"):
        block = lu.get(key)
        if isinstance(block, list):
            blocks.extend(block)
    for row in blocks:
        if not isinstance(row, dict):
            continue
        tname = str((row.get("type") or {}).get("name") or row.get("type_id") or "").lower()
        dev = str((row.get("type") or {}).get("developer_name") or "").upper()
        val = row.get("value")
        if val is None and isinstance(row.get("data"), dict):
            val = row["data"].get("value")
        try:
            num = float(val) if val is not None else None
        except (TypeError, ValueError):
            num = None
        if num is None:
            continue
        if dev == "EXPECTED_GOALS" or "expected goals" in tname or tname == "xg":
            xg = num
        elif "assist" in tname or dev == "EXPECTED_ASSISTS" or tname == "xa":
            xa = num
    return xg, xa


def _parse_lineup_player(
    lu: dict[str, Any],
    *,
    sportmonks_fixture_id: int,
    league_id: int | None,
    season_id: int | None,
    match_date: datetime | None,
    source: str,
    raw_reference: str | None,
    captured_at: datetime,
) -> PlayerMatchStatRecord | None:
    try:
        player_id = int(lu.get("player_id") or 0)
    except (TypeError, ValueError):
        return None
    if player_id <= 0:
        return None

    type_id = int(lu.get("type_id") or 0)
    starter = type_id == _STARTER_TYPE
    formation_pos = lu.get("formation_position")
    try:
        formation_pos_int = int(formation_pos) if formation_pos is not None else None
    except (TypeError, ValueError):
        formation_pos_int = None

    minutes = goals = assists = shots = shots_on_target = 0
    yellow_cards = red_cards = 0
    rating: float | None = None
    captain = False

    for det in lu.get("details") or []:
        if not isinstance(det, dict):
            continue
        name = _detail_name(det)
        val = _detail_value(det)
        if val is None:
            continue
        if "minute" in name:
            minutes = int(val)
        elif name == "goals":
            goals = int(val)
        elif name == "assists":
            assists = int(val)
        elif name == "shots on target" or name == "shots on goal":
            shots_on_target = int(val)
        elif name == "shots":
            shots = int(val)
        elif "yellow" in name:
            yellow_cards = int(val)
        elif "red" in name and "card" in name:
            red_cards = int(val)
        elif "rating" in name:
            rating = round(val, 3)
        elif "captain" in name:
            captain = True
        elif "expected goal" in name or name == "xg":
            pass  # handled via xGLineup

    xg, xa = _extract_xg_xa(lu)

    player_name = lu.get("player_name")
    if not player_name and isinstance(lu.get("player"), dict):
        player_name = lu["player"].get("display_name") or lu["player"].get("name")

    try:
        team_id = int(lu.get("team_id") or 0) or None
    except (TypeError, ValueError):
        team_id = None

    position = position_group_from_formation_position(formation_pos_int)

    return PlayerMatchStatRecord(
        sportmonks_fixture_id=sportmonks_fixture_id,
        player_id=player_id,
        captured_at=captured_at,
        source=source,
        fixture_id=int(lu.get("fixture_id") or sportmonks_fixture_id),
        player_name=str(player_name) if player_name else None,
        team_id=team_id,
        position=position,
        starter=starter,
        captain=captain,
        minutes=minutes,
        goals=goals,
        assists=assists,
        shots=shots,
        shots_on_target=shots_on_target,
        rating=rating,
        xg=round(xg, 4) if xg is not None else None,
        xa=round(xa, 4) if xa is not None else None,
        yellow_cards=yellow_cards,
        red_cards=red_cards,
        season_id=season_id,
        league_id=league_id,
        match_date=match_date,
        raw_reference=raw_reference,
        metadata={
            "type_id": type_id,
            "formation_position": formation_pos_int,
            "jersey_number": lu.get("jersey_number"),
        },
    )


def normalize_fixture_player_stats(
    raw: dict[str, Any],
    *,
    sportmonks_fixture_id: int,
    source: str = "sportmonks_cache",
    raw_reference: str | None = None,
    captured_at: datetime | None = None,
) -> list[PlayerMatchStatRecord]:
    """Extract per-player match stats from Sportmonks fixture lineups."""
    captured = captured_at or _utc_now()
    lineups = [lu for lu in (raw.get("lineups") or []) if isinstance(lu, dict)]
    if not lineups:
        return []

    try:
        league_id = int(raw.get("league_id") or 0) or None
    except (TypeError, ValueError):
        league_id = None
    try:
        season_id = int(raw.get("season_id") or 0) or None
    except (TypeError, ValueError):
        season_id = None
    match_date = _parse_started_at(raw)

    seen: set[int] = set()
    records: list[PlayerMatchStatRecord] = []
    for lu in lineups:
        rec = _parse_lineup_player(
            lu,
            sportmonks_fixture_id=sportmonks_fixture_id,
            league_id=league_id,
            season_id=season_id,
            match_date=match_date,
            source=source,
            raw_reference=raw_reference,
            captured_at=captured,
        )
        if rec is None or rec.player_id in seen:
            continue
        seen.add(rec.player_id)
        records.append(rec)
    return records
