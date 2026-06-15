"""Injury & Suspension Intelligence V2 — API-Football data only."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.injuries.models import (
    InjuryIntelligenceResult,
    InjuryPredictionImpact,
    PositionLosses,
    TeamInjurySide,
    UnavailablePlayer,
)

_IMPORTANCE_CAP = 100.0
_ADJUSTMENT_CAP = 10.0


def _safe_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _impact_band(score: float) -> str:
    if score < 10:
        return "negligible"
    if score < 25:
        return "low"
    if score < 50:
        return "moderate"
    if score < 75:
        return "major"
    return "severe"


def _pos_group(raw: str | None) -> str:
    key = (raw or "").upper().strip()
    if key in {"G", "GK", "GOALKEEPER"}:
        return "Goalkeeper"
    if key in {"D", "DF", "DEF", "DEFENDER"}:
        return "Defender"
    if key in {"M", "MF", "MID", "MIDFIELDER"}:
        return "Midfielder"
    if key in {"F", "FW", "ATT", "FORWARD", "ST", "STRIKER"}:
        return "Forward"
    return "Unknown"


def _classify_status(type_text: str, reason_text: str) -> str:
    combined = f"{type_text} {reason_text}".lower()
    if "suspend" in combined or "red card" in combined or "ban" in combined:
        return "suspended"
    if "doubt" in combined or "question" in combined:
        return "doubtful"
    if "return" in combined or "recover" in combined or "fit" in combined:
        return "expected_return"
    if "missing" in combined or "injur" in combined or "out" in combined:
        return "confirmed"
    return "unknown"


def _starter_map(lineup_items: list[dict[str, Any]], team_id: int | None, team_name: str) -> dict[int, dict[str, Any]]:
    """Map player_id -> {name, pos, in_xi} from lineup data."""
    out: dict[int, dict[str, Any]] = {}
    for item in lineup_items:
        if not isinstance(item, dict):
            continue
        team = item.get("team") or {}
        if team_id is not None and team.get("id") != team_id:
            if team.get("name") != team_name:
                continue
        elif team.get("name") != team_name and team_id is None:
            continue
        for entry in _safe_list(item.get("startXI")) + _safe_list(item.get("substitutes")):
            if not isinstance(entry, dict):
                continue
            player = entry.get("player") or {}
            try:
                pid = int(player.get("id")) if player.get("id") is not None else None
            except (TypeError, ValueError):
                pid = None
            if pid is None:
                continue
            out[pid] = {
                "name": player.get("name"),
                "pos": player.get("pos"),
                "in_xi": entry in _safe_list(item.get("startXI")),
            }
    return out


def _estimate_importance(
    *,
    status: str,
    position_group: str,
    in_starting_xi: bool,
    is_placeholder: bool,
) -> float:
    """Conservative importance — never invent minutes/appearances."""
    score = 35.0
    if status == "suspended":
        score += 18.0
    elif status == "confirmed":
        score += 15.0
    elif status == "doubtful":
        score += 8.0
    elif status == "expected_return":
        score += 5.0

    if in_starting_xi:
        score += 25.0
    elif position_group != "Unknown":
        score += 10.0

    if position_group == "Goalkeeper":
        score += 28.0
    elif position_group == "Forward":
        score += 18.0
    elif position_group == "Defender":
        score += 14.0
    elif position_group == "Midfielder":
        score += 12.0

    if is_placeholder:
        score = min(score, 45.0)
    return round(_clamp(score, 0.0, _IMPORTANCE_CAP), 1)


def _parse_unavailable(
    injuries: list[dict[str, Any]],
    *,
    starter_map: dict[int, dict[str, Any]],
    playing_ids: set[int],
    is_placeholder: bool,
) -> list[UnavailablePlayer]:
    players: list[UnavailablePlayer] = []
    seen: set[int | str] = set()

    for item in injuries:
        if not isinstance(item, dict):
            continue
        player = item.get("player") or {}
        if not isinstance(player, dict):
            continue
        name = str(player.get("name") or "Unknown")
        try:
            pid = int(player.get("id")) if player.get("id") is not None else None
        except (TypeError, ValueError):
            pid = None

        dedupe_key: int | str = pid if pid is not None else name.lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        if pid is not None and pid in playing_ids:
            continue

        ptype = str(player.get("type") or "")
        reason = str(player.get("reason") or "")
        status = _classify_status(ptype, reason)

        lineup_info = starter_map.get(pid or -1, {})
        pos_raw = player.get("pos") or lineup_info.get("pos")
        position_group = _pos_group(str(pos_raw) if pos_raw else None)
        in_xi = bool(lineup_info.get("in_xi"))

        importance = _estimate_importance(
            status=status,
            position_group=position_group,
            in_starting_xi=in_xi,
            is_placeholder=is_placeholder,
        )

        players.append(
            UnavailablePlayer(
                name=name,
                player_id=pid,
                status=status,  # type: ignore[arg-type]
                position_group=position_group,  # type: ignore[arg-type]
                importance_score=importance,
                reason=reason or ptype or None,
            )
        )
    return players


def _position_losses(players: list[UnavailablePlayer]) -> PositionLosses:
    gk = [p for p in players if p.position_group == "Goalkeeper"]
    defs = [p for p in players if p.position_group == "Defender"]
    mids = [p for p in players if p.position_group == "Midfielder"]
    fwds = [p for p in players if p.position_group == "Forward"]

    def _loss(group: list[UnavailablePlayer]) -> float:
        if not group:
            return 0.0
        return round(_clamp(sum(p.importance_score for p in group) / len(group), 0.0, 100.0), 1)

    defensive_vals = [p.importance_score for p in gk + defs]
    defensive = round(_clamp(sum(defensive_vals) / max(len(defensive_vals), 1), 0, 100), 1) if defensive_vals else 0.0

    return PositionLosses(
        defensive_loss=defensive,
        midfield_loss=_loss(mids),
        attacking_loss=_loss(fwds),
    )


def _team_impact_score(players: list[UnavailablePlayer]) -> float:
    if not players:
        return 0.0
    weights = []
    for p in players:
        w = p.importance_score
        if p.status == "doubtful":
            w *= 0.55
        elif p.status == "expected_return":
            w *= 0.35
        weights.append(w)
    raw = sum(weights) / max(len(weights), 1)
    multi_bonus = min(15.0, max(0, len(players) - 1) * 4.0)
    return round(_clamp(raw + multi_bonus, 0.0, 100.0), 1)


def _risk_flags(side: TeamInjurySide, players: list[UnavailablePlayer]) -> list[str]:
    flags: list[str] = []
    if not side.data_available:
        flags.append("low_data_confidence")
        return sorted(set(flags))

    for p in players:
        if p.position_group == "Goalkeeper" and p.importance_score >= 55:
            flags.append("key_goalkeeper_missing")
        if p.position_group == "Defender" and p.importance_score >= 55:
            flags.append("key_defender_missing")
        if p.position_group == "Midfielder" and p.importance_score >= 55:
            flags.append("key_midfielder_missing")
        if p.position_group == "Forward" and p.importance_score >= 55:
            flags.append("key_attacker_missing")
        if "captain" in (p.reason or "").lower():
            flags.append("captain_missing")

    if len(players) >= 3:
        flags.append("multiple_absences")
    if side.suspended_count >= 2:
        flags.append("suspension_cluster")
    if side.injury_impact_score >= 75:
        flags.append("severe_injury_crisis")
    if side.confidence < 40:
        flags.append("low_data_confidence")
    return sorted(set(flags))


def _analyze_team_side(
    injuries: list[dict[str, Any]],
    *,
    lineup_items: list[dict[str, Any]],
    team_id: int | None,
    team_name: str,
    injuries_missing: bool,
    is_placeholder: bool,
) -> TeamInjurySide:
    starter_map = _starter_map(lineup_items, team_id, team_name)
    playing_ids = {pid for pid, info in starter_map.items() if info.get("in_xi")}

    data_available = not injuries_missing and bool(injuries)
    players = _parse_unavailable(
        injuries,
        starter_map=starter_map,
        playing_ids=playing_ids,
        is_placeholder=is_placeholder,
    )

    confirmed = sum(1 for p in players if p.status == "confirmed")
    doubtful = sum(1 for p in players if p.status == "doubtful")
    suspended = sum(1 for p in players if p.status == "suspended")

    impact = _team_impact_score(players)
    losses = _position_losses(players)

    confidence = 25.0
    if data_available and not is_placeholder:
        confidence = 75.0 if players else 60.0
    elif data_available:
        confidence = 45.0
    elif not injuries_missing:
        confidence = 55.0

    side = TeamInjurySide(
        unavailable_players=players,
        confirmed_count=confirmed,
        doubtful_count=doubtful,
        suspended_count=suspended,
        injury_impact_score=impact,
        impact_band=_impact_band(impact),
        position_losses=losses,
        confidence=round(_clamp(confidence, 0.0, 100.0), 1),
        data_available=data_available or (not injuries_missing),
    )
    side.risk_flags = _risk_flags(side, players)
    return side


def _build_prediction_impact(home: TeamInjurySide, away: TeamInjurySide) -> InjuryPredictionImpact:
    home_adj = -(home.injury_impact_score / 100.0) * 8.0
    away_adj = -(away.injury_impact_score / 100.0) * 8.0
    over_adj = 0.0
    under_adj = 0.0

    for side in (home, away):
        losses = side.position_losses
        if losses.defensive_loss >= 40:
            over_adj += 1.5
        if losses.attacking_loss >= 40:
            under_adj += 1.5
        if any(p.position_group == "Goalkeeper" for p in side.unavailable_players):
            over_adj += 2.0
        if side.suspended_count >= 2:
            over_adj += 0.5

    if not home.data_available and not away.data_available:
        return InjuryPredictionImpact()

    if home.injury_impact_score < 5 and away.injury_impact_score < 5:
        home_adj = away_adj = over_adj = under_adj = 0.0

    return InjuryPredictionImpact(
        home_adjustment=round(_clamp(home_adj, -_ADJUSTMENT_CAP, _ADJUSTMENT_CAP), 1),
        away_adjustment=round(_clamp(away_adj, -_ADJUSTMENT_CAP, _ADJUSTMENT_CAP), 1),
        over25_adjustment=round(_clamp(over_adj, -_ADJUSTMENT_CAP, _ADJUSTMENT_CAP), 1),
        under25_adjustment=round(_clamp(under_adj, -_ADJUSTMENT_CAP, _ADJUSTMENT_CAP), 1),
    )


def _build_summary(home: TeamInjurySide, away: TeamInjurySide) -> str:
    if not home.unavailable_players and not away.unavailable_players:
        if "low_data_confidence" in home.risk_flags + away.risk_flags:
            return "No injury/suspension records available — safe fallback applied. Analysis only — not betting advice."
        return "No unavailable players reported — injury impact negligible. Analysis only — not betting advice."
    parts = [
        f"Home impact {home.injury_impact_score:.0f}/100 ({home.impact_band}), "
        f"Away impact {away.injury_impact_score:.0f}/100 ({away.impact_band})."
    ]
    flags = sorted(set(home.risk_flags + away.risk_flags))
    if flags:
        parts.append(f"Risk flags: {', '.join(flags)}.")
    parts.append("Injury analysis only — not betting advice.")
    return " ".join(parts)


def build_injury_intelligence(report: Any) -> InjuryIntelligenceResult:
    """Build injury intelligence — never raises."""
    try:
        return _build_inner(report)
    except Exception:
        empty = TeamInjurySide(risk_flags=["low_data_confidence"])
        return InjuryIntelligenceResult(
            home=empty,
            away=TeamInjurySide(risk_flags=["low_data_confidence"]),
            summary="Injury intelligence unavailable — safe fallback applied.",
            prediction_impact=InjuryPredictionImpact(),
        )


def _build_inner(report: Any) -> InjuryIntelligenceResult:
    missing = set(getattr(report, "missing_data", None) or [])
    injuries_missing = "injuries" in missing
    is_placeholder = bool(getattr(report, "is_placeholder", True))
    lineup_items = _safe_list((getattr(report, "lineups", None) or {}).get("items"))

    home_intel = getattr(report, "home_team", None)
    away_intel = getattr(report, "away_team", None)
    home_inj = _safe_list(home_intel.injuries.players if home_intel and home_intel.injuries else [])
    away_inj = _safe_list(away_intel.injuries.players if away_intel and away_intel.injuries else [])

    home = _analyze_team_side(
        home_inj,
        lineup_items=lineup_items,
        team_id=getattr(home_intel, "team_id", None) if home_intel else None,
        team_name=getattr(home_intel, "team_name", "Home") if home_intel else "Home",
        injuries_missing=injuries_missing,
        is_placeholder=is_placeholder,
    )
    away = _analyze_team_side(
        away_inj,
        lineup_items=lineup_items,
        team_id=getattr(away_intel, "team_id", None) if away_intel else None,
        team_name=getattr(away_intel, "team_name", "Away") if away_intel else "Away",
        injuries_missing=injuries_missing,
        is_placeholder=is_placeholder,
    )

    impact = _build_prediction_impact(home, away)
    summary = _build_summary(home, away)

    return InjuryIntelligenceResult(
        home=home,
        away=away,
        summary=summary,
        prediction_impact=impact,
    )
