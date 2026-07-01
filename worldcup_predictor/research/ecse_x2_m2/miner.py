"""PHASE ECSE-X2-M2 — Equation mining, backtest, and ranking."""

from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from worldcup_predictor.research.ecse_exact_score_backtest import (
    LOG_LOSS_FLOOR,
    multiclass_brier,
)
from worldcup_predictor.research.ecse_x2_m2.constants import (
    MAX_LOG_LOSS_WORSEN,
    METHOD_VERSION,
    MIN_LEAGUE_SAMPLE,
    MIN_LEAGUES_IMPROVED,
    MIN_TEST_SAMPLE,
    MIN_TRAIN_SAMPLE,
    PHASE,
    TOP_SCORES_STORED,
    TRAIN_FRACTION,
)
from worldcup_predictor.research.ecse_x2_m2.equations import CANDIDATE_EQUATIONS, EquationSpec, compute_equation
from worldcup_predictor.research.ecse_x2_m2.prob_features import load_baseline_top_scores, load_fixture_records
from worldcup_predictor.research.ecse_x2_m2.reorder import apply_reorder, learn_lift_table, score_cluster


@dataclass
class SplitMetrics:
    n: int = 0
    top1: int = 0
    top3: int = 0
    top5: int = 0
    log_loss_sum: float = 0.0
    brier_sum: float = 0.0
    prob_actual_sum: float = 0.0

    def add_eval(self, actual: str, rank: int, prob_map: dict[str, float]) -> None:
        self.n += 1
        self.top1 += int(rank == 1)
        self.top3 += int(rank <= 3)
        self.top5 += int(rank <= 5)
        p = max(prob_map.get(actual, LOG_LOSS_FLOOR), LOG_LOSS_FLOOR)
        self.prob_actual_sum += p
        self.log_loss_sum += -math.log(p)
        self.brier_sum += multiclass_brier(prob_map, actual)

    def summary(self) -> dict[str, Any]:
        if self.n == 0:
            return {"n": 0}
        return {
            "n": self.n,
            "top1_hit_rate_pct": round(100.0 * self.top1 / self.n, 4),
            "top3_hit_rate_pct": round(100.0 * self.top3 / self.n, 4),
            "top5_hit_rate_pct": round(100.0 * self.top5 / self.n, 4),
            "avg_log_loss": round(self.log_loss_sum / self.n, 6),
            "avg_brier": round(self.brier_sum / self.n, 6),
            "avg_prob_actual": round(self.prob_actual_sum / self.n, 6),
        }


def _evaluate_dist(actual: str, dist: list[dict[str, Any]]) -> tuple[int, dict[str, float]]:
    prob_map = {str(r["scoreline"]): float(r["probability"]) for r in dist}
    rank_map = {str(r["scoreline"]): int(r["rank"]) for r in dist}
    return rank_map.get(actual, 999), prob_map


def _temporal_split(records: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    ordered = sorted(records, key=lambda r: (r.get("kickoff_unix") or 0, r["registry_fixture_id"]))
    cut = int(len(ordered) * TRAIN_FRACTION)
    return ordered[:cut], ordered[cut:]


def _league_deltas(
    baseline_by_league: dict[str, SplitMetrics],
    treated_by_league: dict[str, SplitMetrics],
) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for league, base in baseline_by_league.items():
        treat = treated_by_league.get(league)
        if not treat or base.n < MIN_LEAGUE_SAMPLE or treat.n < MIN_LEAGUE_SAMPLE:
            continue
        bs = base.summary()
        ts = treat.summary()
        out[league] = {
            "n": treat.n,
            "top1_delta_pp": round(ts["top1_hit_rate_pct"] - bs["top1_hit_rate_pct"], 4),
            "top3_delta_pp": round(ts["top3_hit_rate_pct"] - bs["top3_hit_rate_pct"], 4),
            "log_loss_delta": round(ts["avg_log_loss"] - bs["avg_log_loss"], 6),
        }
    return out


def _reject_reason(
    *,
    train_n: int,
    test_n: int,
    log_loss_delta: float,
    league_deltas: dict[str, dict[str, float]],
    top3_delta: float,
) -> str | None:
    if train_n < MIN_TRAIN_SAMPLE:
        return "train_sample_too_small"
    if test_n < MIN_TEST_SAMPLE:
        return "test_sample_too_small"
    if log_loss_delta > MAX_LOG_LOSS_WORSEN:
        return "log_loss_worsens_materially"
    if top3_delta <= 0 and log_loss_delta > 0:
        return "no_oos_improvement"
    improved_leagues = sum(1 for v in league_deltas.values() if v["top3_delta_pp"] > 0)
    if league_deltas and improved_leagues < MIN_LEAGUES_IMPROVED:
        return "single_league_concentration"
    return None


def _robust_score(delta: dict[str, float]) -> float:
    return (
        float(delta.get("top3_hit_rate_pct", 0)) * 0.45
        + float(delta.get("top1_hit_rate_pct", 0)) * 0.30
        + float(delta.get("top5_hit_rate_pct", 0)) * 0.20
        + float(delta.get("avg_prob_actual", 0)) * 100.0 * 0.05
        - max(0.0, float(delta.get("avg_log_loss", 0))) * 40.0
        - max(0.0, float(delta.get("avg_brier", 0))) * 8.0
    )


def mine_equation(
    spec: EquationSpec,
    records: list[dict[str, Any]],
    dist_map: dict[int, list[dict[str, Any]]],
) -> dict[str, Any]:
    usable: list[dict[str, Any]] = []
    for rec in records:
        fid = int(rec["registry_fixture_id"])
        if fid not in dist_map:
            continue
        val = compute_equation(spec, rec["probs"])
        if val is None:
            continue
        usable.append(
            {
                **rec,
                "value": val,
                "actual_cluster": score_cluster(rec["actual"]),
            }
        )

    train, test = _temporal_split(usable)
    train_vals = [{"value": r["value"], "actual": r["actual"], "actual_cluster": r["actual_cluster"]} for r in train]
    model = learn_lift_table(train_vals)

    base_test = SplitMetrics()
    treat_test = SplitMetrics()
    base_by_league: dict[str, SplitMetrics] = defaultdict(SplitMetrics)
    treat_by_league: dict[str, SplitMetrics] = defaultdict(SplitMetrics)

    cluster_lift_summary: dict[str, dict[str, float]] = {}
    for q, lifts in model.get("cluster_lift", {}).items():
        if lifts:
            top = max(lifts.items(), key=lambda x: x[1])
            cluster_lift_summary[str(q)] = {"cluster": top[0], "lift": round(top[1], 4)}

    for rec in test:
        fid = int(rec["registry_fixture_id"])
        dist = dist_map[fid]
        actual = rec["actual"]
        league = str(rec.get("league") or "unknown")

        base_rank, base_probs = _evaluate_dist(actual, dist)
        base_test.add_eval(actual, base_rank, base_probs)
        base_by_league[league].add_eval(actual, base_rank, base_probs)

        reordered = apply_reorder(dist, value=float(rec["value"]), model=model)
        treat_rank, treat_probs = _evaluate_dist(actual, reordered)
        treat_test.add_eval(actual, treat_rank, treat_probs)
        treat_by_league[league].add_eval(actual, treat_rank, treat_probs)

    base_s = base_test.summary()
    treat_s = treat_test.summary()
    delta = {
        "top1_hit_rate_pct": round(treat_s.get("top1_hit_rate_pct", 0) - base_s.get("top1_hit_rate_pct", 0), 4),
        "top3_hit_rate_pct": round(treat_s.get("top3_hit_rate_pct", 0) - base_s.get("top3_hit_rate_pct", 0), 4),
        "top5_hit_rate_pct": round(treat_s.get("top5_hit_rate_pct", 0) - base_s.get("top5_hit_rate_pct", 0), 4),
        "avg_log_loss": round(treat_s.get("avg_log_loss", 0) - base_s.get("avg_log_loss", 0), 6),
        "avg_brier": round(treat_s.get("avg_brier", 0) - base_s.get("avg_brier", 0), 6),
        "avg_prob_actual": round(treat_s.get("avg_prob_actual", 0) - base_s.get("avg_prob_actual", 0), 6),
    }

    league_deltas = _league_deltas(base_by_league, treat_by_league)
    reject = _reject_reason(
        train_n=len(train),
        test_n=len(test),
        log_loss_delta=float(delta["avg_log_loss"]),
        league_deltas=league_deltas,
        top3_delta=float(delta["top3_hit_rate_pct"]),
    )

    return {
        "key": spec.key,
        "label": spec.label,
        "required_features": list(spec.required),
        "train_n": len(train),
        "test_n": len(test),
        "usable_n": len(usable),
        "baseline_test": base_s,
        "treated_test": treat_s,
        "delta": delta,
        "cluster_lift_by_quantile": cluster_lift_summary,
        "league_stability": league_deltas,
        "rejected": reject is not None,
        "reject_reason": reject,
        "robust_score": round(_robust_score(delta), 4) if reject is None else None,
        "rank_score": round(_robust_score(delta), 4),
    }


@dataclass
class MineResult:
    phase: str = PHASE
    method_version: str = METHOD_VERSION
    equations_tested: int = 0
    equations_accepted: int = 0
    top_equations: list[dict[str, Any]] = field(default_factory=list)
    all_results: list[dict[str, Any]] = field(default_factory=list)
    baseline_test_overall: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "method_version": self.method_version,
            "equations_tested": self.equations_tested,
            "equations_accepted": self.equations_accepted,
            "top_equations": self.top_equations,
            "baseline_test_overall": self.baseline_test_overall,
        }


def run_market_algebra_miner(conn: sqlite3.Connection) -> MineResult:
    records = load_fixture_records(conn)
    dist_map = load_baseline_top_scores(conn, top_n=TOP_SCORES_STORED)

    result = MineResult()
    all_rows: list[dict[str, Any]] = []

    # Overall baseline on temporal test slice (any equation)
    _, test_records = _temporal_split(
        [r for r in records if int(r["registry_fixture_id"]) in dist_map]
    )
    base_overall = SplitMetrics()
    for rec in test_records:
        actual = rec["actual"]
        rank, probs = _evaluate_dist(actual, dist_map[int(rec["registry_fixture_id"])])
        base_overall.add_eval(actual, rank, probs)
    result.baseline_test_overall = base_overall.summary()

    for spec in CANDIDATE_EQUATIONS:
        row = mine_equation(spec, records, dist_map)
        all_rows.append(row)
        result.equations_tested += 1
        if not row["rejected"]:
            result.equations_accepted += 1

    all_rows.sort(key=lambda r: r.get("rank_score") or -999.0, reverse=True)
    result.all_results = all_rows
    accepted = [r for r in all_rows if not r["rejected"]]
    result.top_equations = all_rows[:20]
    return result
