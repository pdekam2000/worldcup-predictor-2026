"""Build ML feature vectors from database records."""

from __future__ import annotations

from typing import Any

import pandas as pd

from worldcup_predictor.database.repository import FootballIntelligenceRepository


FEATURE_COLUMNS = [
    "data_quality",
    "prediction_quality",
    "confidence",
    "lineups_available",
    "has_odds",
    "has_xg",
    "no_bet_flag",
    "is_preliminary",
    "home_advantage",
]


class FeatureBuilder:
    """Construct tabular features for market model training."""

    def __init__(self, repository: FootballIntelligenceRepository | None = None) -> None:
        self._repo = repository or FootballIntelligenceRepository()

    def build_training_frame(self, *, competition_key: str | None = None) -> pd.DataFrame:
        rows = self._repo.fetch_training_rows(competition_key=competition_key)
        records: list[dict[str, Any]] = []
        for row in rows:
            fid = int(row["fixture_id"])
            records.append(
                {
                    "prediction_id": row["prediction_id"],
                    "market": row["market"],
                    "label": 1 if row["result"] == "correct" else 0,
                    "data_quality": float(row["data_quality"]),
                    "prediction_quality": float(row["prediction_quality"]),
                    "confidence": float(row["confidence"]),
                    "lineups_available": int(row["lineups_available"]),
                    "has_odds": int(self._repo.has_odds_snapshot(fid)),
                    "has_xg": int(self._repo.has_xg_snapshot(fid)),
                    "no_bet_flag": int(row["no_bet_flag"]),
                    "is_preliminary": int(row["is_preliminary"]),
                    "home_advantage": 1,
                }
            )
        return pd.DataFrame(records)

    def feature_matrix(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=FEATURE_COLUMNS)
        return df[FEATURE_COLUMNS].fillna(0.0)
