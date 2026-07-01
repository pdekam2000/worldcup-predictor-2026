"""PHASE ECSE-X2-M6 — Cached lift model for live shadow runtime."""

from __future__ import annotations

import sqlite3
from typing import Any

from worldcup_predictor.research.ecse_x2_m2.prob_features import load_fixture_records
from worldcup_predictor.research.ecse_x2_m3.equation import compute_log_home_prob_phi
from worldcup_predictor.research.ecse_x2_m3.scorer import build_lift_model
from worldcup_predictor.research.ecse_x2_m4.segment import evaluate_target_segment

_cached_model: dict[str, Any] | None = None
_cached_train_n: int = 0


def get_lift_model(conn: sqlite3.Connection, *, force_refresh: bool = False) -> dict[str, Any] | None:
    global _cached_model, _cached_train_n
    if _cached_model is not None and not force_refresh:
        return _cached_model

    train_vals: list[dict[str, Any]] = []
    for row in load_fixture_records(conn):
        seg = evaluate_target_segment(row["probs"], coverage=row.get("feature_coverage_count"))
        if not seg["target_segment_passed"]:
            continue
        val = compute_log_home_prob_phi(row["probs"])
        if val is None:
            continue
        train_vals.append(row)

    model = build_lift_model(train_vals)
    _cached_model = model
    _cached_train_n = len(train_vals)
    return model


def lift_model_meta() -> dict[str, Any]:
    return {
        "train_n": _cached_train_n,
        "loaded": _cached_model is not None,
    }
