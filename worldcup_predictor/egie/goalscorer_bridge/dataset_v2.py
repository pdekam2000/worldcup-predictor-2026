"""Goalscorer dataset v2 — ML features + bridged odds."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from worldcup_predictor.egie.goalscorer_bridge.models import FixtureBridge
from worldcup_predictor.egie.goalscorer_ml_shadow.features import load_dataset, prepare_features
from worldcup_predictor.egie.goalscorer_odds_mapping.models import MappedOddsSelection

ARTIFACT_DIR = Path("artifacts/phase54o_goalscorer_bridge")


def build_dataset_v2(
    bridges: list[FixtureBridge],
    mapped_odds: list[MappedOddsSelection],
    *,
    base_dataset_path: Path | str | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    base = load_dataset(base_dataset_path)
    bridged_sm_ids = {
        int(b.sportmonks_fixture_id)
        for b in bridges
        if b.sportmonks_fixture_id and b.bridge_confidence in ("HIGH", "MEDIUM", "LOW")
    }
    wc = base[base["sportmonks_fixture_id"].isin(bridged_sm_ids)].copy()
    if wc.empty:
        return pd.DataFrame(), {"status": "no_bridged_rows_in_base_dataset", "bridged_fixture_ids": len(bridged_sm_ids)}

    odds_df = pd.DataFrame([m.to_dict() for m in mapped_odds])
    if odds_df.empty:
        wc["implied_probability_anytime"] = None
        wc["implied_probability_first"] = None
        wc["odds_anytime"] = None
        return wc, {"status": "no_mapped_odds", "rows": len(wc)}

    if "label" not in odds_df.columns:
        odds_df["label"] = odds_df["market"].apply(
            lambda m: "First" if "first" in str(m).lower() else ("Last" if "last" in str(m).lower() else "Anytime")
        )

    # pivot odds by label
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

    out = wc.merge(anytime, on=["sportmonks_fixture_id", "player_id"], how="left")
    out = out.merge(first, on=["sportmonks_fixture_id", "player_id"], how="left")

    # attach api fixture id
    sm_to_api = {
        int(b.sportmonks_fixture_id): int(b.api_football_fixture_id)
        for b in bridges
        if b.sportmonks_fixture_id
    }
    out["api_football_fixture_id"] = out["sportmonks_fixture_id"].map(sm_to_api)
    out["has_goalscorer_odds"] = out["implied_probability_anytime"].notna().astype(int)

    meta = {
        "status": "ok",
        "rows": len(out),
        "fixtures": int(out["sportmonks_fixture_id"].nunique()),
        "rows_with_anytime_odds": int(out["implied_probability_anytime"].notna().sum()),
        "rows_with_first_odds": int(out["implied_probability_first"].notna().sum()),
    }
    return out, meta
