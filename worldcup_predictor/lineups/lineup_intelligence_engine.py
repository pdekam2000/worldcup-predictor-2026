"""Lineup Intelligence V2 — analyze official lineups, rotations, and risk flags."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.lineups.models import (
    LineupIntelligenceResult,
    PredictionImpact,
    TeamLineupSide,
)

_OFFICIAL_STATUSES = frozenset({"1H", "2H", "HT", "FT", "AET", "PEN", "LIVE", "ET", "P", "BT"})
_FINISHED_STATUSES = frozenset({"FT", "AET", "PEN"})


def _safe_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _player_id(entry: dict[str, Any]) -> int | None:
    player = entry.get("player") if isinstance(entry, dict) else None
    if not isinstance(player, dict):
        return None
    try:
        pid = player.get("id")
        return int(pid) if pid is not None else None
    except (TypeError, ValueError):
        return None


def _player_name(entry: dict[str, Any]) -> str | None:
    player = entry.get("player") if isinstance(entry, dict) else None
    if isinstance(player, dict):
        name = player.get("name")
        return str(name) if name else None
    return None


def _player_pos(entry: dict[str, Any]) -> str:
    player = entry.get("player") if isinstance(entry, dict) else None
    if isinstance(player, dict):
        return str(player.get("pos") or "").upper()
    return ""


def _player_number(entry: dict[str, Any]) -> int | None:
    player = entry.get("player") if isinstance(entry, dict) else None
    if not isinstance(player, dict):
        return None
    try:
        num = player.get("number")
        return int(num) if num is not None else None
    except (TypeError, ValueError):
        return None


def _find_team_lineup(
    items: list[dict[str, Any]],
    *,
    team_id: int | None,
    team_name: str,
) -> dict[str, Any] | None:
    for item in items:
        if not isinstance(item, dict):
            continue
        team = item.get("team") or {}
        if team_id is not None and team.get("id") == team_id:
            return item
        if team.get("name") == team_name:
            return item
    return None


def _injury_names(injuries: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for item in injuries:
        if not isinstance(item, dict):
            continue
        player = item.get("player") or {}
        if isinstance(player, dict):
            name = player.get("name")
            if name:
                names.append(str(name))
                continue
        name = item.get("player_name") or item.get("name")
        if name:
            names.append(str(name))
    return names


def _goalkeeper_status(start_xi: list[dict[str, Any]], injured_names: set[str]) -> tuple[str, str | None]:
    gks = [e for e in start_xi if _player_pos(e) == "G"]
    if not gks:
        return "unknown", None
    gk = gks[0]
    name = _player_name(gk)
    number = _player_number(gk)
    if name and name in injured_names:
        return "unknown", name
    if number == 1:
        return "main", name
    if number is not None and number >= 12:
        return "backup", name
    return "unknown", name


def _previous_fixture_id(
    recent_fixtures: list[dict[str, Any]] | None,
    *,
    team_id: int | None,
    current_fixture_id: int | None,
) -> int | None:
    if not recent_fixtures or team_id is None:
        return None
    for row in recent_fixtures:
        if not isinstance(row, dict):
            continue
        fixture = row.get("fixture") or {}
        try:
            fid = int(fixture.get("id") or 0)
        except (TypeError, ValueError):
            continue
        if current_fixture_id and fid == current_fixture_id:
            continue
        status = str((fixture.get("status") or {}).get("short") or "").upper()
        if status in _FINISHED_STATUSES:
            teams = row.get("teams") or {}
            home = teams.get("home") or {}
            away = teams.get("away") or {}
            if home.get("id") == team_id or away.get("id") == team_id:
                return fid
    return None


def _fetch_previous_starting_ids(api_client: Any, fixture_id: int) -> set[int]:
    try:
        result = api_client.get_fixture_lineups(fixture_id)
        if not result.ok:
            return set()
        items = _safe_list(result.data)
        ids: set[int] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            for entry in _safe_list(item.get("startXI")):
                pid = _player_id(entry)
                if pid is not None:
                    ids.add(pid)
        return ids
    except Exception:
        return set()


def _compute_rotation(
    current_xi: list[dict[str, Any]],
    previous_ids: set[int],
) -> int | None:
    if not previous_ids:
        return None
    current_ids = {_player_id(e) for e in current_xi}
    current_ids = {i for i in current_ids if i is not None}
    if not current_ids:
        return None
    changed = len(current_ids - previous_ids)
    return changed


def _analyze_side(
    lineup: dict[str, Any] | None,
    *,
    injuries: list[dict[str, Any]],
    fixture_status: str,
    is_live_source: bool,
    previous_rotation_ids: set[int],
) -> TeamLineupSide:
    start_xi = _safe_list(lineup.get("startXI")) if lineup else []
    subs = _safe_list(lineup.get("substitutes")) if lineup else []
    injured_names = set(_injury_names(injuries))
    missing_key = sorted(injured_names)

    start_count = len(start_xi)
    subs_count = len(subs)
    lineup_available = start_count > 0
    official = fixture_status.upper() in _OFFICIAL_STATUSES
    announced = start_count >= 11 and bool(lineup)

    gk_status, gk_name = _goalkeeper_status(start_xi, injured_names)
    rotation = _compute_rotation(start_xi, previous_rotation_ids)

    risk_flags: list[str] = []
    if not lineup_available:
        risk_flags.append("official_lineup_missing")
    elif not official and not announced:
        risk_flags.append("official_lineup_missing")
    if missing_key:
        risk_flags.append("key_player_missing")
    if gk_status == "backup":
        risk_flags.append("backup_goalkeeper")
    if rotation is not None and rotation >= 5:
        risk_flags.append("many_rotations")
    if lineup_available and subs_count < 5:
        risk_flags.append("weak_bench")

    strength = 50.0
    if lineup_available:
        strength += min(start_count, 11) * 3.0
    if official or announced:
        strength += 10.0
    if is_live_source:
        strength += 5.0
    strength -= len(missing_key) * 8.0
    if gk_status == "backup":
        strength -= 10.0
    if rotation is not None and rotation >= 5:
        strength -= 12.0
    if subs_count >= 7:
        strength += 5.0
    elif subs_count < 5 and lineup_available:
        strength -= 5.0
    strength = _clamp(strength, 0.0, 100.0)

    confidence = 25.0
    if official:
        confidence = 90.0
    elif announced:
        confidence = 70.0 if is_live_source else 55.0
    elif lineup_available:
        confidence = 45.0
    if not is_live_source:
        confidence = min(confidence, 40.0)
    confidence = _clamp(confidence, 0.0, 100.0)

    if confidence < 40:
        risk_flags.append("low_lineup_confidence")

    formation = None
    if lineup:
        formation = lineup.get("formation")
        if formation is not None:
            formation = str(formation)

    return TeamLineupSide(
        lineup_available=lineup_available,
        official_lineup=official or (announced and is_live_source),
        starting_xi_count=start_count,
        substitutes_count=subs_count,
        missing_key_players=missing_key,
        goalkeeper_status=gk_status,  # type: ignore[arg-type]
        goalkeeper_name=gk_name,
        rotation_count=rotation,
        lineup_strength=round(strength, 1),
        confidence=round(confidence, 1),
        risk_flags=sorted(set(risk_flags)),
        formation=formation,
    )


def _build_prediction_impact(home: TeamLineupSide, away: TeamLineupSide) -> PredictionImpact:
    home_adj = 0.0
    away_adj = 0.0
    over_adj = 0.0
    under_adj = 0.0

    if home.official_lineup and home.lineup_strength >= 70:
        home_adj += 2.0
    if away.official_lineup and away.lineup_strength >= 70:
        away_adj += 2.0

    home_adj -= len(home.missing_key_players) * 2.5
    away_adj -= len(away.missing_key_players) * 2.5

    if home.goalkeeper_status == "backup":
        home_adj -= 3.0
        over_adj += 2.0
    if away.goalkeeper_status == "backup":
        away_adj -= 3.0
        over_adj += 2.0

    if home.rotation_count is not None and home.rotation_count >= 5:
        home_adj -= 2.0
        over_adj += 1.5
    if away.rotation_count is not None and away.rotation_count >= 5:
        away_adj -= 2.0
        over_adj += 1.5

    if not home.lineup_available and not away.lineup_available:
        home_adj = away_adj = over_adj = under_adj = 0.0
    elif "official_lineup_missing" in home.risk_flags and "official_lineup_missing" in away.risk_flags:
        home_adj = _clamp(home_adj, -2.0, 2.0)
        away_adj = _clamp(away_adj, -2.0, 2.0)

    under_adj = -over_adj * 0.5 if over_adj else 0.0

    return PredictionImpact(
        home_adjustment=round(_clamp(home_adj, -10.0, 10.0), 1),
        away_adjustment=round(_clamp(away_adj, -10.0, 10.0), 1),
        over25_adjustment=round(_clamp(over_adj, -10.0, 10.0), 1),
        under25_adjustment=round(_clamp(under_adj, -10.0, 10.0), 1),
    )


def _build_summary(home: TeamLineupSide, away: TeamLineupSide) -> str:
    parts: list[str] = []
    if home.lineup_available or away.lineup_available:
        parts.append(
            f"Home XI {home.starting_xi_count}/11 (strength {home.lineup_strength:.0f}), "
            f"Away XI {away.starting_xi_count}/11 (strength {away.lineup_strength:.0f})."
        )
    else:
        parts.append("Official lineups not yet available — lineup intelligence uses safe fallbacks.")
    flags = sorted(set(home.risk_flags + away.risk_flags))
    if flags:
        parts.append(f"Risk flags: {', '.join(flags)}.")
    parts.append("Lineup analysis only — not betting advice.")
    return " ".join(parts)


def build_lineup_intelligence(
    report: Any,
    *,
    api_client: Any | None = None,
) -> LineupIntelligenceResult:
    """Analyze lineup intelligence from a MatchIntelligenceReport — never raises."""
    try:
        return _build_lineup_intelligence_inner(report, api_client=api_client)
    except Exception:
        empty = TeamLineupSide(risk_flags=["official_lineup_missing", "low_lineup_confidence"])
        return LineupIntelligenceResult(
            home=empty,
            away=TeamLineupSide(risk_flags=["official_lineup_missing", "low_lineup_confidence"]),
            summary="Lineup intelligence unavailable — safe fallback applied.",
            prediction_impact=PredictionImpact(),
        )


def _build_lineup_intelligence_inner(
    report: Any,
    *,
    api_client: Any | None,
) -> LineupIntelligenceResult:
    lineups_block = getattr(report, "lineups", None) or {}
    items = _safe_list(lineups_block.get("items"))
    fixture = getattr(report, "fixture", None)
    fixture_status = getattr(fixture, "status", "NS") if fixture else "NS"
    is_live_source = not getattr(report, "is_placeholder", True)

    home_intel = getattr(report, "home_team", None)
    away_intel = getattr(report, "away_team", None)
    home_id = getattr(home_intel, "team_id", None) if home_intel else None
    away_id = getattr(away_intel, "team_id", None) if away_intel else None
    home_name = getattr(home_intel, "team_name", "Home") if home_intel else "Home"
    away_name = getattr(away_intel, "team_name", "Away") if away_intel else "Away"

    home_inj = _safe_list(home_intel.injuries.players if home_intel and home_intel.injuries else [])
    away_inj = _safe_list(away_intel.injuries.players if away_intel and away_intel.injuries else [])

    home_lineup = _find_team_lineup(items, team_id=home_id, team_name=home_name)
    away_lineup = _find_team_lineup(items, team_id=away_id, team_name=away_name)

    current_fid = getattr(report, "fixture_id", None)
    home_prev_ids: set[int] = set()
    away_prev_ids: set[int] = set()
    if api_client is not None:
        home_prev_fid = _previous_fixture_id(
            getattr(report, "home_recent_fixtures", None),
            team_id=home_id,
            current_fixture_id=current_fid,
        )
        away_prev_fid = _previous_fixture_id(
            getattr(report, "away_recent_fixtures", None),
            team_id=away_id,
            current_fixture_id=current_fid,
        )
        if home_prev_fid:
            home_prev_ids = _fetch_previous_starting_ids(api_client, home_prev_fid)
        if away_prev_fid:
            away_prev_ids = _fetch_previous_starting_ids(api_client, away_prev_fid)

    home = _analyze_side(
        home_lineup,
        injuries=home_inj,
        fixture_status=fixture_status,
        is_live_source=is_live_source,
        previous_rotation_ids=home_prev_ids,
    )
    away = _analyze_side(
        away_lineup,
        injuries=away_inj,
        fixture_status=fixture_status,
        is_live_source=is_live_source,
        previous_rotation_ids=away_prev_ids,
    )

    impact = _build_prediction_impact(home, away)
    summary = _build_summary(home, away)

    return LineupIntelligenceResult(
        home=home,
        away=away,
        summary=summary,
        prediction_impact=impact,
    )
