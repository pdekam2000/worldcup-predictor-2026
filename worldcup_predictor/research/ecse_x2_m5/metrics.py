"""PHASE ECSE-X2-M5 — Evaluation metrics and segment labels."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from worldcup_predictor.research.ecse_exact_score_backtest import LOG_LOSS_FLOOR, multiclass_brier
from worldcup_predictor.research.ecse_x2_m4.segment import (
    classify_match_state,
    is_strong_home_favorite,
)
from worldcup_predictor.research.ecse_x2_m5.constants import MIN_HOME_PROB, SHORTLIST_TOP_N, STRONG_HOME_PROB


def segment_labels(probs: dict[str, float | None], *, home_prob: float | None) -> list[str]:
    labels = []
    if probs.get("ft_home") is not None:
        labels.append("all_eligible")
    h = home_prob if home_prob is not None else probs.get("ft_home")
    if h is not None and h >= MIN_HOME_PROB:
        labels.append("home_ge_55")
    if h is not None and h >= STRONG_HOME_PROB:
        labels.append("home_ge_60")
    state = classify_match_state(probs)
    if state == "home_favorite":
        labels.append("home_favorite")
    if is_strong_home_favorite(probs):
        labels.append("strong_home_favorite")
    if state == "balanced":
        labels.append("balanced_control")
    return labels


def hit_positions(top_rows: list[dict[str, Any]], actual: str) -> dict[str, Any]:
    rank = next((int(r["rank"]) for r in top_rows if r["scoreline"] == actual), None)
    in_shortlist = rank is not None and rank <= SHORTLIST_TOP_N
    return {
        "actual_rank": rank,
        "hit_top1": rank == 1,
        "hit_top3": rank is not None and rank <= 3,
        "hit_top5": rank is not None and rank <= 5,
        "hit_top10": rank is not None and rank <= 10,
        "hit_shortlist": in_shortlist,
        "reciprocal_rank": round(1.0 / rank, 6) if rank else 0.0,
    }


@dataclass
class MethodMetrics:
    n: int = 0
    top1: int = 0
    top3: int = 0
    top5: int = 0
    top10: int = 0
    shortlist: int = 0
    rank_sum: float = 0.0
    rank_n: int = 0
    mrr_sum: float = 0.0
    log_loss_sum: float = 0.0
    brier_sum: float = 0.0
    disagreement: int = 0
    rank_move_abs_sum: float = 0.0
    rank_move_n: int = 0

    def add(
        self,
        *,
        actual: str,
        method_top: list[dict[str, Any]],
        baseline_top: list[dict[str, Any]],
    ) -> None:
        hits = hit_positions(method_top, actual)
        base_hits = hit_positions(baseline_top, actual)
        self.n += 1
        self.top1 += int(hits["hit_top1"])
        self.top3 += int(hits["hit_top3"])
        self.top5 += int(hits["hit_top5"])
        self.top10 += int(hits["hit_top10"])
        self.shortlist += int(hits["hit_shortlist"])
        if hits["actual_rank"]:
            self.rank_sum += hits["actual_rank"]
            self.rank_n += 1
            self.mrr_sum += hits["reciprocal_rank"]
        probs = {r["scoreline"]: r["probability"] for r in method_top}
        p = max(probs.get(actual, LOG_LOSS_FLOOR), LOG_LOSS_FLOOR)
        self.log_loss_sum += -math.log(p)
        self.brier_sum += multiclass_brier(probs, actual)
        self.disagreement += int(
            method_top[0]["scoreline"] != baseline_top[0]["scoreline"] if method_top and baseline_top else False
        )
        br = base_hits["actual_rank"]
        mr = hits["actual_rank"]
        if br and mr:
            self.rank_move_abs_sum += abs(br - mr)
            self.rank_move_n += 1

    def summary(self) -> dict[str, Any]:
        if self.n == 0:
            return {"n": 0}
        out = {
            "n": self.n,
            "top1_hit_rate_pct": round(100.0 * self.top1 / self.n, 4),
            "top3_hit_rate_pct": round(100.0 * self.top3 / self.n, 4),
            "top5_hit_rate_pct": round(100.0 * self.top5 / self.n, 4),
            "top10_hit_rate_pct": round(100.0 * self.top10 / self.n, 4),
            "shortlist_hit_rate_pct": round(100.0 * self.shortlist / self.n, 4),
            "avg_log_loss": round(self.log_loss_sum / self.n, 6),
            "avg_brier": round(self.brier_sum / self.n, 6),
            "disagreement_rate_pct": round(100.0 * self.disagreement / self.n, 4),
        }
        if self.rank_n:
            out["avg_actual_rank"] = round(self.rank_sum / self.rank_n, 4)
            out["mean_reciprocal_rank"] = round(self.mrr_sum / self.rank_n, 6)
        if self.rank_move_n:
            out["rank_volatility"] = round(self.rank_move_abs_sum / self.rank_move_n, 4)
        return out


def delta_vs_champion(champion: MethodMetrics, method: MethodMetrics) -> dict[str, float]:
    cs = champion.summary()
    ms = method.summary()
    if champion.n == 0:
        return {}
    return {
        "top1_delta_pp": round(ms.get("top1_hit_rate_pct", 0) - cs.get("top1_hit_rate_pct", 0), 4),
        "top3_delta_pp": round(ms.get("top3_hit_rate_pct", 0) - cs.get("top3_hit_rate_pct", 0), 4),
        "top5_delta_pp": round(ms.get("top5_hit_rate_pct", 0) - cs.get("top5_hit_rate_pct", 0), 4),
        "top10_delta_pp": round(ms.get("top10_hit_rate_pct", 0) - cs.get("top10_hit_rate_pct", 0), 4),
        "shortlist_delta_pp": round(ms.get("shortlist_hit_rate_pct", 0) - cs.get("shortlist_hit_rate_pct", 0), 4),
        "avg_log_loss": round(ms.get("avg_log_loss", 0) - cs.get("avg_log_loss", 0), 6),
        "avg_actual_rank": round(ms.get("avg_actual_rank", 0) - cs.get("avg_actual_rank", 0), 4),
        "mean_reciprocal_rank": round(
            ms.get("mean_reciprocal_rank", 0) - cs.get("mean_reciprocal_rank", 0), 6
        ),
    }
