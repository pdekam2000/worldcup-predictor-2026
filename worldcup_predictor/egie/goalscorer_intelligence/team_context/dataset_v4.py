"""Build goalscorer dataset v4 with team context enrichment."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from worldcup_predictor.egie.goalscorer_intelligence.dataset_v3 import build_dataset_v3
from worldcup_predictor.egie.goalscorer_intelligence.team_context.features import enrich_team_context
from worldcup_predictor.egie.goalscorer_intelligence.team_context.models import TEAM_CONTEXT_COLUMNS

V3_DATASET = Path("artifacts/phase54q_goalscorer_generalization/goalscorer_dataset_v3.parquet")


def build_dataset_v4(v3: pd.DataFrame | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Join team context into goalscorer_dataset_v3 → v4."""
    if v3 is None:
        if V3_DATASET.is_file():
            base = pd.read_parquet(V3_DATASET)
        else:
            base, _ = build_dataset_v3()
    else:
        base = v3.copy()

    enriched = enrich_team_context(base)
    non_zero = {c: int((enriched[c] != 0).sum()) for c in TEAM_CONTEXT_COLUMNS}

    meta = {
        "status": "ok",
        "rows": len(enriched),
        "fixtures": int(enriched["sportmonks_fixture_id"].nunique()),
        "team_context_columns": list(TEAM_CONTEXT_COLUMNS),
        "non_zero_coverage": non_zero,
        "source": str(V3_DATASET) if V3_DATASET.is_file() else "build_dataset_v3",
    }
    return enriched, meta
