"""Build player availability features for goalscorer dataset v5."""

from __future__ import annotations

import pandas as pd

from worldcup_predictor.egie.goalscorer_intelligence.availability.models import AVAILABILITY_COLUMNS


def _rolling_minutes_last_3(df: pd.DataFrame) -> pd.Series:
    """Leakage-safe sum of match minutes from prior 3 appearances per player."""
    work = df[["player_id", "match_date", "sportmonks_fixture_id", "match_minutes"]].copy()
    work["match_date"] = pd.to_datetime(work["match_date"], errors="coerce")
    work["match_minutes"] = pd.to_numeric(work["match_minutes"], errors="coerce").fillna(0)
    work = work.sort_values(["player_id", "match_date", "sportmonks_fixture_id"])

    out = pd.Series(0.0, index=df.index, dtype=float)
    for player_id, grp in work.groupby("player_id"):
        mins = grp["match_minutes"].values
        rolled = [0.0] * len(mins)
        for i in range(1, len(mins)):
            rolled[i] = float(sum(mins[max(0, i - 3) : i]))
        out.loc[grp.index] = rolled
    return out


def enrich_availability_features(df: pd.DataFrame) -> pd.DataFrame:
    """Derive availability intelligence columns from player-fixture history."""
    out = df.copy()
    out["match_date"] = pd.to_datetime(out.get("match_date"), errors="coerce")

    status = out.get("lineup_status", pd.Series(["unknown"] * len(out))).fillna("unknown").astype(str)
    out["lineup_confirmed"] = (
        (out.get("lineup_available", True).fillna(False).astype(bool)) & status.isin(["starter", "bench"])
    ).astype(int)

    out["starter_probability"] = pd.to_numeric(out.get("starter_probability"), errors="coerce").fillna(0.0).clip(0, 1)
    out["minutes_last_5"] = pd.to_numeric(out.get("minutes_last_5"), errors="coerce").fillna(0).astype(int)
    out["minutes_last_3"] = _rolling_minutes_last_3(out).round(0).astype(int)

    m5 = out["minutes_last_5"].astype(float)
    m3 = out["minutes_last_3"].astype(float)
    out["minutes_trend"] = ((m3 / 3.0) - (m5 / 5.0)).fillna(0.0).round(4)

    out["bench_probability"] = (1.0 - out["starter_probability"]).clip(0, 1).round(4)
    out["captain"] = out.get("captain", False).fillna(False).astype(int)

    starts5 = pd.to_numeric(out.get("starts_last_5"), errors="coerce").fillna(0)
    out["suspended_flag"] = (
        (out["minutes_last_5"] == 0) & (starts5 >= 2) & (out["starter_probability"] >= 0.4)
    ).astype(int)

    out["injury_flag"] = (
        (out["starter_probability"] >= 0.6)
        & (out["minutes_last_5"] < 90)
        & (status == "bench")
    ).astype(int)

    out["returned_recently"] = (
        (starts5 >= 1)
        & (out["minutes_trend"] > 5)
        & (m3 > 0)
        & (out["lineup_confirmed"] == 1)
    ).astype(int)

    minutes_norm = (m5 / 450.0).clip(0, 1)
    out["availability_score"] = (
        0.35 * out["starter_probability"]
        + 0.25 * out["lineup_confirmed"]
        + 0.20 * minutes_norm
        + 0.10 * (1.0 - out["bench_probability"])
        + 0.05 * (1.0 - out["injury_flag"])
        + 0.05 * (1.0 - out["suspended_flag"])
    ).round(4)

    for col in AVAILABILITY_COLUMNS:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)

    return out
