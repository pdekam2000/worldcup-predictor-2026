"""Build historical-safe and in-play pressure features from feature store."""

from __future__ import annotations

from datetime import datetime
from statistics import mean
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.feature_store.pressure_store.aggregations import compute_fixture_pressure_features
from worldcup_predictor.feature_store.pressure_store.models import SportmonksPressureRecord
from worldcup_predictor.feature_store.pressure_store.repository import SportmonksPressureRepository

PRESSURE_FEATURE_NAMES: tuple[str, ...] = (
    "home_avg_pressure",
    "away_avg_pressure",
    "pressure_difference",
    "pressure_first_15_home",
    "pressure_first_15_away",
    "pressure_first_30_home",
    "pressure_first_30_away",
    "pressure_spike_count_home",
    "pressure_spike_count_away",
    "pressure_dominance",
    "pressure_momentum",
    "pressure_swing",
    "pressure_before_first_goal_home",
    "pressure_before_first_goal_away",
    "pressure_last_5_home",
    "pressure_last_5_away",
    "pressure_last_10_home",
    "pressure_last_10_away",
)

PRESSURE_LITE_FEATURES: tuple[str, ...] = (
    "pressure_first_15_home",
    "pressure_first_15_away",
    "pressure_dominance",
    "pressure_momentum",
    "pressure_swing",
)

PRESSURE_MINUTE_PROXY_FEATURES: tuple[str, ...] = (
    "pressure_first_15_home",
    "pressure_first_15_away",
    "pressure_first_30_home",
    "pressure_first_30_away",
    "pressure_last_5_home",
    "pressure_last_5_away",
    "pressure_last_10_home",
    "pressure_last_10_away",
    "pressure_before_first_goal_home",
    "pressure_before_first_goal_away",
)

PRESSURE_WITHOUT_MINUTE_PROXY: tuple[str, ...] = tuple(
    f for f in PRESSURE_FEATURE_NAMES if f not in PRESSURE_MINUTE_PROXY_FEATURES
)

MINUTE_ONLY_FEATURES: tuple[str, ...] = (
    "current_minute",
    "elapsed_minute",
    "minute_normalized",
    "goals_before_home",
    "goals_before_away",
    "score_diff",
    "goal_index",
)

FORBIDDEN_PREMATCH_KEYS = frozenset(
    {
        "pressure_row_count",
        "unique_minutes",
    }
)


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _avg(values: list[float]) -> float | None:
    return round(mean(values), 4) if values else None


def _team_side_metrics(features_json: dict[str, Any], side: str) -> dict[str, float | None]:
    block = features_json.get(side) or {}
    return {
        "avg_pressure": block.get("average_pressure"),
        "pressure_first_15": block.get("pressure_first_15"),
        "pressure_first_30": block.get("pressure_first_30"),
        "pressure_spike_count": block.get("pressure_spike_count"),
        "pressure_dominance": block.get("pressure_dominance"),
        "pressure_momentum": block.get("pressure_momentum"),
        "pressure_swing": block.get("pressure_swing"),
        "pressure_before_first_goal": block.get("pressure_before_first_goal"),
        "pressure_last_5": block.get("pressure_last_5"),
        "pressure_last_10": block.get("pressure_last_10"),
    }


def _flatten_match_features(
    home: dict[str, float | None],
    away: dict[str, float | None],
    *,
    match_block: dict[str, Any] | None = None,
) -> dict[str, Any]:
    home_avg = home.get("avg_pressure")
    away_avg = away.get("avg_pressure")
    diff = None
    if home_avg is not None and away_avg is not None:
        diff = round(float(home_avg) - float(away_avg), 4)
    dom = home.get("pressure_dominance")
    if dom is None and home_avg is not None and away_avg is not None:
        total = float(home_avg) + float(away_avg)
        dom = round(float(home_avg) / total, 4) if total > 0 else None
    mom = home.get("pressure_momentum")
    if mom is None and home.get("pressure_momentum") is not None and away.get("pressure_momentum") is not None:
        mom = round(float(home["pressure_momentum"]) - float(away["pressure_momentum"]), 4)
    swing = None
    if home.get("pressure_swing") is not None and away.get("pressure_swing") is not None:
        swing = round(max(float(home["pressure_swing"]), float(away["pressure_swing"])), 4)
    return {
        "home_avg_pressure": home_avg,
        "away_avg_pressure": away_avg,
        "pressure_difference": diff,
        "pressure_first_15_home": home.get("pressure_first_15"),
        "pressure_first_15_away": away.get("pressure_first_15"),
        "pressure_first_30_home": home.get("pressure_first_30"),
        "pressure_first_30_away": away.get("pressure_first_30"),
        "pressure_spike_count_home": home.get("pressure_spike_count"),
        "pressure_spike_count_away": away.get("pressure_spike_count"),
        "pressure_dominance": dom,
        "pressure_momentum": mom,
        "pressure_swing": swing,
        "pressure_before_first_goal_home": home.get("pressure_before_first_goal"),
        "pressure_before_first_goal_away": away.get("pressure_before_first_goal"),
        "pressure_last_5_home": home.get("pressure_last_5"),
        "pressure_last_5_away": away.get("pressure_last_5"),
        "pressure_last_10_home": home.get("pressure_last_10"),
        "pressure_last_10_away": away.get("pressure_last_10"),
    }


def _rolling_team_pressure(history: list[dict[str, Any]], window: int = 5) -> dict[str, float | None]:
    if not history:
        return {}
    rows = history[-window:]
    keys = (
        "avg_pressure",
        "pressure_first_15",
        "pressure_first_30",
        "pressure_spike_count",
        "pressure_dominance",
        "pressure_momentum",
        "pressure_swing",
        "pressure_before_first_goal",
        "pressure_last_5",
        "pressure_last_10",
    )
    out: dict[str, float | None] = {}
    for k in keys:
        vals = [float(r[k]) for r in rows if r.get(k) is not None]
        if k == "pressure_spike_count":
            out[k] = round(sum(vals), 4) if vals else None
        else:
            out[k] = _avg(vals)
    out["matches_used"] = len(rows)
    return out


class PressureFeatureBuilder:
    """Pre-match rolling + in-play minute-safe pressure features."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.repo = SportmonksPressureRepository(self.settings)

    def load_ordered_summaries(self, *, league_id: int | None = None) -> list[dict[str, Any]]:
        rows = self.repo.list_fixture_summaries(league_id=league_id)
        return sorted(
            rows,
            key=lambda r: (
                _parse_dt(r.get("match_started_at")) or datetime.min,
                int(r.get("sportmonks_fixture_id") or 0),
            ),
        )

    def _team_history_row(self, summary: dict[str, Any], team_id: int) -> dict[str, Any] | None:
        fj = summary.get("features_json") or {}
        if isinstance(fj, str):
            import json

            try:
                fj = json.loads(fj)
            except json.JSONDecodeError:
                fj = {}
        side = "home" if summary.get("home_team_id") == team_id else "away"
        if summary.get("home_team_id") != team_id and summary.get("away_team_id") != team_id:
            return None
        metrics = _team_side_metrics(fj, side)
        if metrics.get("avg_pressure") is None:
            return None
        return {
            "sportmonks_fixture_id": summary.get("sportmonks_fixture_id"),
            "match_started_at": summary.get("match_started_at"),
            **metrics,
        }

    def build_prematch_chronological_features(
        self,
        summaries: list[dict[str, Any]] | None = None,
        *,
        window: int = 5,
    ) -> dict[int, dict[str, Any]]:
        """Rolling pressure from strictly prior fixtures per team (no current-match leakage)."""
        ordered = summaries if summaries is not None else self.load_ordered_summaries()
        history_by_team: dict[int, list[dict[str, Any]]] = {}
        out: dict[int, dict[str, Any]] = {}

        for row in ordered:
            sm_id = int(row.get("sportmonks_fixture_id") or 0)
            home_id = row.get("home_team_id")
            away_id = row.get("away_team_id")
            if sm_id <= 0 or not home_id or not away_id:
                continue

            home_roll = _rolling_team_pressure(history_by_team.get(int(home_id), []), window=window)
            away_roll = _rolling_team_pressure(history_by_team.get(int(away_id), []), window=window)

            features = _flatten_match_features(home_roll, away_roll)
            features["pressure_available"] = bool(
                home_roll.get("matches_used", 0) >= 1 and away_roll.get("matches_used", 0) >= 1
            )
            features["pressure_history_matches_home"] = int(home_roll.get("matches_used") or 0)
            features["pressure_history_matches_away"] = int(away_roll.get("matches_used") or 0)
            out[sm_id] = features

            for team_id in (int(home_id), int(away_id)):
                hist_row = self._team_history_row(row, team_id)
                if hist_row:
                    history_by_team.setdefault(team_id, []).append(hist_row)

        return out

    def build_inplay_features_before_minute(
        self,
        sportmonks_fixture_id: int,
        *,
        before_minute: int,
        home_team_id: int,
        away_team_id: int,
    ) -> dict[str, Any]:
        """Aggregate pressure rows with minute < before_minute only."""
        raw_rows = self.repo.get_records_for_fixture(sportmonks_fixture_id)
        records = [
            SportmonksPressureRecord(
                sportmonks_fixture_id=sportmonks_fixture_id,
                pressure_row_id=int(r["pressure_row_id"]),
                participant_id=int(r["participant_id"]),
                minute=int(r["minute"]),
                pressure_value=float(r["pressure_value"]),
                captured_at=r["captured_at"],
                team_id=int(r.get("team_id") or r["participant_id"]),
            )
            for r in raw_rows
            if int(r.get("minute") or -1) < before_minute
        ]
        if not records:
            return {"pressure_available": False}
        feats = compute_fixture_pressure_features(
            records,
            home_participant_id=home_team_id,
            away_participant_id=away_team_id,
            first_goal_minute=before_minute,
        )
        home = _team_side_metrics(feats, "home")
        away = _team_side_metrics(feats, "away")
        flat = _flatten_match_features(home, away, match_block=feats.get("match"))
        flat["pressure_available"] = True
        flat["inplay_before_minute"] = before_minute
        return flat
