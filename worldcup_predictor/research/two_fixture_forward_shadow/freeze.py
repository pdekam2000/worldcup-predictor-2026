"""Immutable append-only portfolio freeze (hypothetical stakes only)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.research.two_fixture_forward_shadow.constants import (
    BOOK_MIN_STAKE,
    BOOKMAKER_MODE_CROSS,
    BOOKMAKER_MODE_SINGLE,
    COHORT_A_END,
    COHORT_B_END,
    DEFAULT_BUDGET,
    HEDGE_POLICY_VERSION,
    MAX_STANDARD_HEDGES,
    ODDS_INGESTION_VERSION,
    PRIMARY_STAKE_BENCHMARK,
    RULE_VERSION,
    STAKE_STRATEGIES,
    STAKE_VERSION,
    STRATEGY_VERSION,
)
from worldcup_predictor.research.two_fixture_forward_shadow.ddl import ensure_tfps_schema
from worldcup_predictor.research.two_fixture_portfolio.engine import (
    build_primary_matrix,
    classify_arbitrage,
    equal_gross_stakes,
    equal_stakes,
    minimax_equalize_covered,
    model_prob_stakes,
    positive_edge_stakes,
    select_hedge_candidates,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hash(obj: Any) -> str:
    blob = json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def assign_cohort(completed_before: int) -> str:
    """Immutable cohort label based on count of completed portfolios before this freeze."""
    n = completed_before + 1  # this portfolio's ordinal if completed later
    if n <= COHORT_A_END:
        return "A"
    if n <= COHORT_B_END:
        return "B"
    return "C"


def _odds_maps(fx: dict, mode: str) -> tuple[dict[str, float], str | None]:
    if mode == BOOKMAKER_MODE_SINGLE:
        best_name, best_n, best_m = None, -1, {}
        for bm, m in (fx.get("bm_maps") or {}).items():
            n = sum(1 for s in fx["top5_scores"] if s in m)
            if n > best_n:
                best_name, best_n, best_m = bm, n, m
        return best_m, best_name
    return dict(fx.get("cs_odds") or {}), None


def _allocate(tickets: list[dict], strategy: str, budget: float) -> list[float]:
    odds = [t.get("combo_odds") for t in tickets]
    probs = [float(t["joint_p_independence"]) for t in tickets]
    priced = [i for i, o in enumerate(odds) if o is not None]
    if not priced:
        return [0.0] * len(tickets)
    min_s = BOOK_MIN_STAKE
    if strategy == "EQUAL":
        raw = equal_stakes(len(priced), budget, min_s)
    elif strategy == "EQUAL_GROSS_RETURN":
        raw = equal_gross_stakes([odds[i] for i in priced], budget, min_s)
    elif strategy in {"PROBABILITY_WEIGHTED", "MODEL_PROB_WEIGHTED"}:
        raw = model_prob_stakes([probs[i] for i in priced], budget, min_s)
    elif strategy in {"POSITIVE_EDGE_ONLY", "POSITIVE_EDGE"}:
        raw = positive_edge_stakes(
            [probs[i] for i in priced], [odds[i] for i in priced], budget, min_s, 0.05
        )
    elif strategy == "MINIMAX":
        raw, _ = minimax_equalize_covered([odds[i] for i in priced], budget, min_s)
    elif strategy == "TIERED_PRIMARY_HEDGE":
        w = []
        for i in priced:
            t = tickets[i]
            base = float(t["joint_p_independence"])
            w.append(3 * base if t["rank_a"] <= 2 and t["rank_b"] <= 2 else base)
        raw = model_prob_stakes(w, budget, min_s)
    else:
        raw = equal_gross_stakes([odds[i] for i in priced], budget, min_s)
    stakes = [0.0] * len(tickets)
    for j, i in enumerate(priced):
        stakes[i] = float(raw[j]) if j < len(raw) else 0.0
    for i, s in enumerate(stakes):
        if 0 < s < BOOK_MIN_STAKE:
            stakes[i] = 0.0
    tot = sum(stakes)
    if tot > 0:
        stakes = [s * (budget / tot) for s in stakes]
    return stakes


def _hedge_tickets(a: dict, b: dict, total_primary: float, max_hedges: int = MAX_STANDARD_HEDGES) -> list[dict]:
    out = []
    for side, fx in (("A", a), ("B", b)):
        prof = fx.get("profile") or {}
        cands = select_hedge_candidates(
            {
                "top5_scores": fx.get("top5_scores") or prof.get("top5_scores") or [],
                "top10_scores": fx.get("top10_scores") or prof.get("top10_scores") or [],
                "shifted_complementary": fx.get("shifted") or prof.get("shifted_complementary") or [],
                "prob_map": prof.get("prob_map") or {},
                "model_p_draw": fx.get("model_p_draw") or prof.get("model_p_draw") or 0.25,
                "model_p_home": fx.get("model_p_home") or prof.get("model_p_home") or 0.4,
                "model_p_away": fx.get("model_p_away") or prof.get("model_p_away") or 0.35,
                "total_lambda": float(prof.get("total_lambda") or 2.5),
            },
            max_extra=max_hedges,
        )
        for h in cands[: max(1, max_hedges // 2 + 1)]:
            odd = (fx.get("cs_odds") or {}).get(h["selection"])
            if odd is None:
                continue
            stake = min(total_primary * 0.04, total_primary / float(odd))
            if stake < BOOK_MIN_STAKE:
                cls = "TOO_EXPENSIVE"
            elif stake * float(odd) >= total_primary - 1e-9:
                cls = "FULL_STAKE_RECOVERY_POSSIBLE"
            elif stake * float(odd) >= 0.5 * total_primary:
                cls = "PARTIAL_RECOVERY_ONLY"
            else:
                cls = "COVERAGE_ONLY"
            out.append(
                {
                    "fixture_side": side,
                    "fixture_id": fx["fixture_id"],
                    "selection": h["selection"],
                    "kind": h["kind"],
                    "source": "canonical_top6_10" if h["kind"] == "canonical_top6_10" else h["kind"],
                    "decimal_odds": float(odd),
                    "stake": stake,
                    "gross_if_win": stake * float(odd),
                    "failure_scenario": h.get("failure_scenario"),
                    "reason": h.get("reason"),
                    "hedge_classification": cls,
                    "replaces_top5": False,
                    "odds_kind": "REAL",
                }
            )
    # cap total hedges to MAX_STANDARD_HEDGES
    out = sorted(out, key=lambda x: -float(x.get("decimal_odds") or 0))[:MAX_STANDARD_HEDGES]
    return out


def build_portfolio_freeze(
    pair: dict[str, Any],
    *,
    snapshot_window: str,
    bookmaker_mode: str,
    stake_strategy: str = PRIMARY_STAKE_BENCHMARK,
    budget: float = DEFAULT_BUDGET,
    cohort: str = "A",
    prediction_freeze_ids: tuple[str | None, str | None] = (None, None),
    require_full_top5: bool = False,
) -> dict[str, Any] | None:
    a = pair["fixture_a_obj"]
    b = pair["fixture_b_obj"]
    odds_a, bm_a = _odds_maps(a, bookmaker_mode)
    odds_b, bm_b = _odds_maps(b, bookmaker_mode)
    tickets = build_primary_matrix(a["profile"]["top5"] if a.get("profile") else _top5_dicts(a), b["profile"]["top5"] if b.get("profile") else _top5_dicts(b), odds_a, odds_b)
    priced = sum(1 for t in tickets if t["combo_odds"] is not None)
    if require_full_top5 and priced < 25:
        return None
    if priced < 10:
        return None

    stakes = _allocate(tickets, stake_strategy, budget)
    total_primary = sum(stakes)
    primary_out = []
    covered_nets = []
    max_ret = -1e18
    for t, s in zip(tickets, stakes):
        gross = (s * float(t["combo_odds"])) if t["combo_odds"] is not None and s > 0 else 0.0
        net = gross - total_primary if t["combo_odds"] is not None else None
        if t["combo_odds"] is not None and s > 0:
            covered_nets.append(gross - total_primary)
            max_ret = max(max_ret, gross - total_primary)
        primary_out.append(
            {
                **{k: t[k] for k in t},
                "stake": s,
                "gross_return_if_win": gross,
                "net_portfolio_if_win": net,
                "odds_kind": "REAL" if t["combo_odds"] is not None else "UNAVAILABLE",
                "synthetic": False,
                "bookmaker_mode": bookmaker_mode,
                "stakes_hypothetical": True,
            }
        )

    hedges = _hedge_tickets(a, b, total_primary)
    hedge_stake = sum(h["stake"] for h in hedges)
    total_stake = total_primary + hedge_stake
    min_cov = min(covered_nets) if covered_nets else -total_primary
    joint = float(a["top5_mass"]) * float(b["top5_mass"])
    hedge_cov = float(a.get("profile", {}).get("canonical_union_shifted_mass") or a["top5_mass"]) * float(
        b.get("profile", {}).get("canonical_union_shifted_mass") or b["top5_mass"]
    )
    odds_ts = _utc_now()
    payload = {
        "pair_id": pair["pair_id"],
        "fixture_a": a["fixture_id"],
        "fixture_b": b["fixture_id"],
        "snapshot_window": snapshot_window,
        "bookmaker_mode": bookmaker_mode,
        "stake_strategy": stake_strategy,
        "budget_eur": budget,
        "primary_tickets": primary_out,
        "hedge_tickets": hedges,
        "strategy_version": STRATEGY_VERSION,
        "betting_enabled": False,
        "stakes_hypothetical": True,
    }
    source_hash = _hash(
        {
            "a": a["fixture_id"],
            "b": b["fixture_id"],
            "oa": odds_a,
            "ob": odds_b,
            "window": snapshot_window,
            "mode": bookmaker_mode,
            "strategy": stake_strategy,
        }
    )
    freeze_hash = _hash(payload)
    portfolio_id = "pf_" + freeze_hash[:20]
    arb = classify_arbitrage(
        [float(t["combo_odds"]) for t in tickets if t["combo_odds"] is not None]
    )
    return {
        "portfolio_id": portfolio_id,
        "pair_id": pair["pair_id"],
        "report_date": pair["report_date"],
        "frozen_at_utc": odds_ts,
        "snapshot_window": snapshot_window,
        "bookmaker_mode": bookmaker_mode,
        "fixture_a": int(a["fixture_id"]),
        "fixture_b": int(b["fixture_id"]),
        "kickoff_a_utc": a.get("kickoff_utc"),
        "kickoff_b_utc": b.get("kickoff_utc"),
        "prediction_freeze_id_a": prediction_freeze_ids[0],
        "prediction_freeze_id_b": prediction_freeze_ids[1],
        "ecse_version": "generate_score_distribution_readonly",
        "strategy_version": STRATEGY_VERSION,
        "rule_version": RULE_VERSION,
        "hedge_policy_version": HEDGE_POLICY_VERSION,
        "stake_version": STAKE_VERSION,
        "odds_ingestion_version": ODDS_INGESTION_VERSION,
        "cohort": cohort,
        "stake_strategy": stake_strategy,
        "budget_eur": budget,
        "total_primary_stake": total_primary,
        "hedge_stake": hedge_stake,
        "total_stake": total_stake,
        "stakes_hypothetical": 1,
        "primary_tickets_json": json.dumps(primary_out),
        "hedge_tickets_json": json.dumps(hedges),
        "odds_timestamp_utc": odds_ts,
        "bookmakers_json": json.dumps({"a": bm_a, "b": bm_b}),
        "expected_joint_coverage": joint,
        "hedge_enhanced_coverage": hedge_cov,
        "expected_value_est": None,
        "full_loss_prob_est": max(0.0, 1.0 - hedge_cov),
        "min_covered_return": min_cov,
        "max_return": max_ret if max_ret > -1e17 else None,
        "worst_case_loss": -total_stake,
        "source_hash": source_hash,
        "freeze_hash": freeze_hash,
        "payload_json": json.dumps(payload),
        "betting_enabled": 0,
        "priced_primary_n": priced,
        "arbitrage_note": arb,
        "canonical_top5_unchanged": True,
        "shifted_secondary_only": True,
    }


def _top5_dicts(fx: dict) -> list[dict]:
    prof = fx.get("profile") or {}
    if prof.get("top5"):
        return prof["top5"]
    # rebuild minimal
    scores = fx.get("top5_scores") or []
    return [{"score": s, "probability": 0.08} for s in scores]


def persist_freeze(conn, freeze: dict[str, Any]) -> bool:
    """Insert freeze; returns False if duplicate (idempotent)."""
    ensure_tfps_schema(conn)
    before = conn.total_changes
    conn.execute(
        """
        INSERT OR IGNORE INTO tfps_portfolio_freezes (
            portfolio_id, pair_id, report_date, frozen_at_utc, snapshot_window, bookmaker_mode,
            fixture_a, fixture_b, kickoff_a_utc, kickoff_b_utc, prediction_freeze_id_a,
            prediction_freeze_id_b, ecse_version, strategy_version, rule_version,
            hedge_policy_version, stake_version, odds_ingestion_version, cohort, stake_strategy,
            budget_eur, total_primary_stake, hedge_stake, total_stake, stakes_hypothetical,
            primary_tickets_json, hedge_tickets_json, odds_timestamp_utc, bookmakers_json,
            expected_joint_coverage, hedge_enhanced_coverage, expected_value_est,
            full_loss_prob_est, min_covered_return, max_return, worst_case_loss,
            source_hash, freeze_hash, payload_json, betting_enabled
        ) VALUES (
            :portfolio_id, :pair_id, :report_date, :frozen_at_utc, :snapshot_window, :bookmaker_mode,
            :fixture_a, :fixture_b, :kickoff_a_utc, :kickoff_b_utc, :prediction_freeze_id_a,
            :prediction_freeze_id_b, :ecse_version, :strategy_version, :rule_version,
            :hedge_policy_version, :stake_version, :odds_ingestion_version, :cohort, :stake_strategy,
            :budget_eur, :total_primary_stake, :hedge_stake, :total_stake, :stakes_hypothetical,
            :primary_tickets_json, :hedge_tickets_json, :odds_timestamp_utc, :bookmakers_json,
            :expected_joint_coverage, :hedge_enhanced_coverage, :expected_value_est,
            :full_loss_prob_est, :min_covered_return, :max_return, :worst_case_loss,
            :source_hash, :freeze_hash, :payload_json, :betting_enabled
        )
        """,
        {k: freeze[k] for k in freeze if k in {
            "portfolio_id", "pair_id", "report_date", "frozen_at_utc", "snapshot_window", "bookmaker_mode",
            "fixture_a", "fixture_b", "kickoff_a_utc", "kickoff_b_utc", "prediction_freeze_id_a",
            "prediction_freeze_id_b", "ecse_version", "strategy_version", "rule_version",
            "hedge_policy_version", "stake_version", "odds_ingestion_version", "cohort", "stake_strategy",
            "budget_eur", "total_primary_stake", "hedge_stake", "total_stake", "stakes_hypothetical",
            "primary_tickets_json", "hedge_tickets_json", "odds_timestamp_utc", "bookmakers_json",
            "expected_joint_coverage", "hedge_enhanced_coverage", "expected_value_est",
            "full_loss_prob_est", "min_covered_return", "max_return", "worst_case_loss",
            "source_hash", "freeze_hash", "payload_json", "betting_enabled",
        }},
    )
    inserted = conn.total_changes > before
    conn.commit()
    return inserted


def freeze_parallel_strategies(
    pair: dict[str, Any],
    *,
    snapshot_window: str,
    completed_count: int,
) -> list[dict[str, Any]]:
    """Freeze primary benchmark + parallel strategies for single and cross modes."""
    cohort = assign_cohort(completed_count)
    out = []
    for mode in (BOOKMAKER_MODE_SINGLE, BOOKMAKER_MODE_CROSS):
        for strategy in STAKE_STRATEGIES:
            fz = build_portfolio_freeze(
                pair,
                snapshot_window=snapshot_window,
                bookmaker_mode=mode,
                stake_strategy=strategy,
                budget=DEFAULT_BUDGET,
                cohort=cohort,
            )
            if fz:
                out.append(fz)
    return out
