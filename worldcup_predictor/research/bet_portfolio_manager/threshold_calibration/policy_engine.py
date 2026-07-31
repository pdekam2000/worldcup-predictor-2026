"""Day replay under a policy dict (baseline or candidate) — research-only."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from worldcup_predictor.research.bet_portfolio_manager.correlation import analyze_diversification
from worldcup_predictor.research.bet_portfolio_manager.daily_score import compute_daily_portfolio_score
from worldcup_predictor.research.bet_portfolio_manager.fixture_ranking import rank_fixtures
from worldcup_predictor.research.bet_portfolio_manager.input_adapter import attach_outcomes, normalize_fixture
from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.constants import BASELINE_POLICY


def _day_key(raw: dict[str, Any], idx: int) -> str:
    k = str(raw.get("kickoff") or "")[:10]
    if len(k) >= 10:
        return k
    return f"bucket_{(idx // 3):05d}"


def group_days(fixtures: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for i, raw in enumerate(fixtures):
        fx = attach_outcomes(normalize_fixture(raw))
        by[_day_key(raw, i)].append(fx)
    return dict(sorted(by.items(), key=lambda kv: kv[0]))


def league_reliability(fixtures: list[dict[str, Any]]) -> dict[str, float]:
    by: dict[str, list[int]] = defaultdict(list)
    for raw in fixtures:
        fx = attach_outcomes(normalize_fixture(raw))
        if fx.get("hit_insurance") is None:
            continue
        by[str(fx.get("league") or "unknown")].append(1 if fx["hit_insurance"] else 0)
    return {k: (sum(v) / len(v) if v else 0.55) for k, v in by.items()}


def _grade(score: float, grade_thr: dict[str, float]) -> str:
    for g in ("S", "A", "B", "C", "D", "F"):
        if score >= float(grade_thr.get(g, 0.0)):
            return g
    return "F"


def _base_action(score: float, action_thr: dict[str, float]) -> str:
    if score >= float(action_thr.get("BET", 84)):
        return "BET"
    if score >= float(action_thr.get("SMALL_BET", 72)):
        return "SMALL_BET"
    if score >= float(action_thr.get("WATCH", 55)):
        return "WATCH_NO_CAPITAL"
    return "HARD_SKIP"


def evaluate_gates(
    daily: dict[str, Any],
    rankings: dict[str, Any],
    diversification: dict[str, Any],
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    """Gate audit. Veto-active gates match baseline no_bet.py; others are informational."""
    gates_cfg = policy.get("gates") or {}
    comps = daily.get("components") or {}
    checks: list[dict[str, Any]] = []

    def add(name: str, observed: float, threshold: float, op: str, failed: bool, *, veto: bool) -> None:
        dist = observed - threshold if op == ">=" else threshold - observed
        checks.append(
            {
                "gate": name,
                "observed": round(float(observed), 6),
                "threshold": round(float(threshold), 6),
                "operator": op,
                "failed": bool(failed),
                "veto_active": bool(veto),
                "distance_from_threshold": round(float(dist), 6),
            }
        )

    # --- Veto-active (mirrors decide_no_bet) ---
    add(
        "entropy_threshold",
        float(comps.get("low_entropy") or 0),
        float(gates_cfg.get("low_entropy_min", 35)),
        ">=",
        float(comps.get("low_entropy") or 0) < float(gates_cfg.get("low_entropy_min", 35)),
        veto=True,
    )
    add(
        "confidence_threshold",
        float(comps.get("mean_confidence") or 0),
        float(gates_cfg.get("mean_confidence_min", 35)),
        ">=",
        float(comps.get("mean_confidence") or 0) < float(gates_cfg.get("mean_confidence_min", 35)),
        veto=True,
    )
    ins = float(comps.get("insurance_contribution") or 0)
    cov = float(comps.get("coverage_mass") or 0)
    weak_ins = ins < float(gates_cfg.get("insurance_contribution_min", 15))
    weak_cov = cov < float(gates_cfg.get("coverage_mass_min_when_weak_ins", 55))
    add(
        "insurance_effectiveness_threshold",
        ins,
        float(gates_cfg.get("insurance_contribution_min", 15)),
        ">=",
        weak_ins and weak_cov,
        veto=True,
    )
    add(
        "league_reliability_threshold",
        float(comps.get("league_reliability") or 0),
        float(gates_cfg.get("league_reliability_min", 35)),
        ">=",
        float(comps.get("league_reliability") or 0) < float(gates_cfg.get("league_reliability_min", 35)),
        veto=True,
    )
    add(
        "correlation_penalty",
        1.0 if diversification.get("over_concentrated") else 0.0,
        0.5,
        "<",
        bool(diversification.get("over_concentrated")),
        veto=True,
    )
    n_elig = int(rankings.get("n_eligible") or 0)
    add("fixture_count_rule", float(n_elig), 1.0, ">=", n_elig == 0, veto=True)

    # --- Informational / attribution only (do not veto beyond baseline) ---
    add(
        "diversification_threshold",
        float(comps.get("low_correlation") or 0),
        40.0,
        ">=",
        float(comps.get("low_correlation") or 0) < 40.0,
        veto=False,
    )
    add(
        "residual_risk_threshold",
        float(comps.get("low_residual_risk") or 0),
        40.0,
        ">=",
        float(comps.get("low_residual_risk") or 0) < 40.0,
        veto=False,
    )
    add(
        "market_quality_threshold",
        float(comps.get("odds_balance") or 0),
        30.0,
        ">=",
        float(comps.get("odds_balance") or 0) < 30.0,
        veto=False,
    )
    add("odds_completeness_rule", 1.0, 1.0, ">=", False, veto=False)
    add(
        "maximum_exposure_rule",
        float(gates_cfg.get("max_day_exposure_frac", 0.6)),
        1.0,
        "<=",
        False,
        veto=False,
    )
    add("drawdown_state_rule", 1.0, 1.0, ">=", False, veto=False)
    add(
        "calibration_quality_rule",
        float(comps.get("calibration_quality") or 50.0),
        0.0,
        ">=",
        False,
        veto=False,
    )
    add(
        "daily_portfolio_score",
        float(daily.get("daily_portfolio_score") or 0),
        float((policy.get("action_thresholds") or {}).get("WATCH", 55)),
        ">=",
        float(daily.get("daily_portfolio_score") or 0)
        < float((policy.get("action_thresholds") or {}).get("WATCH", 55)),
        veto=False,
    )
    add(
        "grade_boundary",
        float(daily.get("daily_portfolio_score") or 0),
        float((policy.get("grade_thresholds") or {}).get("B", 72)),
        ">=",
        float(daily.get("daily_portfolio_score") or 0)
        < float((policy.get("grade_thresholds") or {}).get("B", 72)),
        veto=False,
    )
    return checks


def decide_under_policy(
    fixtures: list[dict[str, Any]],
    *,
    policy: dict[str, Any],
    league_reliability_map: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Deterministic day decision under an explicit policy (baseline or candidate)."""
    pol = policy or BASELINE_POLICY
    lr = league_reliability_map or {}
    daily = compute_daily_portfolio_score(fixtures, league_reliability=lr)
    score = float(daily.get("daily_portfolio_score") or 0.0)
    grade = _grade(score, pol.get("grade_thresholds") or BASELINE_POLICY["grade_thresholds"])
    base_action = _base_action(score, pol.get("action_thresholds") or BASELINE_POLICY["action_thresholds"])
    daily = {**daily, "grade": grade, "recommendation": base_action, "daily_portfolio_score": score}

    ranking = rank_fixtures(fixtures, league_reliability=lr)
    min_fx = float((pol.get("gates") or {}).get("min_fixture_score_to_bet", 55.0))
    for r in ranking["rankings"]:
        r["eligible_for_capital"] = float(r.get("investment_priority") or 0) >= min_fx
    ranking["n_eligible"] = sum(1 for r in ranking["rankings"] if r["eligible_for_capital"])

    div = analyze_diversification(fixtures)
    gates = evaluate_gates(daily, ranking, div, pol)
    failed_veto = [g for g in gates if g["failed"] and g.get("veto_active")]
    failed_all = [g for g in gates if g["failed"]]
    failed_sorted = sorted(failed_veto or failed_all, key=lambda g: abs(float(g["distance_from_threshold"])), reverse=True)

    action = base_action
    n_fail = len(failed_veto)
    n_elig = int(ranking["n_eligible"])
    atr = pol.get("action_thresholds") or {}
    if n_fail:
        if action == "BET":
            action = (
                "SMALL_BET"
                if score >= float(atr.get("SMALL_BET", 72)) and n_elig >= 1
                else "WATCH_NO_CAPITAL"
            )
        elif action == "SMALL_BET":
            action = "WATCH_NO_CAPITAL"
        elif action == "WATCH_NO_CAPITAL" and n_fail >= 2:
            action = "HARD_SKIP"
        if n_fail >= 3 or n_elig == 0:
            action = "HARD_SKIP"

    watch_pos = False
    if action == "WATCH_NO_CAPITAL" and float(pol.get("watch_micro_allocation_ratio") or 0) > 0:
        near = score >= float(atr.get("SMALL_BET", 72)) - float(pol.get("watch_positive_score_slack", 5.0))
        comps = daily.get("components") or {}
        ok = (
            near
            and float(comps.get("low_residual_risk") or 0) >= 45
            and float(comps.get("insurance_contribution") or 0) >= 10
            and float(comps.get("league_reliability") or 0) >= 40
            and not div.get("over_concentrated")
            and n_elig >= 1
            and n_fail <= 1
        )
        if ok:
            watch_pos = True
            action = "WATCH_POSITIVE"

    dynamic_count = 0
    micro = float(pol.get("watch_micro_allocation_ratio") or 0.0)
    if action == "BET":
        if score >= 90:
            dynamic_count = min(5, n_elig)
        elif score >= float(atr.get("BET", 84)):
            dynamic_count = min(3, n_elig)
        else:
            dynamic_count = min(2, n_elig)
    elif action == "SMALL_BET":
        dynamic_count = min(2, n_elig)
    elif action == "WATCH_POSITIVE":
        dynamic_count = min(1, n_elig)
    else:
        dynamic_count = 0

    selected = [r for r in ranking["rankings"] if r.get("eligible_for_capital")][:dynamic_count]
    # Unit-stake parity with historical_validation for BET/SMALL_BET; micro only for WATCH_POSITIVE
    if action == "WATCH_POSITIVE":
        capital_scale = micro
    elif action in {"WATCH_NO_CAPITAL", "HARD_SKIP", "WATCH_REJECT"}:
        capital_scale = 0.0
    else:
        capital_scale = float(pol.get("bet_unit_scale", 1.0))
        if action == "SMALL_BET":
            capital_scale *= float(pol.get("small_bet_capital_scale", 1.0))

    unit_stakes = [{"fixture_id": r["fixture_id"], "stake_units": capital_scale} for r in selected]

    by_id = {int(f["fixture_id"]): f for f in fixtures}
    pnl = 0.0
    wins = losses = 0
    for s in unit_stakes:
        fx = by_id.get(int(s["fixture_id"])) or {}
        stake = float(s["stake_units"])
        if stake <= 0:
            continue
        if fx.get("hit_insurance") is True:
            odd = float(fx.get("insurance_odds") or fx.get("odds_home") or 2.0)
            pnl += stake * (odd - 1.0)
            wins += 1
        elif fx.get("hit_insurance") is False:
            pnl -= stake
            losses += 1

    exposure = sum(float(s["stake_units"]) for s in unit_stakes)
    zero_capital = exposure <= 1e-12
    return {
        "score": score,
        "grade": grade,
        "base_action": base_action,
        "action": action,
        "action_semantics": {
            "classification": action,
            "capital_allocated": not zero_capital,
            "zero_capital_day": zero_capital,
            "hard_rejection": action == "HARD_SKIP",
            "observation_only": action in {"WATCH_NO_CAPITAL", "WATCH_REJECT"},
        },
        "gates": gates,
        "failed_gates": failed_sorted,
        "strongest_blocker": failed_sorted[0] if failed_sorted else None,
        "second_strongest_blocker": failed_sorted[1] if len(failed_sorted) > 1 else None,
        "selected_fixture_ids": [int(r["fixture_id"]) for r in selected],
        "exposure_units": round(exposure, 6),
        "capital_scale": capital_scale,
        "realized_pnl_evaluation_only": round(pnl, 6),
        "realized_wins": wins,
        "realized_losses": losses,
        "n_fixtures": len(fixtures),
        "components": daily.get("components"),
        "diversification_score": div.get("diversification_score"),
        "over_concentrated": div.get("over_concentrated"),
        "predictions_not_modified": True,
        "result_not_used_in_decision": True,
    }


def replay_all_days(
    fixtures: list[dict[str, Any]],
    *,
    policy: dict[str, Any] | None = None,
    league_reliability_map: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    pol = policy or BASELINE_POLICY
    days = group_days(fixtures)
    lr = league_reliability_map if league_reliability_map is not None else league_reliability(fixtures)
    out = []
    for date, rows in days.items():
        dec = decide_under_policy(rows, policy=pol, league_reliability_map=lr)
        out.append({"date": date, "n_fixtures": len(rows), **dec, "fixtures": rows})
    return out
