"""Statistical helpers for TRUE_FORWARD_472 evaluation (read-only)."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any, Iterable, Sequence


def wilson_interval(hits: int, n: int, z: float = 1.96) -> dict[str, float | None]:
    if n <= 0:
        return {"low": None, "high": None, "center": None}
    phat = hits / n
    z2 = z * z
    denom = 1 + z2 / n
    center = (phat + z2 / (2 * n)) / denom
    margin = (z / denom) * math.sqrt(phat * (1 - phat) / n + z2 / (4 * n * n))
    return {
        "low": max(0.0, center - margin),
        "high": min(1.0, center + margin),
        "center": center,
    }


def accuracy_pack(hits: int, n: int) -> dict[str, Any]:
    acc = (hits / n) if n else None
    return {
        "n": n,
        "hits": hits,
        "misses": max(0, n - hits),
        "accuracy": acc,
        "wilson_95": wilson_interval(hits, n),
    }


def confusion_1x2(
    pairs: Sequence[tuple[str, str]],
) -> dict[str, Any]:
    """pairs: (predicted, actual) normalized to home_win|draw|away_win."""
    labels = ("home_win", "draw", "away_win")
    matrix = {p: {a: 0 for a in labels} for p in labels}
    for pred, actual in pairs:
        if pred in matrix and actual in matrix[pred]:
            matrix[pred][actual] += 1
    out: dict[str, Any] = {"matrix": matrix, "per_class": {}}
    recalls = []
    for cls in labels:
        tp = matrix[cls][cls]
        pred_n = sum(matrix[cls].values())
        actual_n = sum(matrix[p][cls] for p in labels)
        prec = (tp / pred_n) if pred_n else None
        rec = (tp / actual_n) if actual_n else None
        if rec is not None:
            recalls.append(rec)
        out["per_class"][cls] = {
            "precision": prec,
            "recall": rec,
            "support_actual": actual_n,
            "support_predicted": pred_n,
        }
    out["balanced_accuracy"] = (sum(recalls) / len(recalls)) if recalls else None
    return out


def brier_multiclass(probs: dict[str, float], actual: str) -> float | None:
    labels = ("home_win", "draw", "away_win")
    if actual not in labels:
        return None
    s = 0.0
    for lab in labels:
        y = 1.0 if lab == actual else 0.0
        p = float(probs.get(lab, 0.0) or 0.0)
        s += (p - y) ** 2
    return s


def log_loss_multiclass(probs: dict[str, float], actual: str, eps: float = 1e-15) -> float | None:
    if actual not in ("home_win", "draw", "away_win"):
        return None
    p = max(eps, min(1.0 - eps, float(probs.get(actual, 0.0) or 0.0)))
    return -math.log(p)


def priced_performance(
    stakes: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """
    Each stake: {hit: bool, odds: float, side: str}
    unit stake = 1.
    """
    if not stakes:
        return {
            "priced_n": 0,
            "wins": 0,
            "losses": 0,
            "average_odds": None,
            "median_odds": None,
            "total_stake": 0.0,
            "total_return": 0.0,
            "net_profit": 0.0,
            "roi": None,
            "profit_factor": None,
            "max_drawdown": 0.0,
            "longest_winning_streak": 0,
            "longest_losing_streak": 0,
            "cumulative_bankroll": [],
        }
    odds_list = [float(s["odds"]) for s in stakes]
    wins = sum(1 for s in stakes if s["hit"])
    losses = len(stakes) - wins
    total_stake = float(len(stakes))
    returns = []
    bank = 0.0
    peak = 0.0
    max_dd = 0.0
    curve = []
    w_streak = l_streak = 0
    max_w = max_l = 0
    gross_win = 0.0
    gross_loss = 0.0
    for s in stakes:
        o = float(s["odds"])
        if s["hit"]:
            ret = o
            pnl = o - 1.0
            gross_win += pnl
            w_streak += 1
            l_streak = 0
            max_w = max(max_w, w_streak)
        else:
            ret = 0.0
            pnl = -1.0
            gross_loss += 1.0
            l_streak += 1
            w_streak = 0
            max_l = max(max_l, l_streak)
        returns.append(ret)
        bank += pnl
        peak = max(peak, bank)
        max_dd = max(max_dd, peak - bank)
        curve.append(round(bank, 6))
    total_return = sum(returns)
    net = total_return - total_stake
    odds_sorted = sorted(odds_list)
    mid = len(odds_sorted) // 2
    median = (
        odds_sorted[mid]
        if len(odds_sorted) % 2 == 1
        else (odds_sorted[mid - 1] + odds_sorted[mid]) / 2.0
    )
    pf = (gross_win / gross_loss) if gross_loss > 0 else (None if gross_win == 0 else float("inf"))
    return {
        "priced_n": len(stakes),
        "wins": wins,
        "losses": losses,
        "average_odds": sum(odds_list) / len(odds_list),
        "median_odds": median,
        "total_stake": total_stake,
        "total_return": total_return,
        "net_profit": net,
        "roi": (net / total_stake) if total_stake else None,
        "profit_factor": pf,
        "max_drawdown": max_dd,
        "longest_winning_streak": max_w,
        "longest_losing_streak": max_l,
        "cumulative_bankroll": curve,
    }


def timing_stage(hours_to_kickoff: float | None) -> str:
    if hours_to_kickoff is None:
        return "UNKNOWN"
    if hours_to_kickoff < 0:
        return "POST_KICKOFF"
    if hours_to_kickoff <= 2:
        return "FINAL_PREMATCH"
    if hours_to_kickoff <= 12:
        return "LATE"
    if hours_to_kickoff <= 48:
        return "MID"
    return "EARLY"


def calibration_bucket(p_actual: float | None) -> str:
    if p_actual is None:
        return "NO_PROB"
    if p_actual < 0.2:
        return "0.0-0.2"
    if p_actual < 0.4:
        return "0.2-0.4"
    if p_actual < 0.6:
        return "0.4-0.6"
    if p_actual < 0.8:
        return "0.6-0.8"
    return "0.8-1.0"


def group_accuracy(rows: Iterable[dict[str, Any]], key: str) -> dict[str, Any]:
    buckets: dict[str, list[bool]] = defaultdict(list)
    for r in rows:
        buckets[str(r.get(key) or "UNKNOWN")].append(bool(r.get("hit")))
    out = {}
    for k, hits_list in sorted(buckets.items(), key=lambda x: (-len(x[1]), x[0])):
        h = sum(1 for x in hits_list if x)
        out[k] = accuracy_pack(h, len(hits_list))
    return out


def count_by(items: Iterable[Any]) -> dict[str, int]:
    return dict(Counter(str(x) for x in items))
