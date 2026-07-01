"""PHASE WDE-SHADOW-3 — Test-split segment analysis for O/U2.5 and BTTS shadow model."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from worldcup_predictor.research.wde_shadow_historical.backtest import _shadow_predictions
from worldcup_predictor.research.wde_shadow_historical.constants import TARGETS
from worldcup_predictor.research.wde_shadow_historical.split import load_split_dataframes
from worldcup_predictor.research.wde_shadow_historical.wde_shadow_baselines import accuracy, bookmaker_predictions

PHASE = "WDE-SHADOW-3"
SEGMENT_ARTIFACT = Path("artifacts/wde_shadow_market_segment_analysis.json")
DEFAULT_MODEL_DIR = Path("models/shadow/wde_historical_csv_shadow_20260701")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _confidence_bucket(conf: float) -> str:
    if conf < 0.50:
        return "below_0.50"
    if conf < 0.55:
        return "0.50_0.55"
    if conf < 0.60:
        return "0.55_0.60"
    if conf < 0.65:
        return "0.60_0.65"
    return "0.65_plus"


def _favorite_strength(row: pd.Series) -> str:
    probs = [
        float(row.get("implied_prob_home") or 0),
        float(row.get("implied_prob_draw") or 0),
        float(row.get("implied_prob_away") or 0),
    ]
    mx = max(probs) if probs else 0
    if mx >= 0.55:
        return "strong_favorite"
    if mx >= 0.42:
        return "moderate_favorite"
    return "balanced"


def _odds_spread_ou(row: pd.Series) -> str:
    o = float(row.get("implied_prob_over_2_5") or 0.5)
    u = float(row.get("implied_prob_under_2_5") or 0.5)
    spread = abs(o - u)
    if spread >= 0.20:
        return "wide_spread"
    if spread >= 0.10:
        return "medium_spread"
    return "tight_spread"


def _segment_accuracy(
    df: pd.DataFrame,
    y_true: list[str],
    shadow_preds: list,
    book_preds: list[str],
    mask: np.ndarray,
) -> dict[str, Any]:
    idx = np.where(mask)[0]
    if len(idx) == 0:
        return {"n": 0}
    yt = [y_true[i] for i in idx]
    sp = [shadow_preds[i] for i in idx]
    bp = [book_preds[i] for i in idx]
    return {
        "n": int(len(idx)),
        "shadow_accuracy": accuracy(yt, sp),
        "bookmaker_accuracy": accuracy(yt, bp),
        "shadow_minus_bookmaker": round((accuracy(yt, sp) or 0) - (accuracy(yt, bp) or 0), 4)
        if accuracy(yt, sp) is not None and accuracy(yt, bp) is not None
        else None,
    }


def _by_column(
    df: pd.DataFrame,
    col: str,
    y_true: list[str],
    shadow_preds: list,
    book_preds: list[str],
    *,
    top_n: int = 15,
    min_n: int = 30,
) -> dict[str, Any]:
    if col not in df.columns:
        return {}
    counts = df[col].fillna("unknown").astype(str).value_counts()
    out: dict[str, Any] = {}
    for key in counts.head(top_n).index:
        mask = (df[col].fillna("unknown").astype(str) == key).to_numpy()
        seg = _segment_accuracy(df, y_true, shadow_preds, book_preds, mask)
        if seg.get("n", 0) >= min_n:
            out[str(key)] = seg
    return out


def _by_confidence(
    proba: np.ndarray | None,
    classes: list[str],
    y_true: list[str],
    shadow_preds: list,
    book_preds: list[str],
) -> dict[str, Any]:
    if proba is None:
        return {}
    idx_map = {c: i for i, c in enumerate(classes)}
    buckets: dict[str, list[int]] = {}
    for i, (yt, pred) in enumerate(zip(y_true, shadow_preds)):
        if pred not in idx_map:
            continue
        conf = float(proba[i][idx_map[pred]])
        bucket = _confidence_bucket(conf)
        buckets.setdefault(bucket, []).append(i)
    out: dict[str, Any] = {}
    for bucket, indices in sorted(buckets.items()):
        mask = np.zeros(len(y_true), dtype=bool)
        mask[indices] = True
        out[bucket] = _segment_accuracy(
            pd.DataFrame({"_": range(len(y_true))}),
            y_true,
            shadow_preds,
            book_preds,
            mask,
        )
    return out


def _by_agreement(shadow_preds: list, book_preds: list[str], y_true: list[str]) -> dict[str, Any]:
    agree_mask = np.array([s == b for s, b in zip(shadow_preds, book_preds)])
    disagree_mask = ~agree_mask
    df = pd.DataFrame({"_": range(len(y_true))})
    return {
        "agrees_with_bookmaker": _segment_accuracy(df, y_true, shadow_preds, book_preds, agree_mask),
        "disagrees_with_bookmaker": _segment_accuracy(df, y_true, shadow_preds, book_preds, disagree_mask),
    }


def _by_year_month(df: pd.DataFrame, y_true: list[str], shadow_preds: list, book_preds: list[str]) -> dict[str, Any]:
    if "date" not in df.columns:
        return {}
    months = df["date"].fillna("").astype(str).str[:7]
    out: dict[str, Any] = {}
    for ym in sorted(months.unique()):
        if not ym or len(ym) < 7:
            continue
        mask = (months == ym).to_numpy()
        seg = _segment_accuracy(df, y_true, shadow_preds, book_preds, mask)
        if seg.get("n", 0) >= 20:
            out[ym] = seg
    return out


def analyze_market_segments(
    test_df: pd.DataFrame,
    model_dir: Path,
    *,
    markets: tuple[str, ...] = ("ou25", "btts"),
) -> dict[str, Any]:
    shadow_preds, shadow_proba, shadow_classes = _shadow_predictions(model_dir, test_df)
    book = bookmaker_predictions(test_df)

    result_markets: dict[str, Any] = {}
    for market in markets:
        col = TARGETS[market]
        y_true = test_df[col].tolist()
        sp = shadow_preds.get(market, [None] * len(test_df))
        bp = book[market]
        proba = shadow_proba.get(market)
        classes = shadow_classes.get(market, [])

        segments: dict[str, Any] = {
            "overall": _segment_accuracy(
                test_df,
                y_true,
                sp,
                bp,
                np.ones(len(test_df), dtype=bool),
            ),
            "by_confidence_bucket": _by_confidence(proba, classes, y_true, sp, bp),
            "by_competition": _by_column(test_df, "competition", y_true, sp, bp),
            "by_country": _by_column(test_df, "country", y_true, sp, bp),
            "by_league": _by_column(test_df, "league", y_true, sp, bp),
            "by_xg_availability": {
                "xg_available": _segment_accuracy(
                    test_df,
                    y_true,
                    sp,
                    bp,
                    test_df["expectedGoalsHome"].notna().to_numpy(),
                ),
                "xg_missing": _segment_accuracy(
                    test_df,
                    y_true,
                    sp,
                    bp,
                    test_df["expectedGoalsHome"].isna().to_numpy(),
                ),
            },
            "by_odds_spread": {},
            "by_favorite_strength": {},
            "by_shadow_bookmaker_agreement": _by_agreement(sp, bp, y_true),
            "by_year_month": _by_year_month(test_df, y_true, sp, bp),
        }

        spread_groups: dict[str, Any] = {}
        fav_groups: dict[str, Any] = {}
        for label in ("wide_spread", "medium_spread", "tight_spread"):
            mask = np.array([_odds_spread_ou(test_df.iloc[i]) == label for i in range(len(test_df))])
            spread_groups[label] = _segment_accuracy(test_df, y_true, sp, bp, mask)
        for label in ("strong_favorite", "moderate_favorite", "balanced"):
            mask = np.array([_favorite_strength(test_df.iloc[i]) == label for i in range(len(test_df))])
            fav_groups[label] = _segment_accuracy(test_df, y_true, sp, bp, mask)
        segments["by_odds_spread"] = spread_groups
        segments["by_favorite_strength"] = fav_groups

        best_segments: list[dict[str, Any]] = []
        worst_segments: list[dict[str, Any]] = []
        for group_name, group_data in segments.items():
            if not isinstance(group_data, dict):
                continue
            for seg_key, metrics in group_data.items():
                if not isinstance(metrics, dict) or metrics.get("n", 0) < 30:
                    continue
                delta = metrics.get("shadow_minus_bookmaker")
                if delta is None:
                    continue
                entry = {"segment": f"{group_name}/{seg_key}", **metrics}
                if delta >= 0.03:
                    best_segments.append(entry)
                elif delta <= -0.03:
                    worst_segments.append(entry)
        best_segments.sort(key=lambda x: -(x.get("shadow_minus_bookmaker") or 0))
        worst_segments.sort(key=lambda x: x.get("shadow_minus_bookmaker") or 0)

        result_markets[market] = {
            "segments": segments,
            "best_edge_segments": best_segments[:10],
            "avoid_segments": worst_segments[:10],
        }

    return {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "model_dir": str(model_dir),
        "test_rows": len(test_df),
        "markets": result_markets,
    }


def run_segment_analysis(model_dir: Path | None = None) -> dict[str, Any]:
    _, _, test_df = load_split_dataframes()
    model_dir = model_dir or DEFAULT_MODEL_DIR
    if test_df.empty:
        return {"phase": PHASE, "status": "skipped", "reason": "empty_test_set"}
    result = analyze_market_segments(test_df, model_dir)
    SEGMENT_ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    SEGMENT_ARTIFACT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result
