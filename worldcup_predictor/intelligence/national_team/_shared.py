"""National-team intelligence — shared helpers (Phase 32B)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

COMPETITION_WEIGHTS: dict[str, float] = {
    "world_cup": 1.00,
    "continental": 0.85,
    "qualification": 0.75,
    "nations_league": 0.65,
    "friendly": 0.35,
    "other": 0.50,
}

H2H_RECENCY_WEIGHTS: tuple[tuple[float, float], ...] = (
    (2.0, 1.0),
    (4.0, 0.6),
    (8.0, 0.3),
    (999.0, 0.1),
)


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_team_name(name: str) -> str:
    text = (name or "").strip().lower()
    text = text.replace("türkiye", "turkey").replace("turkiye", "turkey")
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_kickoff(value: Any) -> datetime | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
        if "T" in raw:
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo:
                return dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def years_since(match_date: datetime | None, *, reference: datetime | None = None) -> float:
    if match_date is None:
        return 99.0
    ref = reference or datetime.now(timezone.utc).replace(tzinfo=None)
    return max(0.0, (ref - match_date).days / 365.25)


def recency_weight(years: float) -> float:
    for limit, weight in H2H_RECENCY_WEIGHTS:
        if years < limit:
            return weight
    return 0.1


def classify_competition(league: dict[str, Any] | None) -> str:
    if not isinstance(league, dict):
        return "other"
    name = str(league.get("name") or "").lower()
    league_type = str(league.get("type") or "").lower()
    if "world cup" in name:
        return "world_cup"
    if any(k in name for k in ("euro", "copa america", "afcon", "africa cup", "asian cup", "concacaf gold")):
        return "continental"
    if "qualif" in name:
        return "qualification"
    if "nations league" in name or "nations league" in league_type:
        return "nations_league"
    if "friendly" in name or "friendlies" in name:
        return "friendly"
    if league.get("id") == 1:
        return "world_cup"
    return "other"


def competition_weight(league: dict[str, Any] | None) -> float:
    bucket = classify_competition(league)
    return COMPETITION_WEIGHTS.get(bucket, COMPETITION_WEIGHTS["other"])


def match_recency_index(index: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return 1.0 + (total - index) / max(total, 1)


def safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def goals_from_fixture(item: dict[str, Any]) -> tuple[int | None, int | None]:
    goals = item.get("goals") or {}
    home = goals.get("home")
    away = goals.get("away")
    if home is None or away is None:
        score = item.get("score") or {}
        full = score.get("fulltime") or score.get("regular") or {}
        home = full.get("home") if home is None else home
        away = full.get("away") if away is None else away
    try:
        return int(home) if home is not None else None, int(away) if away is not None else None
    except (TypeError, ValueError):
        return None, None


def team_side_in_fixture(item: dict[str, Any], team_id: int) -> str | None:
    teams = item.get("teams") or {}
    home = teams.get("home") or {}
    away = teams.get("away") or {}
    if int_or_none(home.get("id")) == team_id:
        return "home"
    if int_or_none(away.get("id")) == team_id:
        return "away"
    return None


def venue_bucket(item: dict[str, Any], team_id: int) -> str:
    side = team_side_in_fixture(item, team_id)
    if side is None:
        return "neutral"
    fixture = item.get("fixture") or {}
    venue = fixture.get("venue") or {}
    neutral = venue.get("neutral")
    if neutral is True:
        return "neutral"
    return side


def fixture_item_id(item: dict[str, Any]) -> int | None:
    return int_or_none((item.get("fixture") or {}).get("id"))


def fixture_item_kickoff(item: dict[str, Any]) -> datetime | None:
    return parse_kickoff((item.get("fixture") or {}).get("date"))


def filter_history_fixtures(
    fixtures: list[dict[str, Any]] | None,
    *,
    before_kickoff: datetime | None = None,
    exclude_fixture_id: int | None = None,
) -> list[dict[str, Any]]:
    """Drop circular/forward rows: require match_date < kickoff and id != target."""
    out: list[dict[str, Any]] = []
    for item in safe_list(fixtures):
        if not isinstance(item, dict):
            continue
        fid = fixture_item_id(item)
        if exclude_fixture_id is not None and fid is not None and int(fid) == int(exclude_fixture_id):
            continue
        if before_kickoff is not None:
            kick = fixture_item_kickoff(item)
            if kick is not None and kick >= before_kickoff:
                continue
        out.append(item)
    return out


def resolve_report_kickoff(
    report: Any,
    *,
    repo: Any | None = None,
) -> datetime | None:
    """Resolve target fixture kickoff from report object or SQLite row."""
    if report.fixture and getattr(report.fixture, "kickoff_utc", None):
        kick = parse_kickoff(report.fixture.kickoff_utc)
        if kick:
            return kick
    fixture_id = getattr(report, "fixture_id", None)
    if fixture_id and repo is not None:
        row = repo.get_fixture_row(int(fixture_id))
        if row:
            kick = parse_kickoff(row.get("kickoff_utc"))
            if kick:
                return kick
    return None
