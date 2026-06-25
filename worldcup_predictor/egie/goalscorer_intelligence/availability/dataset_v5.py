"""Build goalscorer dataset v5 with availability enrichment."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from worldcup_predictor.egie.goalscorer_intelligence.availability.features import enrich_availability_features
from worldcup_predictor.egie.goalscorer_intelligence.availability.models import AVAILABILITY_COLUMNS

V4_DATASET = Path("artifacts/phase54r_team_context_goalscorer/goalscorer_dataset_v4.parquet")
V3_DATASET = Path("artifacts/phase54q_goalscorer_generalization/goalscorer_dataset_v3.parquet")


def build_dataset_v5(v4: pd.DataFrame | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    if v4 is None:
        if V4_DATASET.is_file():
            base = pd.read_parquet(V4_DATASET)
        elif V3_DATASET.is_file():
            base = pd.read_parquet(V3_DATASET)
        else:
            from worldcup_predictor.egie.goalscorer_intelligence.dataset_v3 import build_dataset_v3

            base, _ = build_dataset_v3()
    else:
        base = v4.copy()

    enriched = enrich_availability_features(base)
    non_zero = {c: int((enriched[c] != 0).sum()) for c in AVAILABILITY_COLUMNS}

    meta = {
        "status": "ok",
        "rows": len(enriched),
        "fixtures": int(enriched["sportmonks_fixture_id"].nunique()),
        "availability_columns": list(AVAILABILITY_COLUMNS),
        "non_zero_coverage": non_zero,
        "source": str(V4_DATASET) if V4_DATASET.is_file() else str(V3_DATASET),
    }
    return enriched, meta
