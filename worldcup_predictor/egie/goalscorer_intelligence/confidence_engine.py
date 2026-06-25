"""Confidence tier assignment for goalscorer intelligence."""

from __future__ import annotations

import pandas as pd

from worldcup_predictor.egie.goalscorer_intelligence.models import ConfidenceTier


def _tier_row(row: pd.Series) -> ConfidenceTier:
    ml_r = float(row.get("ml_rank") or 99)
    odds_r = float(row.get("odds_rank") or 99)
    starter = float(row.get("starter_probability") or 0)
    form = float(row.get("form_norm") or 0)
    lineup = str(row.get("lineup_status") or "")

    ml_odds_close = abs(ml_r - odds_r) <= 3
    both_top5 = ml_r <= 5 and odds_r <= 5
    strong_lineup = starter >= 0.6 or lineup == "starter"
    strong_form = form >= 0.5

    signals_agree = int(ml_odds_close) + int(strong_lineup) + int(strong_form)
    if both_top5 and strong_lineup and strong_form:
        return "A"
    if both_top5 or (ml_odds_close and strong_lineup):
        return "B"
    if signals_agree >= 2 or ml_r <= 8:
        return "C"
    return "D"


def assign_confidence_tiers(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["confidence_tier"] = out.apply(_tier_row, axis=1)
    out["is_surprise_candidate"] = (out["ml_rank"] <= 10) & (out["odds_rank"] >= 8)
    out["is_value_pick"] = out["value_gap"] >= 5.0
    return out


def confidence_summary(df: pd.DataFrame) -> dict[str, int]:
    if "confidence_tier" not in df.columns:
        return {}
    return {str(k): int(v) for k, v in df["confidence_tier"].value_counts().items()}
