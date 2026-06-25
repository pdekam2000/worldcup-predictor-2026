"""Build historical-safe xG features from Sportmonks feature store."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.feature_store.aggregations import compute_team_rolling_xg
from worldcup_predictor.feature_store.repository import SportmonksXgRepository

XG_FEATURE_NAMES: tuple[str, ...] = (
    "home_recent_xg",
    "away_recent_xg",
    "home_recent_xga",
    "away_recent_xga",
    "xg_difference",
    "attack_strength_difference",
    "defensive_weakness_difference",
    "xg_momentum_difference",
    "rolling_xg_3_home",
    "rolling_xg_3_away",
    "rolling_xg_5_home",
    "rolling_xg_5_away",
    "rolling_xg_10_home",
    "rolling_xg_10_away",
    "rolling_xga_3_home",
    "rolling_xga_3_away",
    "rolling_xga_5_home",
    "rolling_xga_5_away",
    "rolling_xga_10_home",
    "rolling_xga_10_away",
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


class XgFeatureBuilder:
    """
    Read fs_sportmonks_xg_fixture_summary and emit pre-match-safe xG features.

    CRITICAL: Never uses current-fixture post-match xG (home_xg/away_xg on same row).
    Rolling features are computed only from strictly prior matches per team.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.repo = SportmonksXgRepository(self.settings)

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
        is_home = summary.get("home_team_id") == team_id
        is_away = summary.get("away_team_id") == team_id
        if not is_home and not is_away:
            return None
        xg_for = summary.get("home_xg") if is_home else summary.get("away_xg")
        xg_against = summary.get("away_xg") if is_home else summary.get("home_xg")
        if xg_for is None and xg_against is None:
            return None
        return {
            "sportmonks_fixture_id": summary.get("sportmonks_fixture_id"),
            "match_started_at": summary.get("match_started_at"),
            "xg_for": float(xg_for) if xg_for is not None else None,
            "xg_against": float(xg_against) if xg_against is not None else None,
            "is_home": is_home,
        }

    def build_chronological_features(
        self,
        summaries: list[dict[str, Any]] | None = None,
    ) -> dict[int, dict[str, Any]]:
        """Map sportmonks_fixture_id → pre-match xG feature dict."""
        ordered = summaries if summaries is not None else self.load_ordered_summaries()
        history_by_team: dict[int, list[dict[str, Any]]] = {}
        out: dict[int, dict[str, Any]] = {}

        for row in ordered:
            sm_id = int(row.get("sportmonks_fixture_id") or 0)
            home_id = row.get("home_team_id")
            away_id = row.get("away_team_id")
            if sm_id <= 0 or not home_id or not away_id:
                continue

            home_hist = history_by_team.get(int(home_id), [])
            away_hist = history_by_team.get(int(away_id), [])

            home_r3 = compute_team_rolling_xg(home_hist, window=3)
            home_r5 = compute_team_rolling_xg(home_hist, window=5)
            home_r10 = compute_team_rolling_xg(home_hist, window=10)
            away_r3 = compute_team_rolling_xg(away_hist, window=3)
            away_r5 = compute_team_rolling_xg(away_hist, window=5)
            away_r10 = compute_team_rolling_xg(away_hist, window=10)

            home_recent_xg = home_r5.get("rolling_xg_for")
            away_recent_xg = away_r5.get("rolling_xg_for")
            home_recent_xga = home_r5.get("rolling_xga")
            away_recent_xga = away_r5.get("rolling_xga")

            xg_diff = None
            if home_recent_xg is not None and away_recent_xg is not None:
                xg_diff = round(float(home_recent_xg) - float(away_recent_xg), 4)

            atk_diff = xg_diff
            def_diff = None
            if home_recent_xga is not None and away_recent_xga is not None:
                def_diff = round(float(away_recent_xga) - float(home_recent_xga), 4)

            mom_diff = None
            home_mom = home_r5.get("xg_momentum")
            away_mom = away_r5.get("xg_momentum")
            if home_mom is not None and away_mom is not None:
                mom_diff = round(float(home_mom) - float(away_mom), 4)

            features = {
                "home_recent_xg": home_recent_xg,
                "away_recent_xg": away_recent_xg,
                "home_recent_xga": home_recent_xga,
                "away_recent_xga": away_recent_xga,
                "xg_difference": xg_diff,
                "attack_strength_difference": atk_diff,
                "defensive_weakness_difference": def_diff,
                "xg_momentum_difference": mom_diff,
                "rolling_xg_3_home": home_r3.get("rolling_xg_for"),
                "rolling_xg_3_away": away_r3.get("rolling_xg_for"),
                "rolling_xg_5_home": home_r5.get("rolling_xg_for"),
                "rolling_xg_5_away": away_r5.get("rolling_xg_for"),
                "rolling_xg_10_home": home_r10.get("rolling_xg_for"),
                "rolling_xg_10_away": away_r10.get("rolling_xg_for"),
                "rolling_xga_3_home": home_r3.get("rolling_xga"),
                "rolling_xga_3_away": away_r3.get("rolling_xga"),
                "rolling_xga_5_home": home_r5.get("rolling_xga"),
                "rolling_xga_5_away": away_r5.get("rolling_xga"),
                "rolling_xga_10_home": home_r10.get("rolling_xga"),
                "rolling_xga_10_away": away_r10.get("rolling_xga"),
                "xg_available": any(
                    v is not None
                    for v in (home_recent_xg, away_recent_xg, home_recent_xga, away_recent_xga)
                ),
                "xg_history_matches_home": home_r5.get("matches_used") or 0,
                "xg_history_matches_away": away_r5.get("matches_used") or 0,
            }
            out[sm_id] = features

            # Append current match to history AFTER feature extraction (no leakage)
            for team_id in (int(home_id), int(away_id)):
                hist_row = self._team_history_row(row, team_id)
                if hist_row:
                    history_by_team.setdefault(team_id, []).append(hist_row)

        return out

    def build_for_fixture(self, sportmonks_fixture_id: int) -> dict[str, Any]:
        feats = self.build_chronological_features()
        return feats.get(int(sportmonks_fixture_id), {"xg_available": False})

    @staticmethod
    def records_for_fixture(sportmonks_fixture_id: int, settings: Settings | None = None) -> list[dict[str, Any]]:
        repo = SportmonksXgRepository(settings or get_settings())
        return repo.get_records_for_fixture(sportmonks_fixture_id)
