"""Part B — Bookmaker, historical, and current-WDE baselines for shadow backtest."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from typing import Any

import numpy as np
import pandas as pd

from worldcup_predictor.research.wde_shadow_historical.constants import CROSSWALK_PATH, TARGETS


def bookmaker_predictions(df: pd.DataFrame) -> dict[str, list[str]]:
    pick_1x2 = []
    for _, r in df.iterrows():
        probs = {
            "home_win": float(r.get("implied_prob_home") or 0),
            "draw": float(r.get("implied_prob_draw") or 0),
            "away_win": float(r.get("implied_prob_away") or 0),
        }
        pick_1x2.append(max(probs, key=probs.get))
    pick_ou = [
        "over_2_5" if float(r.get("implied_prob_over_2_5") or 0) >= float(r.get("implied_prob_under_2_5") or 0) else "under_2_5"
        for _, r in df.iterrows()
    ]
    pick_btts = [
        "yes" if float(r.get("implied_prob_btts_yes") or 0) >= float(r.get("implied_prob_btts_no") or 0) else "no"
        for _, r in df.iterrows()
    ]
    return {"1x2": pick_1x2, "ou25": pick_ou, "btts": pick_btts}


def bookmaker_probabilities(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """Return normalized implied probability matrices per market."""
    n = len(df)
    p_1x2 = np.column_stack(
        [
            df["implied_prob_home"].fillna(0).to_numpy(),
            df["implied_prob_draw"].fillna(0).to_numpy(),
            df["implied_prob_away"].fillna(0).to_numpy(),
        ]
    )
    row_sums = p_1x2.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1.0
    p_1x2 = p_1x2 / row_sums

    p_ou = np.column_stack(
        [
            df["implied_prob_over_2_5"].fillna(0.5).to_numpy(),
            df["implied_prob_under_2_5"].fillna(0.5).to_numpy(),
        ]
    )
    row_sums = p_ou.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1.0
    p_ou = p_ou / row_sums

    p_btts = np.column_stack(
        [
            df["implied_prob_btts_yes"].fillna(0.5).to_numpy(),
            df["implied_prob_btts_no"].fillna(0.5).to_numpy(),
        ]
    )
    row_sums = p_btts.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1.0
    p_btts = p_btts / row_sums

    return {"1x2": p_1x2, "ou25": p_ou, "btts": p_btts}


def _fit_historical_stats(train_df: pd.DataFrame) -> dict[str, Any]:
    global_modes = {
        "1x2": train_df["label_1x2"].mode().iloc[0] if len(train_df) else "home_win",
        "ou25": train_df["label_over_2_5"].mode().iloc[0] if len(train_df) else "under_2_5",
        "btts": train_df["label_btts"].mode().iloc[0] if len(train_df) else "no",
    }
    league_modes: dict[str, dict[str, str]] = defaultdict(dict)
    if "league" in train_df.columns:
        for league, grp in train_df.groupby("league"):
            if len(grp) < 20:
                continue
            league_modes[str(league)] = {
                "1x2": grp["label_1x2"].mode().iloc[0],
                "ou25": grp["label_over_2_5"].mode().iloc[0],
                "btts": grp["label_btts"].mode().iloc[0],
            }
    return {"global": global_modes, "league": dict(league_modes)}


def historical_baseline_predictions(df: pd.DataFrame, *, train_stats: dict[str, Any]) -> dict[str, list[str]]:
    """Leakage-safe: uses only pre-fitted train statistics."""
    global_modes = train_stats.get("global") or {}
    league_modes = train_stats.get("league") or {}
    out: dict[str, list[str]] = {"1x2": [], "ou25": [], "btts": []}
    for _, r in df.iterrows():
        league = str(r.get("league") or "")
        for market, col in TARGETS.items():
            pick = (league_modes.get(league) or {}).get(market) or global_modes.get(market)
            out[market].append(str(pick))
    return out


def _parse_wde_payload(payload: dict[str, Any]) -> dict[str, str | None]:
    out: dict[str, str | None] = {"1x2": None, "ou25": None, "btts": None}
    preds = payload.get("predictions") or payload.get("market_predictions") or payload
    if not isinstance(preds, dict):
        return out
    mapping = {
        "match_result": "1x2",
        "1x2": "1x2",
        "over_under_2_5": "ou25",
        "btts": "btts",
    }
    for key, slot in mapping.items():
        block = preds.get(key)
        if isinstance(block, dict):
            pick = block.get("pick") or block.get("selection") or block.get("prediction")
            if pick:
                out[slot] = str(pick).lower().replace(" ", "_")
    if out["1x2"] in ("home", "1"):
        out["1x2"] = "home_win"
    if out["1x2"] in ("away", "2"):
        out["1x2"] = "away_win"
    if out["ou25"] and "over" in out["ou25"]:
        out["ou25"] = "over_2_5"
    if out["ou25"] and "under" in out["ou25"]:
        out["ou25"] = "under_2_5"
    return out


def _load_crosswalk_map() -> dict[str, int]:
    if not CROSSWALK_PATH.exists():
        return {}
    try:
        cw = json.loads(CROSSWALK_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    cw_map: dict[str, int] = {}
    for row in cw.get("rows") or []:
        if row.get("fixture_id") and row.get("status") in (
            "MATCHED_HIGH_CONFIDENCE",
            "HIGH_CONFIDENCE",
            "MATCHED_LOW_CONFIDENCE",
        ):
            key = f"{row.get('home_team')}|{row.get('away_team')}|{str(row.get('event_date', ''))[:10]}"
            cw_map[key] = int(row["fixture_id"])
    return cw_map


def current_wde_predictions(
    conn: sqlite3.Connection | None,
    df: pd.DataFrame,
) -> tuple[dict[str, list[str | None]], dict[str, Any]]:
    """Return per-market picks and coverage metadata."""
    wde_preds: dict[str, list[str | None]] = {"1x2": [], "ou25": [], "btts": []}
    matched = 0
    cw_map = _load_crosswalk_map()
    for _, r in df.iterrows():
        key = f"{r.get('home_team')}|{r.get('away_team')}|{str(r.get('date', ''))[:10]}"
        fid = cw_map.get(key)
        pick: dict[str, str | None] = {"1x2": None, "ou25": None, "btts": None}
        if fid and conn is not None:
            row = conn.execute(
                "SELECT payload_json FROM worldcup_stored_predictions WHERE fixture_id = ? LIMIT 1",
                (fid,),
            ).fetchone()
            if row:
                try:
                    pick = _parse_wde_payload(json.loads(row["payload_json"]))
                    matched += 1
                except json.JSONDecodeError:
                    pass
        for m in wde_preds:
            wde_preds[m].append(pick.get(m))

    coverage = {
        "matched_predictions": matched,
        "total_rows": len(df),
        "coverage_rate": round(matched / len(df), 4) if len(df) else 0.0,
        "crosswalk_keys": len(cw_map),
        "note": "Small coverage expected — historical CSV rows rarely map to production fixtures",
    }
    return wde_preds, coverage


def accuracy(y_true: list[str], y_pred: list[str | None]) -> float | None:
    valid = [(a, b) for a, b in zip(y_true, y_pred) if b is not None]
    if not valid:
        return None
    return round(sum(1 for a, b in valid if a == b) / len(valid), 4)


def log_loss(y_true: list[str], proba: np.ndarray, classes: list[str]) -> float | None:
    idx = {c: i for i, c in enumerate(classes)}
    eps = 1e-15
    losses = []
    for yt, row in zip(y_true, proba):
        if yt not in idx:
            continue
        p = max(eps, min(1 - eps, float(row[idx[yt]])))
        losses.append(-np.log(p))
    return round(float(np.mean(losses)), 4) if losses else None


def brier_score_multiclass(y_true: list[str], proba: np.ndarray, classes: list[str]) -> float | None:
    idx = {c: i for i, c in enumerate(classes)}
    scores = []
    for yt, row in zip(y_true, proba):
        if yt not in idx:
            continue
        one_hot = np.zeros(len(classes))
        one_hot[idx[yt]] = 1.0
        scores.append(float(np.mean((row - one_hot) ** 2)))
    return round(float(np.mean(scores)), 4) if scores else None


def calibration_buckets(y_true: list[str], proba: np.ndarray, classes: list[str], *, n_bins: int = 5) -> list[dict[str, Any]]:
    idx = {c: i for i, c in enumerate(classes)}
    confidences: list[float] = []
    hits: list[int] = []
    for yt, row in zip(y_true, proba):
        if yt not in idx:
            continue
        pred_i = int(np.argmax(row))
        confidences.append(float(row[pred_i]))
        hits.append(1 if classes[pred_i] == yt else 0)
    if not confidences:
        return []
    conf = np.array(confidences)
    hit = np.array(hits)
    bins = np.linspace(0, 1, n_bins + 1)
    out: list[dict[str, Any]] = []
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        mask = (conf >= lo) & (conf < hi if i < n_bins - 1 else conf <= hi)
        if not mask.any():
            continue
        out.append(
            {
                "bin": f"{lo:.2f}-{hi:.2f}",
                "count": int(mask.sum()),
                "mean_confidence": round(float(conf[mask].mean()), 4),
                "accuracy": round(float(hit[mask].mean()), 4),
            }
        )
    return out


def confusion_matrix_dict(y_true: list[str], y_pred: list[str | None]) -> dict[str, Any]:
    labels = sorted(set(y_true))
    matrix: dict[str, dict[str, int]] = {a: {b: 0 for b in labels} for a in labels}
    for yt, yp in zip(y_true, y_pred):
        if yp is None or yt not in matrix or yp not in matrix[yt]:
            continue
        matrix[yt][yp] += 1
    return {"labels": labels, "matrix": matrix}
