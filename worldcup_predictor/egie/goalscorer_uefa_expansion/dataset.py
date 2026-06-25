"""Build expanded dataset with UEFA odds overlay."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from worldcup_predictor.egie.goalscorer_bridge.dataset_v2 import build_dataset_v2
from worldcup_predictor.egie.goalscorer_bridge.models import FixtureBridge
from worldcup_predictor.egie.goalscorer_intelligence.dataset_v3 import build_dataset_v3
from worldcup_predictor.egie.goalscorer_odds_mapping.models import MappedOddsSelection
from worldcup_predictor.egie.goalscorer_uefa_expansion.models import UEFA_LEAGUE_IDS

V3_PATH = Path("artifacts/phase54q_goalscorer_generalization/goalscorer_dataset_v3.parquet")


def _attach_odds_to_base(
    base: pd.DataFrame,
    bridges: list[FixtureBridge],
    mapped_odds: list[MappedOddsSelection],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Overlay mapped odds onto full player store."""
    bridged_sm_ids = {
        int(b.sportmonks_fixture_id)
        for b in bridges
        if b.sportmonks_fixture_id and b.bridge_confidence in ("HIGH", "MEDIUM", "LOW")
    }

    odds_df = pd.DataFrame([m.to_dict() for m in mapped_odds])
    out = base.copy()

    if odds_df.empty:
        out["has_goalscorer_odds"] = 0
        return out, {"status": "no_mapped_odds", "fixtures_with_odds": 0}

    if "label" not in odds_df.columns:
        odds_df["label"] = odds_df["market"].apply(
            lambda m: "First" if "first" in str(m).lower() else ("Last" if "last" in str(m).lower() else "Anytime")
        )

    anytime = (
        odds_df[odds_df["label"].str.contains("Anytime", case=False, na=False)]
        .groupby(["sportmonks_fixture_id", "player_id"], as_index=False)
        .agg(implied_probability_anytime=("implied_probability", "mean"), odds_anytime=("odds", "mean"))
    )
    first = (
        odds_df[odds_df["label"].str.contains("First", case=False, na=False)]
        .groupby(["sportmonks_fixture_id", "player_id"], as_index=False)
        .agg(implied_probability_first=("implied_probability", "mean"), odds_first=("odds", "mean"))
    )

    for col in ("implied_probability_anytime", "implied_probability_first", "odds_anytime", "odds_first", "has_goalscorer_odds"):
        if col not in out.columns:
            out[col] = None

    out = out.drop(columns=[c for c in ("implied_probability_anytime", "implied_probability_first", "odds_anytime", "odds_first") if c in out.columns], errors="ignore")
    out = out.merge(anytime, on=["sportmonks_fixture_id", "player_id"], how="left")
    out = out.merge(first, on=["sportmonks_fixture_id", "player_id"], how="left")
    out["has_goalscorer_odds"] = out["implied_probability_anytime"].notna().astype(int)

    sm_to_api = {
        int(b.sportmonks_fixture_id): int(b.api_football_fixture_id)
        for b in bridges
        if b.sportmonks_fixture_id
    }
    out["api_football_fixture_id"] = out["sportmonks_fixture_id"].map(sm_to_api)

    uefa_ids = set(UEFA_LEAGUE_IDS.keys())
    uefa_with = int(out.loc[(out["league_id"].isin(uefa_ids)) & (out["has_goalscorer_odds"] == 1), "sportmonks_fixture_id"].nunique())
    wc_with = int(out.loc[(out["league_id"] == 732) & (out["has_goalscorer_odds"] == 1), "sportmonks_fixture_id"].nunique())
    total_with = int(out.loc[out["has_goalscorer_odds"] == 1, "sportmonks_fixture_id"].nunique())
    total_fx = int(out["sportmonks_fixture_id"].nunique())

    return out, {
        "status": "ok",
        "rows": len(out),
        "fixtures": total_fx,
        "fixtures_with_odds": total_with,
        "coverage_pct": round(total_with / total_fx, 4) if total_fx else 0.0,
        "wc_fixtures_with_odds": wc_with,
        "uefa_fixtures_with_odds": uefa_with,
        "rows_with_anytime_odds": int(out["implied_probability_anytime"].notna().sum()),
        "bridged_fixture_ids": len(bridged_sm_ids),
    }


def build_before_dataset() -> tuple[pd.DataFrame, dict[str, Any]]:
    if V3_PATH.is_file():
        df = pd.read_parquet(V3_PATH)
        meta = {
            "source": str(V3_PATH),
            "fixtures": int(df["sportmonks_fixture_id"].nunique()),
            "fixtures_with_odds": int(df.loc[df["has_goalscorer_odds"] == 1, "sportmonks_fixture_id"].nunique()),
        }
        return df, meta
    return build_dataset_v3()


def build_after_dataset(
    bridges: list[FixtureBridge],
    mapped_odds: list[MappedOddsSelection],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if V3_PATH.is_file():
        base = pd.read_parquet(V3_PATH)
    else:
        base, _ = build_dataset_v3()
    return _attach_odds_to_base(base, bridges, mapped_odds)
