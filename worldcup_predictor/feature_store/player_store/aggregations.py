"""Rolling player feature aggregations (point-in-time before fixture)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.feature_store.player_store.models import PlayerMatchStatRecord, PlayerRollingFeatureRecord

ROLLING_FEATURE_KEYS = (
    "goals_last_3",
    "goals_last_5",
    "goals_last_10",
    "assists_last_5",
    "minutes_last_5",
    "starts_last_5",
    "shots_last_5",
    "shots_on_target_last_5",
    "xg_last_5",
    "xg_last_10",
    "goals_per_90",
    "xg_per_90",
    "starter_probability",
    "recent_form_score",
)


def _sum_int(values: list[int], n: int) -> int:
    return sum(values[-n:]) if values else 0


def _sum_optional_float(values: list[float | None], n: int) -> float | None:
    tail = [v for v in values[-n:] if v is not None]
    return round(sum(tail), 4) if tail else None


def _per_90(total: float | int, minutes: int) -> float | None:
    if minutes <= 0:
        return None
    return round(float(total) * 90.0 / float(minutes), 4)


def compute_rolling_features(
    history: list[PlayerMatchStatRecord],
    *,
    current: PlayerMatchStatRecord,
    lineup_context: dict[str, Any],
) -> PlayerRollingFeatureRecord:
    """Build rolling features from prior match stats (excludes current fixture)."""
    prior = sorted(
        [h for h in history if h.match_date and current.match_date and h.match_date < current.match_date],
        key=lambda r: r.match_date or "",
    )
    if not prior:
        prior = [h for h in history if h.sportmonks_fixture_id != current.sportmonks_fixture_id]

    goals = [h.goals for h in prior]
    assists = [h.assists for h in prior]
    minutes = [h.minutes for h in prior]
    starts = [1 if h.starter else 0 for h in prior]
    shots = [h.shots for h in prior]
    sot = [h.shots_on_target for h in prior]
    xg_vals = [h.xg for h in prior]

    goals_last_5 = _sum_int(goals, 5)
    minutes_last_5 = _sum_int(minutes, 5)
    xg_last_5 = _sum_optional_float(xg_vals, 5)
    xg_last_10 = _sum_optional_float(xg_vals, 10)

    goals_per_90 = _per_90(goals_last_5, minutes_last_5)
    xg_per_90 = _per_90(xg_last_5 or 0.0, minutes_last_5) if xg_last_5 is not None else None

    starts_last_5 = _sum_int(starts, 5)
    starter_probability = round(starts_last_5 / min(5, len(starts)), 4) if starts else None

    recent_form_score = None
    if prior:
        weighted = 0.0
        weight = 0.0
        for i, h in enumerate(reversed(prior[-5:])):
            w = float(i + 1)
            score = float(h.goals) * 3.0 + float(h.assists) * 2.0
            if h.xg is not None:
                score += float(h.xg) * 1.5
            weighted += score * w
            weight += w
        if weight > 0:
            recent_form_score = round(weighted / weight, 4)

    position_group = current.position
    if current.metadata:
        fp = current.metadata.get("formation_position")
        if fp and not position_group:
            from worldcup_predictor.feature_store.player_store.normalizers import position_group_from_formation_position

            position_group = position_group_from_formation_position(fp)

    return PlayerRollingFeatureRecord(
        sportmonks_fixture_id=current.sportmonks_fixture_id,
        player_id=current.player_id,
        captured_at=current.captured_at,
        source=current.source,
        fixture_id=current.fixture_id,
        team_id=current.team_id,
        league_id=current.league_id,
        season_id=current.season_id,
        match_date=current.match_date,
        goals_last_3=_sum_int(goals, 3),
        goals_last_5=goals_last_5,
        goals_last_10=_sum_int(goals, 10),
        assists_last_5=_sum_int(assists, 5),
        minutes_last_5=minutes_last_5,
        starts_last_5=starts_last_5,
        shots_last_5=_sum_int(shots, 5),
        shots_on_target_last_5=_sum_int(sot, 5),
        xg_last_5=xg_last_5,
        xg_last_10=xg_last_10,
        goals_per_90=goals_per_90,
        xg_per_90=xg_per_90,
        starter_probability=starter_probability,
        recent_form_score=recent_form_score,
        starter=current.starter,
        captain=current.captain,
        position=current.position,
        position_group=position_group,
        formation=lineup_context.get("formation"),
        goalkeeper_player_id=lineup_context.get("goalkeeper_player_id"),
        captain_player_id=lineup_context.get("captain_player_id"),
        lineup_available=bool(lineup_context.get("lineup_available")),
        lineup_quality_score=lineup_context.get("lineup_quality_score"),
        starting_xi=list(lineup_context.get("starting_xi") or []),
        bench=list(lineup_context.get("bench") or []),
        metadata={"history_matches": len(prior)},
    )


def build_fixture_rolling_features(
    match_stats: list[PlayerMatchStatRecord],
    *,
    lineup_context: dict[str, Any],
    player_histories: dict[int, list[PlayerMatchStatRecord]] | None = None,
) -> list[PlayerRollingFeatureRecord]:
    """Compute rolling features for all players in a fixture."""
    histories = player_histories or {}
    out: list[PlayerRollingFeatureRecord] = []
    for rec in match_stats:
        hist = histories.get(rec.player_id, [])
        out.append(compute_rolling_features(hist, current=rec, lineup_context=lineup_context))
    return out
