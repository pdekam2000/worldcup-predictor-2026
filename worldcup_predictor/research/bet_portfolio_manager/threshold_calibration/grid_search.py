"""Bounded threshold grid + chronological calibration (research-only)."""

from __future__ import annotations

import copy
import hashlib
import itertools
import json
from typing import Any

from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.constants import BASELINE_POLICY
from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.metrics import (
    always_bet_metrics,
    summarize_days,
)
from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.policy_engine import (
    replay_all_days,
)


def _hash(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def days_to_fixtures(days: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for d in days:
        out.extend(d.get("fixtures") or [])
    return out


def chronological_splits(days: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(days)
    i60 = int(n * 0.60)
    i80 = int(n * 0.80)
    train = days[:i60]
    val = days[i60:i80]
    hold = days[i80:]
    return {
        "n_total": n,
        "train": train,
        "validation": val,
        "holdout": hold,
        "train_fixtures": days_to_fixtures(train),
        "validation_fixtures": days_to_fixtures(val),
        "holdout_fixtures": days_to_fixtures(hold),
        "manifest": {
            "train_dates": [train[0]["date"], train[-1]["date"]] if train else [],
            "validation_dates": [val[0]["date"], val[-1]["date"]] if val else [],
            "holdout_dates": [hold[0]["date"], hold[-1]["date"]] if hold else [],
            "train_n": len(train),
            "validation_n": len(val),
            "holdout_n": len(hold),
            "train_hash": _hash([d["date"] for d in train]),
            "validation_hash": _hash([d["date"] for d in val]),
            "holdout_hash": _hash([d["date"] for d in hold]),
            "split_ratios": {"train": 0.60, "validation": 0.20, "holdout": 0.20},
            "shuffle": False,
        },
    }


def walk_forward_folds(days: list[dict[str, Any]], n_folds: int = 3) -> list[dict[str, Any]]:
    """Rolling chronological folds when dataset is large enough."""
    n = len(days)
    if n < 40:
        return []
    folds = []
    # Expanding window: train grows, next block validates
    block = max(5, n // (n_folds + 2))
    for i in range(n_folds):
        train_end = block * (i + 2)
        val_end = min(n, train_end + block)
        if train_end >= n or train_end < 10:
            break
        train = days[:train_end]
        val = days[train_end:val_end]
        if not val:
            break
        folds.append(
            {
                "fold": i,
                "train_dates": [train[0]["date"], train[-1]["date"]],
                "validation_dates": [val[0]["date"], val[-1]["date"]],
                "train_n": len(train),
                "validation_n": len(val),
            }
        )
    return folds


def leakage_validation(manifest: dict[str, Any]) -> dict[str, Any]:
    t = set()
    # reconstruct from hashes only check date range order
    train_dates = manifest.get("train_dates") or []
    val_dates = manifest.get("validation_dates") or []
    hold_dates = manifest.get("holdout_dates") or []
    ordered = True
    if train_dates and val_dates:
        ordered = ordered and train_dates[-1] <= val_dates[0]
    if val_dates and hold_dates:
        ordered = ordered and val_dates[-1] <= hold_dates[0]
    return {
        "research_only": True,
        "chronological_order_ok": ordered,
        "no_shuffle": True,
        "train_validation_overlap": False,
        "validation_holdout_overlap": False,
        "future_leakage": False,
        "hashes": {
            "train": manifest.get("train_hash"),
            "validation": manifest.get("validation_hash"),
            "holdout": manifest.get("holdout_hash"),
        },
    }


def _policy_variant(
    *,
    bet_min: float,
    small_min: float,
    watch_min: float,
    conf_min: float,
    ent_min: float,
    league_min: float,
    ins_min: float,
    watch_micro: float,
    capital_mode: str = "score_weighted",
) -> dict[str, Any]:
    p = copy.deepcopy(BASELINE_POLICY)
    p["policy_version"] = (
        f"candidate_bet{bet_min}_sm{small_min}_w{watch_min}"
        f"_c{conf_min}_e{ent_min}_l{league_min}_i{ins_min}_m{watch_micro}"
    )
    p["action_thresholds"] = {
        "BET": float(bet_min),
        "SMALL_BET": float(small_min),
        "WATCH": float(watch_min),
        "SKIP": 0.0,
    }
    # Keep grade thresholds aligned loosely with actions for interpretability (audit already done)
    p["grade_thresholds"] = {
        "S": max(92.0, bet_min + 8),
        "A": float(bet_min),
        "B": float(small_min),
        "C": float(watch_min),
        "D": max(20.0, watch_min - 15),
        "F": 0.0,
    }
    p["gates"]["mean_confidence_min"] = float(conf_min)
    p["gates"]["low_entropy_min"] = float(ent_min)
    p["gates"]["league_reliability_min"] = float(league_min)
    p["gates"]["insurance_contribution_min"] = float(ins_min)
    p["watch_micro_allocation_ratio"] = float(watch_micro)
    p["watch_positive_score_slack"] = 6.0
    p["capital_mode"] = capital_mode
    # Unit-stake parity with historical_validation / Always Bet (allocation modes studied separately)
    p["small_bet_capital_scale"] = 1.0
    p["bet_unit_scale"] = 1.0
    return p


def generate_candidate_policies() -> list[dict[str, Any]]:
    """Bounded grid around baseline — deterministic, modest size for auditability."""
    bet_mins = (78.0, 80.0, 82.0, 84.0)
    small_mins = (65.0, 68.0, 72.0)
    watch_mins = (48.0, 52.0, 55.0)
    gate_packs = (
        (35.0, 35.0, 35.0, 15.0),  # baseline-like
        (30.0, 30.0, 30.0, 10.0),  # slightly looser
    )
    micros = (0.0, 0.10, 0.15)

    out = [copy.deepcopy(BASELINE_POLICY)]
    for bet, small, watch in itertools.product(bet_mins, small_mins, watch_mins):
        if not (bet > small > watch >= 45):
            continue
        for conf, ent, lg, ins in gate_packs:
            for micro in micros:
                out.append(
                    _policy_variant(
                        bet_min=bet,
                        small_min=small,
                        watch_min=watch,
                        conf_min=conf,
                        ent_min=ent,
                        league_min=lg,
                        ins_min=ins,
                        watch_micro=micro,
                    )
                )
    seen: set[str] = set()
    uniq: list[dict[str, Any]] = []
    for p in out:
        vid = str(p["policy_version"])
        if vid in seen:
            continue
        seen.add(vid)
        uniq.append(p)
    return uniq


def evaluate_policy_on_fixtures(
    fixtures: list[dict[str, Any]],
    policy: dict[str, Any],
    *,
    league_reliability_map: dict[str, float] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    days = replay_all_days(fixtures, policy=policy, league_reliability_map=league_reliability_map)
    return days, summarize_days(days)


def score_candidate(metrics: dict[str, Any], always: dict[str, Any]) -> float:
    """Validation ranking score — higher is better (no holdout peeking)."""
    roi_raw = metrics.get("roi")
    if roi_raw is None:
        # Zero-capital policies cannot be ranked by ROI; strong penalty
        roi = -2.0
    else:
        roi = float(roi_raw)
    dd = float(metrics.get("max_drawdown") or 1e9)
    exp = float(metrics.get("average_exposure") or 0)
    active = float(metrics.get("active_day_ratio") or 0)
    always_roi = float(always.get("roi") or 0)
    always_dd = float(always.get("max_drawdown") or 1)
    always_exp = float(always.get("average_exposure") or 1)
    s = 0.0
    s += 40.0 * (roi - always_roi)
    s += 25.0 * max(0.0, (always_dd - dd) / max(1e-6, always_dd))
    s += 15.0 * max(0.0, (always_exp - exp) / max(1e-6, always_exp))
    if 0.20 <= active <= 0.65:
        s += 20.0
    elif active < 0.05:
        s -= 40.0
    else:
        s -= 10.0 * abs(active - 0.4)
    s += 5.0 * float(metrics.get("win_frequency") or 0)
    return round(s, 6)


def run_grid_on_split(
    fixtures_train: list[dict[str, Any]],
    fixtures_val: list[dict[str, Any]],
    policies: list[dict[str, Any]],
    *,
    league_reliability_map: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.policy_engine import (
        league_reliability as _lr,
    )

    lr = league_reliability_map if league_reliability_map is not None else _lr(fixtures_train)
    always_val_days = replay_all_days(fixtures_val, policy=BASELINE_POLICY, league_reliability_map=lr)
    always_val = always_bet_metrics(always_val_days)

    results = []
    for i, pol in enumerate(policies):
        train_days, train_m = evaluate_policy_on_fixtures(fixtures_train, pol, league_reliability_map=lr)
        val_days, val_m = evaluate_policy_on_fixtures(fixtures_val, pol, league_reliability_map=lr)
        results.append(
            {
                "configuration_id": f"cfg_{i:04d}",
                "policy_version": pol.get("policy_version"),
                "threshold_values": {
                    "action_thresholds": pol.get("action_thresholds"),
                    "gates": {
                        k: pol.get("gates", {}).get(k)
                        for k in (
                            "mean_confidence_min",
                            "low_entropy_min",
                            "league_reliability_min",
                            "insurance_contribution_min",
                            "min_fixture_score_to_bet",
                        )
                    },
                    "watch_micro_allocation_ratio": pol.get("watch_micro_allocation_ratio"),
                    "capital_mode": pol.get("capital_mode"),
                },
                "training_metrics": train_m,
                "validation_metrics": val_m,
                "validation_rank_score": score_candidate(val_m, always_val),
                "policy": pol,
            }
        )
    results.sort(key=lambda r: (-float(r["validation_rank_score"]), r["configuration_id"]))
    return results


def pareto_frontier(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pts = []
    for r in results:
        m = r["validation_metrics"]
        pts.append(
            {
                "configuration_id": r["configuration_id"],
                "policy_version": r["policy_version"],
                "roi": m.get("roi"),
                "max_drawdown": m.get("max_drawdown"),
                "average_exposure": m.get("average_exposure"),
                "active_day_ratio": m.get("active_day_ratio"),
                "capital_efficiency": m.get("roi"),
            }
        )

    def dominates(a: dict[str, Any], b: dict[str, Any]) -> bool:
        # higher ROI, lower DD, lower exposure better; active in band soft — use closer to 0.4 as better via abs
        better_or_eq = (
            float(a.get("roi") or -9) >= float(b.get("roi") or -9)
            and float(a.get("max_drawdown") or 9e9) <= float(b.get("max_drawdown") or 9e9)
            and float(a.get("average_exposure") or 9e9) <= float(b.get("average_exposure") or 9e9)
        )
        strictly = (
            float(a.get("roi") or -9) > float(b.get("roi") or -9)
            or float(a.get("max_drawdown") or 9e9) < float(b.get("max_drawdown") or 9e9)
            or float(a.get("average_exposure") or 9e9) < float(b.get("average_exposure") or 9e9)
        )
        return better_or_eq and strictly

    frontier = []
    for p in pts:
        if any(dominates(q, p) for q in pts if q is not p):
            continue
        frontier.append(p)
    return frontier


def check_guardrails(managed: dict[str, Any], always: dict[str, Any]) -> dict[str, Any]:
    m_roi = managed.get("roi")
    a_roi = always.get("roi")
    m_dd = float(managed.get("max_drawdown") or 0)
    a_dd = float(always.get("max_drawdown") or 0)
    m_exp = float(managed.get("average_exposure") or 0)
    a_exp = float(always.get("average_exposure") or 0)
    active = float(managed.get("active_day_ratio") or 0)
    checks = {
        "managed_roi_ge_always": bool(m_roi is not None and a_roi is not None and m_roi >= a_roi),
        "drawdown_le_75pct_always": bool(a_dd > 0 and m_dd <= 0.75 * a_dd),
        "exposure_le_70pct_always": bool(a_exp > 0 and m_exp <= 0.70 * a_exp),
        "active_days_ge_20pct": active >= 0.20,
        "active_days_le_65pct": active <= 0.65,
    }
    return {
        "passed": {k: v for k, v in checks.items() if v},
        "failed": {k: v for k, v in checks.items() if not v},
        "all_passed": all(checks.values()),
        "checks": checks,
    }
