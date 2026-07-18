"""Extended metrics for Phase 3B (RPS, ECE, exact-score NLL, xG errors)."""

from __future__ import annotations

import math
from typing import Any, Sequence

from worldcup_predictor.challenger.backtest.metrics import (
    accuracy,
    bootstrap_ci,
    brier_binary,
    log_loss_binary,
    multiclass_brier,
    multiclass_logloss,
    topk_hit,
)


def ranked_probability_score(y_true: Sequence[str], probs: Sequence[dict[str, float]], labels=("home", "draw", "away")) -> float | None:
    if not y_true:
        return None
    total = 0.0
    for yt, pr in zip(y_true, probs):
        cum_p = 0.0
        cum_y = 0.0
        s = 0.0
        for lab in labels:
            cum_p += float(pr.get(lab, 0.0))
            cum_y += 1.0 if yt == lab else 0.0
            s += (cum_p - cum_y) ** 2
        total += s
    return total / len(y_true)


def expected_calibration_error(
    y_true: Sequence[str],
    probs: Sequence[dict[str, float]],
    *,
    n_bins: int = 10,
    labels=("home", "draw", "away"),
) -> float | None:
    if not y_true:
        return None
    # Confidence = max predicted class; correctness of that class
    confs = []
    corrects = []
    for yt, pr in zip(y_true, probs):
        best = max(labels, key=lambda l: float(pr.get(l, 0.0)))
        confs.append(float(pr.get(best, 0.0)))
        corrects.append(1.0 if best == yt else 0.0)
    bins = [[] for _ in range(n_bins)]
    for c, ok in zip(confs, corrects):
        idx = min(n_bins - 1, int(c * n_bins))
        bins[idx].append((c, ok))
    ece = 0.0
    n = len(y_true)
    for b in bins:
        if not b:
            continue
        acc = sum(ok for _, ok in b) / len(b)
        conf = sum(c for c, _ in b) / len(b)
        ece += (len(b) / n) * abs(acc - conf)
    return ece


def exact_score_nll(actual_scores: Sequence[str], preds: Sequence[dict[str, Any]], eps: float = 1e-15) -> float | None:
    if not actual_scores:
        return None
    s = 0.0
    for act, p in zip(actual_scores, preds):
        tops = {t["score"]: float(t["probability"]) for t in (p.get("top10") or [])}
        # If not in top10, approximate residual mass uniformly over remaining cells (8x8-10)
        pr = tops.get(act)
        if pr is None:
            used = sum(tops.values())
            residual = max(eps, 1.0 - used)
            pr = residual / max(1.0, 64 - len(tops))
        s += -math.log(max(eps, pr))
    return s / len(actual_scores)


def xg_errors(rows: Sequence[dict], preds: Sequence[dict[str, Any]]) -> dict[str, float | None]:
    if not rows:
        return {"mae": None, "rmse": None}
    errs = []
    for r, p in zip(rows, preds):
        eh = float(p.get("expected_home_goals") or 0.0)
        ea = float(p.get("expected_away_goals") or 0.0)
        errs.append(abs(eh - float(r["home_goals"])))
        errs.append(abs(ea - float(r["away_goals"])))
    mae = sum(errs) / len(errs)
    rmse = math.sqrt(sum(e * e for e in errs) / len(errs))
    return {"mae": mae, "rmse": rmse}


def evaluate_full(rows: list[dict], preds: list[dict]) -> dict[str, Any]:
    y1 = [r["actual_1x2"] for r in rows]
    p1 = [p["decision_1x2"] for p in preds]
    probs = [p["hda"] for p in preds]
    btts_y = [r["actual_btts"] for r in rows]
    btts_p = [p["btts_yes"] for p in preds]
    ou_y = [r["actual_over25"] for r in rows]
    ou_p = [p["ou25_over"] for p in preds]
    scores = [r["actual_score"] for r in rows]
    top5 = [[t["score"] for t in (p.get("top5") or [])] for p in preds]
    top10 = [[t["score"] for t in (p.get("top10") or [])] for p in preds]
    xg = xg_errors(rows, preds)
    return {
        "n": len(rows),
        "source_label_note": "Challenger metrics on RECONSTRUCTED_RESEARCH_ONLY snapshots unless otherwise stated",
        "acc_1x2": accuracy(y1, p1),
        "brier_1x2": multiclass_brier(y1, probs),
        "logloss_1x2": multiclass_logloss(y1, probs),
        "rps_1x2": ranked_probability_score(y1, probs),
        "ece_1x2": expected_calibration_error(y1, probs),
        "brier_btts": brier_binary(btts_y, btts_p),
        "logloss_btts": log_loss_binary(btts_y, btts_p),
        "acc_btts": accuracy(btts_y, [1 if p >= 0.5 else 0 for p in btts_p]),
        "brier_ou25": brier_binary(ou_y, ou_p),
        "logloss_ou25": log_loss_binary(ou_y, ou_p),
        "acc_ou25": accuracy(ou_y, [1 if p >= 0.5 else 0 for p in ou_p]),
        "exact_score_nll": exact_score_nll(scores, preds),
        "top1_hit": topk_hit(scores, top5, 1),
        "top3_hit": topk_hit(scores, top5, 3),
        "top5_hit": topk_hit(scores, top5, 5),
        "top10_hit": topk_hit(scores, top10, 10),
        "expected_goal_mae": xg["mae"],
        "expected_goal_rmse": xg["rmse"],
        "bootstrap_acc_1x2": bootstrap_ci([1.0 if a == b else 0.0 for a, b in zip(y1, p1)]),
    }
