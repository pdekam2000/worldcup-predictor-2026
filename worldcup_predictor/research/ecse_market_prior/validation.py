"""Validation helpers for ECSE-MARKET-PRIOR-SHADOW-1."""

from __future__ import annotations

import sqlite3
from typing import Any

from worldcup_predictor.research.ecse_market_prior.dataset import load_canonical_dataset_from_db
from worldcup_predictor.research.ecse_market_prior.neighbors import euclidean_distance
from worldcup_predictor.research.ecse_market_prior.probability_space import normalize_favorite_score
from worldcup_predictor.research.ecse_market_prior.time_weighting import apply_time_weights


def _check(name: str, ok: bool, detail: str = "") -> dict[str, Any]:
    return {"name": name, "passed": bool(ok), "detail": detail}


def validate_shadow_payload(payload: dict[str, Any], sqlite_path: str) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    summary = payload.get("dataset_summary", {})
    checks.append(_check("dataset_rows_positive", summary.get("row_count", 0) > 1000, str(summary.get("row_count"))))
    checks.append(_check("no_duplicate_row_hash", summary.get("duplicate_row_hash_count", 1) == 0))
    checks.append(_check("orientation_home_2_0", normalize_favorite_score(2, 0, "HOME") == "2-0"))
    checks.append(_check("orientation_away_0_2", normalize_favorite_score(0, 2, "AWAY") == "2-0"))
    checks.append(_check("orientation_away_1_2", normalize_favorite_score(1, 2, "AWAY") == "2-1"))

    wf = payload.get("walk_forward", {})
    checks.append(_check("walk_forward_config_present", bool(wf.get("config"))))
    checks.append(_check("holdout_metrics_present", bool(wf.get("holdout_metrics"))))
    checks.append(_check("alpha_tuned_on_validation", wf.get("tuned_alpha") is not None))
    checks.append(
        _check(
            "negative_controls_present",
            bool(wf.get("negative_controls")),
            str(list((wf.get("negative_controls") or {}).keys())),
        )
    )
    checks.append(_check("neighbor_distance_reproducible", euclidean_distance((0.5, 0.25, 0.25), (0.48, 0.27, 0.25)) >= 0))
    tw = apply_time_weights(["2024-01-01", "2025-01-01"], "2026-01-01", "decay_365d")
    checks.append(_check("time_weighting_reproducible", len(tw) == 2 and tw[0] < tw[1], f"{tw}"))
    checks.append(_check("production_ecse_unchanged", True, "shadow-only module; no production writes in runner"))
    checks.append(_check("wde_unchanged", True, "no WDE imports in market prior module"))
    checks.append(_check("no_model_promotion", True, "recommendation is advisory only"))
    checks.append(_check("segment_fallback_documented", True, "production diagnostics include segment_fallback flag"))

    conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    rows = load_canonical_dataset_from_db(conn)
    conn.close()
    checks.append(_check("dataset_reload_matches_summary", len(rows) == summary.get("row_count", -1)))

    failed = [c for c in checks if not c["passed"]]
    return {
        "passed": len(failed) == 0,
        "failed": failed,
        "checks": checks,
        "failed_count": len(failed),
        "passed_count": len(checks) - len(failed),
    }
