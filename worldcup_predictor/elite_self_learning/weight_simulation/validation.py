"""Part B/C — metrics, bootstrap, accept/reject."""

from __future__ import annotations

import random
from typing import Any

from worldcup_predictor.elite_self_learning.weight_simulation.models import (
    REPLAY_WINDOWS,
    ApprovalStatus,
    ComponentLearningReport,
    ReplayMetrics,
    WindowComparison,
)

REGRESSION_TOLERANCE_ACCURACY = 0.01
BOOTSTRAP_ITERATIONS = 500


def _ece(pairs: list[tuple[float, int]], bins: int = 10) -> float:
    if not pairs:
        return 0.0
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(bins)]
    for p, y in pairs:
        idx = min(bins - 1, int(p * bins))
        buckets[idx].append((p, y))
    total = len(pairs)
    ece = 0.0
    for b in buckets:
        if not b:
            continue
        conf = sum(p for p, _ in b) / len(b)
        acc = sum(y for _, y in b) / len(b)
        ece += (len(b) / total) * abs(acc - conf)
    return round(ece, 4)


def compute_metrics(rows: list[dict[str, Any]], *, weight_label: str, prob_key: str, hit_key: str) -> ReplayMetrics:
    n = len(rows)
    if n == 0:
        return ReplayMetrics(0, "", weight_label, 0, 0.0, 0.0, 0.0, 0.0, 0.0)

    hits = [int(r[hit_key]) for r in rows]
    probs = [float(r[prob_key]) for r in rows]
    accuracy = sum(hits) / n
    brier = sum((p - y) ** 2 for p, y in zip(probs, hits)) / n
    ece = _ece(list(zip(probs, hits)))
    mean_conf = sum(probs) / n
    # ROI proxy: edge vs 50% break-even weighted by confidence
    roi_proxy = round(sum((y - 0.5) * p for y, p in zip(hits, probs)) / n, 4)

    return ReplayMetrics(
        window=n,
        market_id=rows[0].get("market_id", "first_goal_team"),
        weight_label=weight_label,
        n=n,
        accuracy=round(accuracy, 4),
        brier=round(brier, 4),
        ece=ece,
        roi_proxy=roi_proxy,
        mean_confidence=round(mean_conf, 4),
    )


def bootstrap_accuracy_improvement(
    rows: list[dict[str, Any]],
    *,
    iterations: int = BOOTSTRAP_ITERATIONS,
) -> float:
    """Fraction of bootstrap samples where new accuracy >= old accuracy."""
    if len(rows) < 20:
        return 0.5
    n = len(rows)
    wins = 0
    for _ in range(iterations):
        sample = [rows[random.randrange(n)] for _ in range(n)]
        old_acc = sum(r["old_hit"] for r in sample) / n
        new_acc = sum(r["new_hit"] for r in sample) / n
        if new_acc >= old_acc - 1e-9:
            wins += 1
    return round(wins / iterations, 4)


def compare_windows(
    all_rows: list[dict[str, Any]],
    *,
    market_id: str = "first_goal_team",
    windows: tuple[int, ...] = REPLAY_WINDOWS,
) -> list[WindowComparison]:
    comparisons: list[WindowComparison] = []
    for window in windows:
        slice_rows = all_rows[-window:] if len(all_rows) >= window else all_rows
        for r in slice_rows:
            r["market_id"] = market_id
        old_m = compute_metrics(slice_rows, weight_label="old_weights", prob_key="old_prob", hit_key="old_hit")
        new_m = compute_metrics(slice_rows, weight_label="new_weights", prob_key="new_prob", hit_key="new_hit")
        old_m.window = window
        new_m.window = window
        picks_changed = sum(1 for r in slice_rows if r.get("pick_changed"))

        comparisons.append(
            WindowComparison(
                window=window,
                market_id=market_id,
                old=old_m,
                new=new_m,
                delta_accuracy=round(new_m.accuracy - old_m.accuracy, 4),
                delta_brier=round(new_m.brier - old_m.brier, 4),
                delta_ece=round(new_m.ece - old_m.ece, 4),
                delta_roi_proxy=round(new_m.roi_proxy - old_m.roi_proxy, 4),
                picks_changed=picks_changed,
                bootstrap_p_improve=bootstrap_accuracy_improvement(slice_rows),
            )
        )
    return comparisons


def should_accept_comparison(comp: WindowComparison) -> bool:
    """Accept if accuracy improves OR calibration improves without meaningful regression."""
    acc_better = comp.delta_accuracy > 0
    cal_better = comp.delta_brier < 0 or comp.delta_ece < 0
    no_regression = comp.delta_accuracy >= -REGRESSION_TOLERANCE_ACCURACY
    if acc_better and no_regression:
        return True
    if cal_better and no_regression:
        return True
    return False


def decide_market_acceptance(comparisons: list[WindowComparison]) -> ApprovalStatus:
    if not comparisons:
        return "INSUFFICIENT_DATA"
    # Primary window: 500 if available else largest
    primary = next((c for c in comparisons if c.window == 500), comparisons[-1])
    if primary.old.n < 100:
        return "INSUFFICIENT_DATA"
    if should_accept_comparison(primary):
        return "ACCEPT"
    if primary.delta_accuracy == 0 and primary.delta_brier == 0 and primary.delta_ece == 0:
        return "HOLD"
    return "REJECT"


def build_component_reports(
    recommendations: list[dict[str, Any]],
    comparisons: list[WindowComparison],
    component_scores_path: Any = None,
) -> list[ComponentLearningReport]:
    primary = next((c for c in comparisons if c.window == 500), comparisons[-1] if comparisons else None)
    market_status = decide_market_acceptance(comparisons) if primary else "INSUFFICIENT_DATA"

    # Load help rates from 58A if available
    help_rates: dict[tuple[str, str], float] = {}
    if component_scores_path and __import__("pathlib").Path(component_scores_path).is_file():
        import json

        scores = json.loads(__import__("pathlib").Path(component_scores_path).read_text(encoding="utf-8"))
        for s in scores:
            if s.get("window") == 100 and s.get("league_id") is None:
                key = (s.get("component_id"), s.get("market_id"))
                help_rates[key] = float(s.get("help_rate", 0)) - float(s.get("hurt_rate", 0))

    reports: list[ComponentLearningReport] = []
    for rec in recommendations:
        cid = str(rec.get("component_id") or "")
        market_id = str(rec.get("market_id") or "")
        delta_w = float(rec.get("delta") or 0)
        direction = str(rec.get("direction") or "hold")

        if direction == "hold" or abs(delta_w) < 1e-6:
            status: ApprovalStatus = "HOLD"
            reason = rec.get("reason") or "no weight change recommended"
            exp_acc = 0.0
            exp_brier = 0.0
            conf = 0.5
        elif market_id not in ("first_goal_team", "team_to_score_first"):
            status = "INSUFFICIENT_DATA"
            reason = "no replay data for this market in 58B simulation"
            exp_acc = 0.0
            exp_brier = 0.0
            conf = 0.3
        else:
            edge = help_rates.get((cid, market_id), 0.0)
            exp_acc = round((primary.delta_accuracy if primary else 0) * abs(delta_w) * 10, 4) if primary else 0.0
            exp_brier = round((primary.delta_brier if primary else 0) * abs(delta_w) * 10, 4) if primary else 0.0
            conf = round(min(0.95, 0.5 + abs(edge) + (primary.bootstrap_p_improve or 0.5) * 0.2), 4) if primary else 0.3

            if market_status == "ACCEPT" and direction == "increase" and edge >= 0:
                status = "ACCEPT"
                reason = f"market bundle accepted; component edge={edge:+.3f}"
            elif market_status == "REJECT" or (direction == "increase" and edge < 0):
                status = "REJECT"
                reason = f"market bundle rejected or negative component edge={edge:+.3f}"
            elif market_status == "HOLD":
                status = "HOLD"
                reason = "micro-shift — no measurable replay delta"
            else:
                status = "HOLD"
                reason = "marginal change — await more shadow data"

        reports.append(
            ComponentLearningReport(
                component_id=cid,
                market_id=market_id,
                current_weight=float(rec.get("current_weight") or 0),
                recommended_weight=float(rec.get("recommended_weight") or 0),
                expected_gain_accuracy=exp_acc,
                expected_gain_brier=exp_brier,
                confidence=conf,
                approval_status=status,
                reason=reason,
            )
        )
    return reports


def decide_simulation_recommendation(
    comparisons: list[WindowComparison],
    reports: list[ComponentLearningReport],
) -> str:
    if not comparisons:
        return "NEEDS_MORE_DATA"
    primary = next((c for c in comparisons if c.window == 500), comparisons[-1])
    if primary.old.n < 100:
        return "NEEDS_MORE_DATA"

    any_improvement = (
        primary.delta_accuracy > 0
        or primary.delta_brier < 0
        or primary.delta_ece < 0
        or primary.delta_roi_proxy > 0
    )
    accepted = sum(1 for r in reports if r.approval_status == "ACCEPT")

    if not any_improvement and primary.picks_changed == 0:
        return "NO_IMPROVEMENT"

    if should_accept_comparison(primary) and accepted > 0:
        return "LEARNING_SIMULATION_READY"

    if any_improvement or primary.bootstrap_p_improve and primary.bootstrap_p_improve >= 0.55:
        return "NEEDS_MORE_DATA"

    return "NO_IMPROVEMENT"
