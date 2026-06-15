"""Extract real shooting / xG statistics from API-Football and supplemental sources."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.domain.intelligence import MatchIntelligenceReport

_STAT_ALIASES: dict[str, tuple[str, ...]] = {
    "shots_total": ("total shots", "shots total", "shots"),
    "shots_on_target": ("shots on goal", "shots on target", "on target"),
    "big_chances": ("big chances", "big chance"),
    "blocked_shots": ("blocked shots", "blocked"),
    "inside_box": ("shots insidebox", "shots inside box", "inside box shots"),
    "goalkeeper_saves": ("goalkeeper saves", "saves"),
    "expected_goals": ("expected goals", "xg", "expected_goals"),
}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip().replace("%", "")
        if not cleaned or cleaned == "-":
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _nested_total(stats: dict[str, Any], group: str, field: str) -> float | None:
    block = stats.get(group)
    if not isinstance(block, dict):
        return None
    direct = _float_or_none(block.get(field))
    if direct is not None:
        return direct
    nested = block.get(field)
    if isinstance(nested, dict):
        return _float_or_none(nested.get("total") or nested.get("average"))
    total_block = block.get("total")
    if isinstance(total_block, dict):
        return _float_or_none(total_block.get("total") or total_block.get("average"))
    return _float_or_none(total_block)


def _matches_played(stats: dict[str, Any]) -> float | None:
    played = _nested_total(stats, "fixtures", "played")
    if played is not None and played > 0:
        return played
    fixtures = stats.get("fixtures") or {}
    if isinstance(fixtures, dict):
        played_block = fixtures.get("played") or {}
        if isinstance(played_block, dict):
            return _float_or_none(played_block.get("total"))
    return None


def _goals_for_total(stats: dict[str, Any]) -> float | None:
    goals = stats.get("goals") or {}
    if not isinstance(goals, dict):
        return None
    for_block = goals.get("for") or {}
    if isinstance(for_block, dict):
        total_block = for_block.get("total") or {}
        if isinstance(total_block, dict):
            val = _float_or_none(total_block.get("total"))
            if val is not None:
                return val
            avg = _float_or_none(total_block.get("average"))
            played = _matches_played(stats)
            if avg is not None and played:
                return avg * played
    return None


def _goals_against_avg(stats: dict[str, Any]) -> float | None:
    goals = stats.get("goals") or {}
    if not isinstance(goals, dict):
        return None
    against = goals.get("against") or {}
    if isinstance(against, dict):
        total_block = against.get("total") or {}
        if isinstance(total_block, dict):
            return _float_or_none(total_block.get("average"))
    return None


def _parse_fixture_stat_map(items: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for block in items:
        if not isinstance(block, dict):
            continue
        team = block.get("team") or {}
        team_id = team.get("id")
        team_name = str(team.get("name") or "").lower()
        key = str(team_id) if team_id is not None else team_name
        parsed: dict[str, float] = {}
        for stat in block.get("statistics") or []:
            if not isinstance(stat, dict):
                continue
            stat_type = str(stat.get("type") or "").lower().strip()
            val = _float_or_none(stat.get("value"))
            if val is None:
                continue
            for canonical, aliases in _STAT_ALIASES.items():
                if stat_type in aliases or any(alias in stat_type for alias in aliases):
                    parsed[canonical] = val
                    break
            else:
                parsed[stat_type.replace(" ", "_")] = val
        if parsed:
            out[key] = parsed
            if team_name:
                out[team_name] = parsed
    return out


def _fixture_side_map(report: MatchIntelligenceReport) -> dict[str, dict[str, float]]:
    fixture_stats = report.fixture_statistics or {}
    items = fixture_stats.get("items") if isinstance(fixture_stats, dict) else None
    if not items or not isinstance(items, list):
        return {}
    return _parse_fixture_stat_map(items)


def _supplemental_match_stats(report: MatchIntelligenceReport) -> dict[str, Any]:
    supplemental = getattr(report, "supplemental_sources", None) or {}
    rapid_stats = supplemental.get("rapid_football_stats") or {}
    match_stats = rapid_stats.get("match_statistics") if isinstance(rapid_stats, dict) else {}
    return match_stats if isinstance(match_stats, dict) else {}


def extract_real_xg(
    report: MatchIntelligenceReport,
    *,
    side: str,
    team_stats: dict[str, Any],
) -> tuple[float | None, str | None]:
    """Return (xg_value, source) only when real xG is present — never invented."""
    supplemental = getattr(report, "supplemental_sources", None) or {}
    rapid_stats = supplemental.get("rapid_football_stats") or {}
    rapid_xg = supplemental.get("rapid_xg_statistics") or {}

    for source_name, block in (
        ("rapid_xg_statistics", rapid_xg),
        ("rapid_football_stats", rapid_stats),
    ):
        if not isinstance(block, dict):
            continue
        xg_block = block.get("xg") or block.get("npxg")
        if isinstance(xg_block, dict):
            val = _float_or_none(xg_block.get(side) or xg_block.get(f"{side}_xg"))
            if val is not None:
                return val, source_name
        fixture_detail = block.get("fixture_detail")
        if isinstance(fixture_detail, dict):
            for key in (f"{side}_xg", f"{side}Xg", "xg"):
                nested = fixture_detail.get(key)
                if isinstance(nested, dict):
                    val = _float_or_none(nested.get(side))
                    if val is not None:
                        return val, source_name
                val = _float_or_none(nested)
                if val is not None:
                    return val, source_name

    expected_block = (team_stats.get("goals") or {}).get("for", {}).get("expected")
    if isinstance(expected_block, dict):
        val = _float_or_none(expected_block.get("total") or expected_block.get("average"))
        if val is not None:
            return val, "api_team_expected_goals"

    fixture_map = _fixture_side_map(report)
    team_id = report.home_team.team_id if side == "home" else report.away_team.team_id
    team_name = (report.home_team.team_name if side == "home" else report.away_team.team_name).lower()
    for lookup in (str(team_id) if team_id is not None else None, team_name):
        if lookup and lookup in fixture_map:
            val = fixture_map[lookup].get("expected_goals")
            if val is not None:
                return val, "api_fixture_statistics"

    return None, None


def extract_team_shooting_profile(
    report: MatchIntelligenceReport,
    *,
    side: str,
    team_stats: dict[str, Any],
) -> dict[str, float | None]:
    """Build shooting profile from team season stats, fixture stats, and supplemental data."""
    team_id = report.home_team.team_id if side == "home" else report.away_team.team_id
    team_name = (report.home_team.team_name if side == "home" else report.away_team.team_name).lower()
    played = _matches_played(team_stats)

    shots_total = _nested_total(team_stats, "shots", "total")
    shots_on_target = _nested_total(team_stats, "shots", "on")
    blocked = _nested_total(team_stats, "shots", "blocked")
    inside_box = _nested_total(team_stats, "shots", "insidebox")
    big_chances: float | None = None

    goals_avg = _float_or_none(
        (team_stats.get("goals") or {}).get("for", {}).get("total", {}).get("average")
    )
    goals = goals_avg
    if goals is None:
        goals_total = _goals_for_total(team_stats)
        goals = _per_match_value(goals_total, played)

    ga_avg = _goals_against_avg(team_stats)

    use_fixture_stats = not report.is_placeholder and report.source != "placeholder"
    fixture_map = _fixture_side_map(report) if use_fixture_stats else {}
    side_fixture: dict[str, float] = {}
    for lookup in (str(team_id) if team_id is not None else None, team_name):
        if lookup and lookup in fixture_map:
            side_fixture = fixture_map[lookup]
            break

    if side_fixture:
        shots_total = side_fixture.get("shots_total", shots_total)
        shots_on_target = side_fixture.get("shots_on_target", shots_on_target)
        big_chances = side_fixture.get("big_chances", big_chances)
        blocked = side_fixture.get("blocked_shots", blocked)
        inside_box = side_fixture.get("inside_box", inside_box)

    match_stats = _supplemental_match_stats(report)
    prefix = f"{side}_"
    if match_stats:
        shots_total = _float_or_none(match_stats.get(f"{prefix}shots")) or shots_total
        shots_on_target = _float_or_none(match_stats.get(f"{prefix}shots_on_target")) or shots_on_target
        big_chances = _float_or_none(match_stats.get(f"{prefix}big_chances")) or big_chances

    saves = side_fixture.get("goalkeeper_saves") if side_fixture else None

    return {
        "shots_total": _per_match_value(shots_total, played),
        "shots_on_target": _per_match_value(shots_on_target, played),
        "big_chances": _per_match_value(big_chances, played),
        "blocked_shots": _per_match_value(blocked, played),
        "inside_box_shots": _per_match_value(inside_box, played),
        "goalkeeper_saves": _per_match_value(saves, played),
        "goals": goals,
        "goals_against_avg": ga_avg,
        "matches_played": played,
    }


def _per_match_value(total: float | None, played: float | None) -> float | None:
    if total is None:
        return None
    if played and played > 0 and total > played:
        return total / played
    return total
