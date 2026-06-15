"""Phase 55 — conservative player feature extraction from existing API-Sports payloads."""

from __future__ import annotations

from typing import Any

_RATING_WEIGHT = 0.12
_ASSISTS_WEIGHT = 0.08
_KEY_PASSES_WEIGHT = 0.06
_GOALS_WEIGHT = 1.0
_SHOTS_WEIGHT = 0.15


def _float_val(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.replace("%", "").strip()
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_val(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def extract_player_rating(stats: dict[str, Any], games: dict[str, Any]) -> float | None:
    for block in (games, stats):
        if not isinstance(block, dict):
            continue
        rating = _float_val(block.get("rating"))
        if rating is not None and 4.0 <= rating <= 10.0:
            return round(rating, 2)
    return None


def extract_assists(stats: dict[str, Any]) -> int:
    goals_block = stats.get("goals") if isinstance(stats, dict) else {}
    if isinstance(goals_block, dict):
        return _int_val(goals_block.get("assists")) or 0
    return 0


def extract_key_passes(stats: dict[str, Any]) -> int:
    if not isinstance(stats, dict):
        return 0
    passes = stats.get("passes") or {}
    if isinstance(passes, dict):
        return _int_val(passes.get("key")) or _int_val(passes.get("key_passes")) or 0
    return 0


def extract_appearances(games: dict[str, Any]) -> int:
    if not isinstance(games, dict):
        return 0
    for key in ("appearences", "appearances", "played"):
        val = _int_val(games.get(key))
        if val and val > 0:
            return val
    return 0


def rating_trend(fixture_rating: float | None, average_rating: float | None) -> str | None:
    if fixture_rating is None or average_rating is None:
        return None
    delta = fixture_rating - average_rating
    if delta >= 0.35:
        return "rising"
    if delta <= -0.35:
        return "falling"
    return "stable"


def chance_creation_score(
    *,
    key_passes: int = 0,
    assists: int = 0,
    appearances: int = 1,
    per_match: bool = True,
) -> float:
    """0–100 chance creation index — conservative, capped."""
    apps = max(appearances, 1)
    kp = key_passes / apps if per_match else key_passes
    ast = assists / apps if per_match else assists
    raw = min(kp, 5.0) * 8.0 + min(ast, 3.0) * 10.0
    return round(min(raw, 100.0), 1)


def compute_conservative_player_score(row: dict[str, Any]) -> float:
    """Blend goals/shots with rating, assists, key passes — rating never dominates."""
    goals = float(row.get("goals") or 0)
    shots = float(row.get("shots") or 0)
    base = 40.0 + goals * _GOALS_WEIGHT * 10 + shots * _SHOTS_WEIGHT * 2

    rating = _float_val(row.get("player_rating"))
    if rating is not None:
        base += (rating - 6.5) * 10 * _RATING_WEIGHT

    assists = float(row.get("assists") or 0)
    base += assists * 4 * _ASSISTS_WEIGHT * 10

    kp = float(row.get("key_passes") or 0)
    base += kp * 2 * _KEY_PASSES_WEIGHT * 10

    trend = row.get("recent_rating_trend")
    if trend == "rising":
        base += 1.5
    elif trend == "falling":
        base -= 1.0

    cc = _float_val(row.get("chance_creation_score"))
    if cc is not None:
        base += cc * 0.05

    return round(min(max(base, 0.0), 99.0), 1)


def enrich_fixture_player_row(stats: dict[str, Any], games: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    rating = extract_player_rating(stats, games)
    assists = extract_assists(stats)
    key_passes = extract_key_passes(stats)
    minutes = _int_val(games.get("minutes")) or 0
    row = {**base, "assists": assists, "key_passes": key_passes, "minutes": minutes}
    if rating is not None:
        row["player_rating"] = rating
    row["chance_creation_score"] = chance_creation_score(
        key_passes=key_passes,
        assists=assists,
        appearances=1,
        per_match=False,
    )
    return row


def enrich_topscorer_row(stats: dict[str, Any], games: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    rating = extract_player_rating(stats, games)
    assists = extract_assists(stats)
    appearances = extract_appearances(games)
    minutes = _int_val(games.get("minutes")) or 0
    goals = int(base.get("goals") or 0)
    row = {
        **base,
        "assists": assists,
        "minutes": minutes,
        "appearances": appearances,
        "assists_per_match": round(assists / max(appearances, 1), 2),
        "recent_assists": assists,
    }
    if rating is not None:
        row["player_rating"] = rating
        row["average_rating"] = rating
    row["chance_creation_score"] = chance_creation_score(
        key_passes=0,
        assists=assists,
        appearances=appearances,
        per_match=True,
    )
    return row


def team_chance_creation_aggregate(rows: list[dict[str, Any]]) -> dict[str, float]:
    """Aggregate chance creation metrics for a team's player rows."""
    if not rows:
        return {"chance_creation_score": 0.0, "avg_rating": 0.0, "total_assists": 0.0}
    scores = [_float_val(r.get("chance_creation_score")) or 0 for r in rows]
    ratings = [_float_val(r.get("player_rating") or r.get("average_rating")) for r in rows]
    ratings = [r for r in ratings if r is not None]
    assists = sum(int(r.get("assists") or 0) for r in rows)
    return {
        "chance_creation_score": round(sum(scores) / len(scores), 1) if scores else 0.0,
        "avg_rating": round(sum(ratings) / len(ratings), 2) if ratings else 0.0,
        "total_assists": float(assists),
    }
