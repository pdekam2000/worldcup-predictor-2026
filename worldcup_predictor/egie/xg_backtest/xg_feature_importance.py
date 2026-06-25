"""Phase 54F-6 — xG feature importance and stability analysis."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from worldcup_predictor.egie.xg_backtest.xg_feature_builder import XG_FEATURE_NAMES

ARTIFACT_DIR = Path("artifacts/phase54f6_expanded_dataset")


def analyze_feature_importance(ab_results: dict[str, Any]) -> dict[str, Any]:
    """Rank xG features by Arm B importance and compare deltas vs Arm A."""
    markets = ab_results.get("markets") or {}
    pooled_b: dict[str, float] = {}
    per_market: dict[str, dict[str, float]] = {}

    for market, block in markets.items():
        arm_b = block.get("arm_b_xg") or {}
        imp = arm_b.get("feature_importance") or {}
        xg_imp = {k: float(v) for k, v in imp.items() if k in XG_FEATURE_NAMES}
        per_market[market] = xg_imp
        for feat, val in xg_imp.items():
            pooled_b[feat] = pooled_b.get(feat, 0.0) + val

    ranked = sorted(pooled_b.items(), key=lambda x: x[1], reverse=True)
    total = sum(pooled_b.values()) or 1.0

    stable: list[str] = []
    noisy: list[str] = []
    for feat, val in ranked:
        appearances = sum(1 for m in per_market.values() if feat in m and m[feat] > 0.01)
        if appearances >= 2 and val / total >= 0.05:
            stable.append(feat)
        elif appearances <= 1 or val / total < 0.02:
            noisy.append(feat)

    deltas: dict[str, dict[str, float | None]] = {}
    for market, block in markets.items():
        deltas[market] = block.get("delta") or {}

    helps_markets: list[str] = []
    hurts_markets: list[str] = []
    for market, d in deltas.items():
        acc = d.get("accuracy")
        if acc is None:
            continue
        if float(acc) > 0:
            helps_markets.append(market)
        elif float(acc) < 0:
            hurts_markets.append(market)

    return {
        "ranked_xg_features": [
            {"feature": k, "importance_sum": round(v, 6), "share_pct": round(100 * v / total, 2)}
            for k, v in ranked
        ],
        "strongest_features": [k for k, _ in ranked[:5]],
        "stable_features": stable,
        "noisy_features": noisy,
        "markets_xg_helps": helps_markets,
        "markets_xg_hurts": hurts_markets,
        "per_market_xg_importance": per_market,
        "per_market_delta": deltas,
    }


def save_feature_analysis(ab_path: Path | None = None, out_dir: Path | None = None) -> dict[str, Any]:
    out = out_dir or ARTIFACT_DIR
    out.mkdir(parents=True, exist_ok=True)
    path = ab_path or out / "ab_test_results.json"
    if not path.is_file():
        return {"error": "ab_results_missing"}
    ab = json.loads(path.read_text(encoding="utf-8"))
    analysis = analyze_feature_importance(ab)
    (out / "feature_importance_analysis.json").write_text(json.dumps(analysis, indent=2), encoding="utf-8")
    return analysis
