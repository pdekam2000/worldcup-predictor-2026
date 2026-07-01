"""PHASE ECSE-X3-A — Extended evaluation metrics."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from worldcup_predictor.research.ecse_exact_score_backtest import LOG_LOSS_FLOOR, multiclass_brier
from worldcup_predictor.research.ecse_x3.constants import TOP_N_SHADOW, ZZ2_TARGET
from worldcup_predictor.research.ecse_x2_m4.segment import classify_match_state, is_strong_home_favorite
from worldcup_predictor.research.ecse_x2_m5.metrics import delta_vs_champion as _base_delta
from worldcup_predictor.research.ecse_x2_m5.metrics import hit_positions
from worldcup_predictor.research.ecse_x3.constants import (
    BTTS_HIGH_MIN,
    DRAW_HIGH_MIN,
    MIN_HOME_PROB,
    OVER_HIGH_MIN,
    STRONG_HOME_PROB,
    UNDER_HIGH_MIN,
)


def _parse_score(scoreline: str) -> tuple[int, int] | None:
    try:
        h, a = scoreline.split("-")
        return int(h), int(a)
    except (ValueError, AttributeError):
        return None


def _outcome(h: int, a: int) -> str:
    if h > a:
        return "home"
    if h < a:
        return "away"
    return "draw"


def _btts(sl: str) -> bool | None:
    p = _parse_score(sl)
    return p[0] > 0 and p[1] > 0 if p else None


def _ou25(sl: str) -> bool | None:
    p = _parse_score(sl)
    return (p[0] + p[1]) > 2 if p else None


def segment_labels(
    probs: dict[str, float | None],
    *,
    home_prob: float | None,
    league: str | None = None,
    coverage_count: int | None = None,
) -> list[str]:
    labels: list[str] = []
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
    elif state == "away_favorite":
        labels.append("away_favorite")
    elif state == "balanced":
        labels.append("balanced_match")
    if is_strong_home_favorite(probs):
        labels.append("strong_home_favorite")
    pd = probs.get("ft_draw") or probs.get("draw_proxy")
    if pd is not None and pd >= DRAW_HIGH_MIN:
        labels.append("draw_high")
    if probs.get("btts_yes") is not None and float(probs["btts_yes"]) >= BTTS_HIGH_MIN:
        labels.append("btts_high")
    if probs.get("ou_under_25") is not None and float(probs["ou_under_25"]) >= UNDER_HIGH_MIN:
        labels.append("under_25_high")
    if probs.get("ou_over_25") is not None and float(probs["ou_over_25"]) >= OVER_HIGH_MIN:
        labels.append("over_25_high")
    cov = int(coverage_count or 0)
    if cov >= 12:
        labels.append("odds_liquidity_high")
    elif cov >= 8:
        labels.append("odds_liquidity_mid")
    else:
        labels.append("odds_liquidity_low")
    lg = (league or "").lower()
    if "world cup" in lg:
        if any(x in lg for x in ("final", "quarter", "semi", "round of 16", "knockout")):
            labels.append("world_cup_knockout")
        else:
            labels.append("world_cup_group")
    if league:
        labels.append(f"league:{league[:48]}")
    return labels


def close_miss(full_dist: list[dict[str, Any]] | None, actual: str) -> bool:
    if not full_dist:
        return False
    rank = next((int(r["rank"]) for r in full_dist if r["scoreline"] == actual), None)
    return rank is not None and rank > TOP_N_SHADOW and rank <= TOP_N_SHADOW + 5


@dataclass
class MethodMetrics:
    n: int = 0
    top1: int = 0
    top3: int = 0
    top5: int = 0
    top10: int = 0
    rank_sum: float = 0.0
    rank_n: int = 0
    mrr_sum: float = 0.0
    log_loss_sum: float = 0.0
    close_miss_n: int = 0
    winner_correct_score_wrong: int = 0
    btts_flip_improved: int = 0
    ou_flip_improved: int = 0
    zz2_would_help: int = 0
    disagreement: int = 0
    rank_move_abs_sum: float = 0.0
    rank_move_n: int = 0
    signals_applied: int = 0

    def add(
        self,
        *,
        actual: str,
        method_top: list[dict[str, Any]],
        baseline_top: list[dict[str, Any]],
        full_dist: list[dict[str, Any]] | None = None,
        signals_ok: bool = False,
        zz2_meta: dict[str, Any] | None = None,
    ) -> None:
        hits = hit_positions(method_top, actual)
        base_hits = hit_positions(baseline_top, actual)
        self.n += 1
        if signals_ok:
            self.signals_applied += 1
        self.top1 += int(hits["hit_top1"])
        self.top3 += int(hits["hit_top3"])
        self.top5 += int(hits["hit_top5"])
        self.top10 += int(hits["hit_top10"])
        if hits["actual_rank"]:
            self.rank_sum += hits["actual_rank"]
            self.rank_n += 1
            self.mrr_sum += hits["reciprocal_rank"]
        probs = {r["scoreline"]: r["probability"] for r in method_top}
        p = max(probs.get(actual, LOG_LOSS_FLOOR), LOG_LOSS_FLOOR)
        self.log_loss_sum += -math.log(p)
        self.disagreement += int(
            method_top[0]["scoreline"] != baseline_top[0]["scoreline"] if method_top and baseline_top else False
        )
        br, mr = base_hits["actual_rank"], hits["actual_rank"]
        if br and mr:
            self.rank_move_abs_sum += abs(br - mr)
            self.rank_move_n += 1

        if close_miss(full_dist, actual):
            self.close_miss_n += 1

        act_p = _parse_score(actual)
        if act_p and method_top and baseline_top:
            act_out = _outcome(*act_p)
            meth_t0 = _parse_score(str(method_top[0]["scoreline"]))
            if meth_t0 and _outcome(*meth_t0) == act_out and str(method_top[0]["scoreline"]) != actual:
                self.winner_correct_score_wrong += 1

            base_btts = _btts(str(baseline_top[0]["scoreline"]))
            meth_btts = _btts(str(method_top[0]["scoreline"]))
            act_btts = act_p[0] > 0 and act_p[1] > 0
            if base_btts is not None and meth_btts is not None:
                if base_btts != act_btts and meth_btts == act_btts:
                    self.btts_flip_improved += 1

            base_ou = _ou25(str(baseline_top[0]["scoreline"]))
            meth_ou = _ou25(str(method_top[0]["scoreline"]))
            act_ou = (act_p[0] + act_p[1]) > 2
            if base_ou is not None and meth_ou is not None:
                if base_ou != act_ou and meth_ou == act_ou:
                    self.ou_flip_improved += 1

        zm = zz2_meta or {}
        if zm.get("zz2_fired") and not zm.get("zz2_in_pool") and actual == ZZ2_TARGET:
            self.zz2_would_help += 1

    def summary(self) -> dict[str, Any]:
        if self.n == 0:
            return {"n": 0}
        out: dict[str, Any] = {
            "n": self.n,
            "top1_hit_rate_pct": round(100.0 * self.top1 / self.n, 4),
            "top3_hit_rate_pct": round(100.0 * self.top3 / self.n, 4),
            "top5_hit_rate_pct": round(100.0 * self.top5 / self.n, 4),
            "top10_hit_rate_pct": round(100.0 * self.top10 / self.n, 4),
            "avg_log_loss": round(self.log_loss_sum / self.n, 6),
            "disagreement_rate_pct": round(100.0 * self.disagreement / self.n, 4),
            "close_miss_rate_pct": round(100.0 * self.close_miss_n / self.n, 4),
            "winner_correct_score_wrong_rate_pct": round(100.0 * self.winner_correct_score_wrong / self.n, 4),
            "btts_flip_improved_rate_pct": round(100.0 * self.btts_flip_improved / self.n, 4),
            "ou_flip_improved_rate_pct": round(100.0 * self.ou_flip_improved / self.n, 4),
            "zz2_would_help_rate_pct": round(100.0 * self.zz2_would_help / self.n, 4),
            "coverage_pct": round(100.0 * self.signals_applied / self.n, 4),
        }
        if self.rank_n:
            out["avg_actual_rank"] = round(self.rank_sum / self.rank_n, 4)
            out["mean_reciprocal_rank"] = round(self.mrr_sum / self.rank_n, 6)
        if self.rank_move_n:
            out["rank_volatility"] = round(self.rank_move_abs_sum / self.rank_move_n, 4)
        return out


def delta_vs_champion(champion: MethodMetrics, method: MethodMetrics) -> dict[str, float]:
    return _base_delta(champion, method)
