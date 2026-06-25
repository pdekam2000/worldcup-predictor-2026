"""Build goalscorer dataset v3 — full player store + WC odds overlay."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from worldcup_predictor.egie.goalscorer_intelligence.generalization_models import LEAGUE_LABELS
from worldcup_predictor.egie.goalscorer_ml_shadow.features import load_dataset

V2_DATASET = Path("artifacts/phase54o_goalscorer_bridge/goalscorer_dataset_v2.parquet")
K_DATASET = Path("artifacts/phase54k_goalscorer_shadow/goalscorer_dataset.parquet")


def build_dataset_v3() -> tuple[pd.DataFrame, dict[str, Any]]:
    """Merge full 54K player store rows with WC bridged odds from v2."""
    base = load_dataset(K_DATASET)
    base["league_key"] = base["league_id"].map(lambda x: LEAGUE_LABELS.get(int(x), f"league_{x}"))

    odds_cols = [
        "implied_probability_anytime",
        "odds_anytime",
        "implied_probability_first",
        "odds_first",
        "api_football_fixture_id",
        "has_goalscorer_odds",
    ]

    if V2_DATASET.is_file():
        v2 = pd.read_parquet(V2_DATASET)
        avail = ["sportmonks_fixture_id", "player_id"] + [c for c in odds_cols if c in v2.columns]
        odds_slice = v2[avail].drop_duplicates(["sportmonks_fixture_id", "player_id"])
        out = base.merge(odds_slice, on=["sportmonks_fixture_id", "player_id"], how="left")
    else:
        out = base.copy()
        for c in odds_cols:
            out[c] = None

    out["has_goalscorer_odds"] = out.get("has_goalscorer_odds", pd.Series([0] * len(out))).fillna(0).astype(int)
    out["data_source"] = out["has_goalscorer_odds"].map(lambda x: "wc_odds_bridge" if x else "player_store_only")

    meta = {
        "status": "ok",
        "rows": len(out),
        "fixtures": int(out["sportmonks_fixture_id"].nunique()),
        "fixtures_with_odds": int(out.loc[out["has_goalscorer_odds"] == 1, "sportmonks_fixture_id"].nunique()),
        "by_league": {
            LEAGUE_LABELS.get(int(lid), str(lid)): int(cnt)
            for lid, cnt in out.groupby("league_id")["sportmonks_fixture_id"].nunique().items()
        },
        "meets_100_fixtures": int(out["sportmonks_fixture_id"].nunique()) >= 100,
        "meets_200_fixtures": int(out["sportmonks_fixture_id"].nunique()) >= 200,
    }
    return out, meta
