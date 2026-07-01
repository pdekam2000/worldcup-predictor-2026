"""Part D — Backtest shadow WDE vs baselines and current production."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from joblib import load

from worldcup_predictor.research.wde_shadow_historical.constants import BACKTEST_ARTIFACT, PHASE, TARGETS
from worldcup_predictor.research.wde_shadow_historical.wde_shadow_baselines import (
    _fit_historical_stats,
    accuracy,
    bookmaker_predictions,
    brier_score_multiclass,
    calibration_buckets,
    confusion_matrix_dict,
    current_wde_predictions,
    historical_baseline_predictions,
    log_loss,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _shadow_predictions(model_dir: Path, df: pd.DataFrame) -> tuple[dict[str, list], dict[str, np.ndarray | None], dict[str, list[str]]]:
    encoder_path = model_dir / "feature_encoder.joblib"
    if not encoder_path.exists():
        return {}, {}, {}
    encoder = load(encoder_path)
    x, _ = encoder.transform(df)
    preds: dict[str, list] = {}
    proba: dict[str, np.ndarray | None] = {}
    classes: dict[str, list[str]] = {}
    for market in TARGETS:
        path = model_dir / f"shadow_{market}.joblib"
        if not path.exists():
            continue
        clf = load(path)
        preds[market] = clf.predict(x).tolist()
        classes[market] = list(clf.classes_)
        proba[market] = clf.predict_proba(x) if hasattr(clf, "predict_proba") else None
    return preds, proba, classes


def _confidence_accuracy(y_true: list[str], proba: np.ndarray | None, classes: list[str]) -> list[dict[str, Any]]:
    if proba is None or not len(y_true):
        return []
    idx = {c: i for i, c in enumerate(classes)}
    buckets: dict[str, list[tuple[float, int]]] = {"low": [], "mid": [], "high": []}
    for yt, row in zip(y_true, proba):
        if yt not in idx:
            continue
        pred_i = int(np.argmax(row))
        conf = float(row[pred_i])
        hit = 1 if classes[pred_i] == yt else 0
        if conf < 0.4:
            buckets["low"].append((conf, hit))
        elif conf < 0.6:
            buckets["mid"].append((conf, hit))
        else:
            buckets["high"].append((conf, hit))
    out = []
    for name, items in buckets.items():
        if not items:
            continue
        out.append(
            {
                "bucket": name,
                "count": len(items),
                "mean_confidence": round(float(np.mean([c for c, _ in items])), 4),
                "accuracy": round(float(np.mean([h for _, h in items])), 4),
            }
        )
    return out


def _market_eval(
    y_true: list[str],
    preds: list[str | None],
    proba: np.ndarray | None = None,
    classes: list[str] | None = None,
) -> dict[str, Any]:
    acc = accuracy(y_true, preds)
    out: dict[str, Any] = {
        "accuracy": acc,
        "n": sum(1 for p in preds if p is not None),
    }
    if proba is not None and classes:
        valid_idx = [i for i, p in enumerate(preds) if p is not None]
        if valid_idx:
            yt = [y_true[i] for i in valid_idx]
            pr = proba[valid_idx]
            out["log_loss"] = log_loss(yt, pr, classes)
            out["brier_score"] = brier_score_multiclass(yt, pr, classes)
            out["calibration_buckets"] = calibration_buckets(yt, pr, classes)
            out["confidence_vs_accuracy"] = _confidence_accuracy(yt, pr, classes)
    out["confusion_matrix"] = confusion_matrix_dict(y_true, preds)
    return out


def _segment_metrics(
    df: pd.DataFrame,
    y_true: dict[str, list[str]],
    shadow_preds: dict[str, list],
    book_preds: dict[str, list[str]],
) -> dict[str, Any]:
    segments: dict[str, Any] = {}

    def _by_col(col: str, top_n: int = 12) -> dict[str, Any]:
        if col not in df.columns:
            return {}
        counts = df[col].fillna("unknown").astype(str).value_counts()
        out: dict[str, Any] = {}
        for key in counts.head(top_n).index:
            mask = df[col].fillna("unknown").astype(str) == key
            idx = mask.to_numpy().nonzero()[0]
            if len(idx) == 0:
                continue
            out[str(key)] = {
                "n": int(len(idx)),
                "shadow_1x2_accuracy": accuracy(
                    [y_true["1x2"][i] for i in idx],
                    [shadow_preds.get("1x2", [None] * len(df))[i] for i in idx],
                ),
                "bookmaker_1x2_accuracy": accuracy(
                    [y_true["1x2"][i] for i in idx],
                    [book_preds["1x2"][i] for i in idx],
                ),
            }
        return out

    segments["by_competition"] = _by_col("competition")
    segments["by_country"] = _by_col("country")
    segments["by_league"] = _by_col("league")
    if "season_year" in df.columns:
        segments["by_season_year"] = _by_col("season_year", top_n=20)

    has_odds = df["implied_prob_home"].notna().to_numpy()
    has_xg = df["expectedGoalsHome"].notna().to_numpy()
    for label, mask in [("odds_available", has_odds), ("odds_missing", ~has_odds), ("xg_available", has_xg), ("xg_missing", ~has_xg)]:
        idx = np.where(mask)[0]
        if len(idx) == 0:
            continue
        segments[f"by_{label}"] = {
            "n": int(len(idx)),
            "shadow_1x2_accuracy": accuracy(
                [y_true["1x2"][i] for i in idx],
                [shadow_preds.get("1x2", [None] * len(df))[i] for i in idx],
            ),
            "bookmaker_1x2_accuracy": accuracy(
                [y_true["1x2"][i] for i in idx],
                [book_preds["1x2"][i] for i in idx],
            ),
        }
    return segments


def _evaluate_split(
    split_name: str,
    df: pd.DataFrame,
    model_dir: Path,
    train_stats: dict[str, Any],
    conn: sqlite3.Connection | None,
) -> dict[str, Any]:
    if df.empty:
        return {"split": split_name, "rows": 0, "status": "empty"}

    y = {m: df[col].tolist() for m, col in TARGETS.items()}
    shadow_preds, shadow_proba, shadow_classes = _shadow_predictions(model_dir, df)
    if not shadow_preds:
        book = bookmaker_predictions(df)
        shadow_preds = book

    book = bookmaker_predictions(df)
    hist = historical_baseline_predictions(df, train_stats=train_stats)
    wde_preds, wde_coverage = current_wde_predictions(conn, df)

    markets: dict[str, Any] = {}
    for market in TARGETS:
        markets[market] = {
            "shadow": _market_eval(
                y[market],
                shadow_preds.get(market, [None] * len(df)),
                shadow_proba.get(market),
                shadow_classes.get(market),
            ),
            "bookmaker_baseline": _market_eval(y[market], book[market]),
            "historical_baseline": _market_eval(y[market], hist[market]),
            "current_wde": _market_eval(y[market], wde_preds[market]),
        }

    return {
        "split": split_name,
        "rows": len(df),
        "markets": markets,
        "current_wde_coverage": wde_coverage,
        "segments": _segment_metrics(df, y, shadow_preds, book),
    }


def backtest_shadow_vs_current(
    conn: sqlite3.Connection | None,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame,
    train_df: pd.DataFrame,
    *,
    model_dir: Path,
) -> dict[str, Any]:
    train_stats = _fit_historical_stats(train_df)
    val_result = _evaluate_split("validation", val_df, model_dir, train_stats, conn)
    test_result = _evaluate_split("test", test_df, model_dir, train_stats, conn)

    def _extract(split_result: dict[str, Any], market: str, source: str) -> float | None:
        return (
            (split_result.get("markets") or {})
            .get(market, {})
            .get(source, {})
            .get("accuracy")
        )

    comparison = {
        "validation": {
            m: {
                "shadow": _extract(val_result, m, "shadow"),
                "bookmaker": _extract(val_result, m, "bookmaker_baseline"),
                "historical": _extract(val_result, m, "historical_baseline"),
                "current_wde": _extract(val_result, m, "current_wde"),
            }
            for m in TARGETS
        },
        "test": {
            m: {
                "shadow": _extract(test_result, m, "shadow"),
                "bookmaker": _extract(test_result, m, "bookmaker_baseline"),
                "historical": _extract(test_result, m, "historical_baseline"),
                "current_wde": _extract(test_result, m, "current_wde"),
            }
            for m in TARGETS
        },
    }

    result = {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "model_dir": str(model_dir),
        "validation": val_result,
        "test": test_result,
        "comparison": comparison,
        "note": "Current WDE compared only on crosswalked fixtures; coverage expected to be small.",
    }
    BACKTEST_ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    BACKTEST_ARTIFACT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result
