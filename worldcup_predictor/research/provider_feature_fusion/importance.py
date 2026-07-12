"""Feature importance from shadow fusion models."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from worldcup_predictor.research.provider_feature_fusion.constants import IMPORTANCE_PATH, PHASE
from worldcup_predictor.research.provider_feature_fusion.experiments import FEATURE_SETS, _prep_xy
from worldcup_predictor.research.wde_shadow_historical.constants import TEST_PARQUET, TRAIN_PARQUET


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute_feature_importance() -> dict[str, Any]:
    if not TRAIN_PARQUET.exists() or not TEST_PARQUET.exists():
        return {"phase": PHASE, "skipped_reason": "split_parquets_missing"}

    train_df = pd.read_parquet(TRAIN_PARQUET)
    holdout_df = pd.read_parquet(TEST_PARQUET)
    variant = "H_full_safe_fusion"
    features = FEATURE_SETS[variant]

    work_tr = train_df[train_df["label_1x2"].notna()].copy()
    work_ho = holdout_df[holdout_df["label_1x2"].notna()].copy()
    x_tr, _ = _prep_xy(work_tr, features)
    x_ho, _ = _prep_xy(work_ho, features)
    y_tr = work_tr["label_1x2"].astype(str).tolist()
    y_ho = work_ho["label_1x2"].astype(str).tolist()

    pipe = Pipeline(
        [
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=500, C=1.0, solver="lbfgs")),
        ]
    )
    pipe.fit(x_tr, y_tr)
    clf = pipe.named_steps["clf"]
    coef = clf.coef_
    classes = list(clf.classes_)

    perm = permutation_importance(
        pipe,
        x_ho,
        y_ho,
        n_repeats=5,
        random_state=42,
        scoring="accuracy",
    )

    coefficients = []
    for i, feat in enumerate(features):
        coefficients.append(
            {
                "feature": feat,
                "coef_by_class": {classes[j]: round(float(coef[j, i]), 4) for j in range(len(classes))},
            }
        )

    importance = []
    for i, feat in enumerate(features):
        importance.append(
            {
                "feature": feat,
                "permutation_mean": round(float(perm.importances_mean[i]), 4),
                "permutation_std": round(float(perm.importances_std[i]), 4),
            }
        )
    importance.sort(key=lambda x: x["permutation_mean"], reverse=True)

    report = {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "variant": variant,
        "holdout_rows": len(work_ho),
        "coefficients": coefficients,
        "permutation_importance": importance,
        "consistently_useful": [x["feature"] for x in importance if x["permutation_mean"] > 0.001],
        "unstable_or_redundant": [x["feature"] for x in importance if x["permutation_mean"] <= 0],
        "leakage_like": [],
        "provider_artifacts": [],
    }
    IMPORTANCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    IMPORTANCE_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
