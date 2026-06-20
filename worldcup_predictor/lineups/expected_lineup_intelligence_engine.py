"""Expected Lineup Intelligence — Phase 22F (benchmark/trace, no WDE changes)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from worldcup_predictor.lineups.lineup_intelligence_engine import (
    _OFFICIAL_STATUSES,
    _analyze_side,
    _fetch_previous_starting_ids,
    _find_team_lineup,
    _previous_fixture_id,
    _safe_list,
)

_OFFICIAL_LINEUP_MIN = 11
_ATTACK_POS = frozenset({"F", "FW", "ST", "CF", "LW", "RW", "SS"})
_DEF_POS = frozenset({"D", "DF", "CB", "LB", "RB", "WB", "LWB", "RWB"})
_MID_POS = frozenset({"M", "MF", "CM", "DM", "CDM", "AM", "CAM", "LM", "RM"})


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


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
    if isinstance(player, dict):
        try:
            num = player.get("number")
            return int(num) if num is not None else None
        except (TypeError, ValueError):
            return None
    return None


def _norm_name(name: str) -> str:
    return (name or "").strip().lower()


def _role_bucket(pos: str) -> str:
    p = pos.upper()
    if p == "G" or "GOAL" in p:
        return "goalkeeper"
    if p in _ATTACK_POS or p.startswith("F"):
        return "attacker"
    if p in _DEF_POS or p.startswith("D"):
        return "defender"
    if p in _MID_POS or p.startswith("M"):
        return "midfielder"
    return "other"


def _injury_names(injuries: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for item in injuries:
        if not isinstance(item, dict):
            continue
        player = item.get("player") or {}
        if isinstance(player, dict):
            name = player.get("name")
            if name:
                names.add(_norm_name(str(name)))
                continue
        name = item.get("player_name") or item.get("name")
        if name:
            names.add(_norm_name(str(name)))
    return names


def _lineup_snapshot(
    lineup: dict[str, Any] | None,
    *,
    side: str,
    source: str,
) -> dict[str, Any]:
    if not lineup:
        return {"side": side, "available": False, "source": source, "starters": [], "formation": None}
    starters = []
    for entry in _safe_list(lineup.get("startXI")):
        if not isinstance(entry, dict):
            continue
        name = _player_name(entry)
        if not name:
            continue
        starters.append(
            {
                "name": name,
                "pos": _player_pos(entry),
                "number": _player_number(entry),
            }
        )
    return {
        "side": side,
        "available": bool(starters),
        "source": source,
        "starters": starters,
        "formation": lineup.get("formation"),
        "substitutes_count": len(_safe_list(lineup.get("substitutes"))),
    }


def _collect_lineup_items(report: Any) -> tuple[list[dict[str, Any]], str]:
    """Priority: API-Football lineups, then Sportmonks gap-fill."""
    lineups_block = getattr(report, "lineups", None) or {}
    items = _safe_list(lineups_block.get("items"))
    source = str(lineups_block.get("source") or "api_football")
    if items:
        return items, source

    supplemental = getattr(report, "supplemental_sources", None) or {}
    sm = supplemental.get("sportmonks") or {}
    sm_items = _safe_list(sm.get("lineups_api"))
    if sm_items:
        return sm_items, "sportmonks"
    return [], "none"


def _collect_injuries(report: Any, side: str) -> tuple[list[dict[str, Any]], str]:
    """Priority: API-Football injuries, then Sportmonks sidelined."""
    team = report.home_team if side == "home" else report.away_team
    injuries = _safe_list(team.injuries.players if team and team.injuries else [])
    if injuries:
        return injuries, "api_football"

    supplemental = getattr(report, "supplemental_sources", None) or {}
    sm = supplemental.get("sportmonks") or {}
    sm_inj = _safe_list(sm.get(f"{side}_injuries"))
    if sm_inj:
        return sm_inj, "sportmonks"
    return [], "none"


def _is_confirmed(fixture_status: str, lineup: dict[str, Any] | None) -> bool:
    status = (fixture_status or "NS").upper()
    return status in _OFFICIAL_STATUSES


def _historical_expected_xi(
    api_client: Any,
    *,
    team_id: int | None,
    recent_fixtures: list[dict[str, Any]] | None,
    current_fixture_id: int | None,
    injured: set[str],
) -> dict[str, Any] | None:
    prev_fid = _previous_fixture_id(
        recent_fixtures,
        team_id=team_id,
        current_fixture_id=current_fixture_id,
    )
    if not prev_fid or api_client is None:
        return None
    prev_ids = _fetch_previous_starting_ids(api_client, prev_fid)
    if not prev_ids:
        return None

    try:
        result = api_client.get_fixture_lineups(prev_fid)
        if not result.ok:
            return None
        items = _safe_list(result.data)
        for item in items:
            if not isinstance(item, dict):
                continue
            team = item.get("team") or {}
            if team_id is not None and team.get("id") != team_id:
                continue
            starters = []
            for entry in _safe_list(item.get("startXI")):
                name = _player_name(entry)
                if not name or _norm_name(name) in injured:
                    continue
                starters.append(
                    {
                        "player": {
                            "name": name,
                            "pos": _player_pos(entry),
                            "number": _player_number(entry),
                        }
                    }
                )
            if starters:
                return {
                    "team": team,
                    "formation": item.get("formation"),
                    "startXI": starters[:11],
                    "substitutes": [],
                    "source": "historical_pattern",
                }
    except Exception:
        return None
    return None


def _compare_expected_confirmed(
    expected: dict[str, Any],
    confirmed: dict[str, Any],
) -> dict[str, Any]:
    exp_names = {_norm_name(s.get("name", "")) for s in expected.get("starters", []) if s.get("name")}
    conf_names = {_norm_name(s.get("name", "")) for s in confirmed.get("starters", []) if s.get("name")}
    exp_names.discard("")
    conf_names.discard("")

    overlap = exp_names & conf_names
    union = exp_names | conf_names
    overlap_pct = round(len(overlap) / max(len(union), 1) * 100.0, 1)

    exp_gk = next((s for s in expected.get("starters", []) if _role_bucket(s.get("pos", "")) == "goalkeeper"), None)
    conf_gk = next((s for s in confirmed.get("starters", []) if _role_bucket(s.get("pos", "")) == "goalkeeper"), None)
    gk_match = None
    if exp_gk and conf_gk:
        gk_match = _norm_name(exp_gk.get("name", "")) == _norm_name(conf_gk.get("name", ""))

    exp_form = str(expected.get("formation") or "")
    conf_form = str(confirmed.get("formation") or "")
    formation_match = bool(exp_form and conf_form and exp_form == conf_form)

    surprise = sorted(conf_names - exp_names)
    missed = sorted(exp_names - conf_names)

    return {
        "comparison_available": bool(exp_names and conf_names),
        "player_overlap_pct": overlap_pct,
        "goalkeeper_match": gk_match,
        "formation_match": formation_match,
        "surprise_starters": surprise[:11],
        "missed_expected": missed[:11],
    }


def _missing_by_role(starters: list[dict[str, Any]], injured: set[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {"attackers": [], "midfielders": [], "defenders": [], "key": []}
    for entry in starters:
        name = _player_name(entry)
        if not name or _norm_name(name) not in injured:
            continue
        role = _role_bucket(_player_pos(entry))
        if role == "attacker":
            out["attackers"].append(name)
        elif role == "midfielder":
            out["midfielders"].append(name)
        elif role == "defender":
            out["defenders"].append(name)
        out["key"].append(name)
    return out


@dataclass
class ExpectedLineupIntelligenceResult:
    lineup_confidence: float = 25.0
    lineup_strength_delta: float = 0.0
    expected_goalkeeper_home: str | None = None
    expected_goalkeeper_away: str | None = None
    goalkeeper_change_flag: bool = False
    missing_key_players: list[str] = field(default_factory=list)
    missing_attackers: int = 0
    missing_midfielders: int = 0
    missing_defenders: int = 0
    rotation_risk: str = "Medium"
    expected_formation: str | None = None
    formation_change_risk: str = "medium"
    expected_xi_quality: float = 50.0
    lineup_supports_internal: bool = True
    star_player_absence_score: float = 0.0
    chemistry_risk: str = "medium"
    continuity_score: float = 50.0
    bench_strength_score: float = 50.0
    late_news_risk: str = "medium"
    comparison_available: bool = False
    confirmed_available: bool = False
    expected_snapshot: dict[str, Any] = field(default_factory=dict)
    confirmed_snapshot: dict[str, Any] = field(default_factory=dict)
    player_overlap_pct: float | None = None
    surprise_starters: list[str] = field(default_factory=list)
    missed_expected: list[str] = field(default_factory=list)
    data_sources: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    version: str = "22f"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def reconcile_expected_with_prior(
    result: ExpectedLineupIntelligenceResult,
    prior_payload: dict[str, Any] | None,
) -> ExpectedLineupIntelligenceResult:
    """When confirmed XI arrives, compare against cached pre-kickoff expected snapshot."""
    if not result.confirmed_available or not prior_payload:
        return result
    prior_exp = prior_payload.get("expected_snapshot")
    if not isinstance(prior_exp, dict) or not prior_exp:
        return result

    home_cmp = _compare_expected_confirmed(
        prior_exp.get("home") or {},
        (result.confirmed_snapshot or {}).get("home") or {},
    )
    away_cmp = _compare_expected_confirmed(
        prior_exp.get("away") or {},
        (result.confirmed_snapshot or {}).get("away") or {},
    )
    comparison_available = home_cmp.get("comparison_available") or away_cmp.get("comparison_available")
    overlaps = [v for v in (home_cmp.get("player_overlap_pct"), away_cmp.get("player_overlap_pct")) if v is not None]
    avg_overlap = round(sum(overlaps) / len(overlaps), 1) if overlaps else None
    surprise = sorted(set(home_cmp.get("surprise_starters") or []) | set(away_cmp.get("surprise_starters") or []))
    missed = sorted(set(home_cmp.get("missed_expected") or []) | set(away_cmp.get("missed_expected") or []))

    notes = list(result.notes)
    notes.append("Compared confirmed XI vs cached pre-kickoff expected snapshot.")
    return ExpectedLineupIntelligenceResult(
        **{
            **result.to_dict(),
            "expected_snapshot": prior_exp,
            "comparison_available": comparison_available,
            "player_overlap_pct": avg_overlap,
            "surprise_starters": surprise[:12],
            "missed_expected": missed[:12],
            "notes": notes,
        }
    )


def build_expected_lineup_intelligence(
    report: Any,
    *,
    api_client: Any | None = None,
    specialist_signals: dict[str, Any] | None = None,
) -> ExpectedLineupIntelligenceResult:
    """Build expected lineup benchmark — trace only, no WDE changes."""
    specialist_signals = specialist_signals or {}
    fixture = getattr(report, "fixture", None)
    fixture_status = getattr(fixture, "status", "NS") if fixture else "NS"
    is_live_source = not getattr(report, "is_placeholder", True)
    current_fid = getattr(report, "fixture_id", None)

    home_intel = report.home_team
    away_intel = report.away_team
    home_id = home_intel.team_id
    away_id = away_intel.team_id
    home_name = home_intel.team_name
    away_name = away_intel.team_name

    items, lineup_source = _collect_lineup_items(report)
    home_lineup = _find_team_lineup(items, team_id=home_id, team_name=home_name)
    away_lineup = _find_team_lineup(items, team_id=away_id, team_name=away_name)

    home_inj, home_inj_src = _collect_injuries(report, "home")
    away_inj, away_inj_src = _collect_injuries(report, "away")
    home_injured = _injury_names(home_inj)
    away_injured = _injury_names(away_inj)

    sources: list[str] = []
    if items:
        sources.append(f"lineups_{lineup_source}")
    if home_inj or away_inj:
        sources.append(f"injuries_{home_inj_src if home_inj else away_inj_src}")

    home_confirmed = _is_confirmed(fixture_status, home_lineup)
    away_confirmed = _is_confirmed(fixture_status, away_lineup)

    home_expected_lineup = home_lineup
    away_expected_lineup = away_lineup
    expected_source = lineup_source

    if not home_confirmed and home_lineup and len(_safe_list(home_lineup.get("startXI"))) >= 1:
        home_expected_lineup = home_lineup
        expected_source = lineup_source
    elif not home_confirmed:
        hist = _historical_expected_xi(
            api_client,
            team_id=home_id,
            recent_fixtures=getattr(report, "home_recent_fixtures", None),
            current_fixture_id=current_fid,
            injured=home_injured,
        )
        if hist:
            home_expected_lineup = hist
            expected_source = "historical_pattern"
            sources.append("historical_starting_xi_home")
    if not away_confirmed and away_lineup and len(_safe_list(away_lineup.get("startXI"))) >= 1:
        away_expected_lineup = away_lineup
        expected_source = lineup_source
    elif not away_confirmed:
        hist = _historical_expected_xi(
            api_client,
            team_id=away_id,
            recent_fixtures=getattr(report, "away_recent_fixtures", None),
            current_fixture_id=current_fid,
            injured=away_injured,
        )
        if hist:
            away_expected_lineup = hist
            expected_source = "historical_pattern"
            sources.append("historical_starting_xi_away")

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

    home_side = _analyze_side(
        home_expected_lineup if not home_confirmed else home_lineup,
        injuries=home_inj,
        fixture_status=fixture_status,
        is_live_source=is_live_source,
        previous_rotation_ids=home_prev_ids,
    )
    away_side = _analyze_side(
        away_expected_lineup if not away_confirmed else away_lineup,
        injuries=away_inj,
        fixture_status=fixture_status,
        is_live_source=is_live_source,
        previous_rotation_ids=away_prev_ids,
    )

    confirmed_home = _lineup_snapshot(home_lineup if home_confirmed else None, side="home", source=lineup_source)
    confirmed_away = _lineup_snapshot(away_lineup if away_confirmed else None, side="away", source=lineup_source)
    expected_home = _lineup_snapshot(
        home_expected_lineup,
        side="home",
        source=expected_source if not home_confirmed else lineup_source,
    )
    expected_away = _lineup_snapshot(
        away_expected_lineup,
        side="away",
        source=expected_source if not away_confirmed else lineup_source,
    )

    expected_snapshot = {"home": expected_home, "away": expected_away}
    confirmed_snapshot = {"home": confirmed_home, "away": confirmed_away}
    confirmed_available = confirmed_home.get("available") or confirmed_away.get("available")

    home_cmp = _compare_expected_confirmed(expected_home, confirmed_home) if home_confirmed else {}
    away_cmp = _compare_expected_confirmed(expected_away, confirmed_away) if away_confirmed else {}
    comparison_available = home_cmp.get("comparison_available") or away_cmp.get("comparison_available")

    overlaps = [v for v in (home_cmp.get("player_overlap_pct"), away_cmp.get("player_overlap_pct")) if v is not None]
    avg_overlap = round(sum(overlaps) / len(overlaps), 1) if overlaps else None

    surprise = sorted(set(home_cmp.get("surprise_starters") or []) | set(away_cmp.get("surprise_starters") or []))
    missed = sorted(set(home_cmp.get("missed_expected") or []) | set(away_cmp.get("missed_expected") or []))

    home_missing = _missing_by_role(_safe_list(home_expected_lineup.get("startXI")) if home_expected_lineup else [], home_injured)
    away_missing = _missing_by_role(_safe_list(away_expected_lineup.get("startXI")) if away_expected_lineup else [], away_injured)
    missing_key = sorted(set(home_missing["key"] + away_missing["key"] + list(home_injured | away_injured)))
    missing_attackers = len(home_missing["attackers"]) + len(away_missing["attackers"])
    missing_midfielders = len(home_missing["midfielders"]) + len(away_missing["midfielders"])
    missing_defenders = len(home_missing["defenders"]) + len(away_missing["defenders"])

    exp_gk_home = home_side.goalkeeper_name
    exp_gk_away = away_side.goalkeeper_name
    gk_change = home_side.goalkeeper_status == "backup" or away_side.goalkeeper_status == "backup"

    formations: list[str] = []
    if home_side.formation:
        formations.append(f"Home {home_side.formation}")
    if away_side.formation:
        formations.append(f"Away {away_side.formation}")
    expected_formation = " / ".join(formations) if formations else None

    rotation_scores = []
    for side in (home_side, away_side):
        if side.rotation_count is not None:
            rotation_scores.append(side.rotation_count)
    rotation_risk = "Low"
    if any(r >= 5 for r in rotation_scores):
        rotation_risk = "High"
    elif any(r >= 3 for r in rotation_scores):
        rotation_risk = "Medium"

    formation_change_risk = "low"
    if home_side.rotation_count and home_side.rotation_count >= 4:
        formation_change_risk = "high"
    elif away_side.rotation_count and away_side.rotation_count >= 4:
        formation_change_risk = "medium"

    avg_strength = (home_side.lineup_strength + away_side.lineup_strength) / 2
    avg_confidence = (home_side.confidence + away_side.confidence) / 2
    baseline = 50.0
    strength_delta = round(avg_strength - baseline, 1)

    continuity_parts = []
    for side_obj, prev_ids in ((home_side, home_prev_ids), (away_side, away_prev_ids)):
        if side_obj.rotation_count is not None and prev_ids:
            continuity_parts.append(max(0, 11 - side_obj.rotation_count) / 11 * 100)
    continuity_score = round(sum(continuity_parts) / len(continuity_parts), 1) if continuity_parts else 50.0

    bench_scores = []
    for side_obj in (home_side, away_side):
        subs = side_obj.substitutes_count
        bench_scores.append(_clamp(40 + subs * 8, 0, 100))
    bench_strength_score = round(sum(bench_scores) / len(bench_scores), 1) if bench_scores else 50.0

    star_absence = _clamp(len(missing_key) * 12 + missing_attackers * 8, 0, 100)
    chemistry_risk = "high" if star_absence >= 40 or "many_rotations" in home_side.risk_flags + away_side.risk_flags else (
        "medium" if star_absence >= 20 else "low"
    )
    late_news_risk = "high" if not confirmed_available and avg_confidence < 45 else (
        "medium" if not confirmed_available else "low"
    )

    lineup_supports_internal = True
    lineup_v2 = specialist_signals.get("lineup_intelligence_agent")
    if lineup_v2 is not None and getattr(lineup_v2, "is_usable", True):
        block = lineup_v2.signals if hasattr(lineup_v2, "signals") else lineup_v2
        if isinstance(block, dict):
            int_home = float((block.get("home") or {}).get("lineup_strength") or avg_strength)
            int_away = float((block.get("away") or {}).get("lineup_strength") or avg_strength)
            int_avg = (int_home + int_away) / 2
            lineup_supports_internal = abs(int_avg - avg_strength) < 15

    notes: list[str] = []
    if not sources:
        notes.append("Limited lineup data — expected XI uses safe fallbacks.")
    if confirmed_available and comparison_available:
        notes.append(f"Expected vs confirmed overlap {avg_overlap}% — benchmark trace.")
    elif not confirmed_available:
        notes.append("Confirmed lineups not published — expected XI only (trace).")
    if gk_change:
        notes.append("Goalkeeper change detected — volatility flag (analysis only).")
    if not lineup_supports_internal:
        notes.append("Expected lineup benchmark diverges from Lineup Intelligence V2.")

    return ExpectedLineupIntelligenceResult(
        lineup_confidence=round(avg_confidence, 1),
        lineup_strength_delta=strength_delta,
        expected_goalkeeper_home=exp_gk_home,
        expected_goalkeeper_away=exp_gk_away,
        goalkeeper_change_flag=gk_change,
        missing_key_players=missing_key[:12],
        missing_attackers=missing_attackers,
        missing_midfielders=missing_midfielders,
        missing_defenders=missing_defenders,
        rotation_risk=rotation_risk,
        expected_formation=expected_formation,
        formation_change_risk=formation_change_risk,
        expected_xi_quality=round(avg_strength, 1),
        lineup_supports_internal=lineup_supports_internal,
        star_player_absence_score=round(star_absence, 1),
        chemistry_risk=chemistry_risk,
        continuity_score=continuity_score,
        bench_strength_score=bench_strength_score,
        late_news_risk=late_news_risk,
        comparison_available=comparison_available,
        confirmed_available=confirmed_available,
        expected_snapshot=expected_snapshot,
        confirmed_snapshot=confirmed_snapshot,
        player_overlap_pct=avg_overlap,
        surprise_starters=surprise[:12],
        missed_expected=missed[:12],
        data_sources=sources,
        notes=notes,
    )
