#!/usr/bin/env python3
"""Two-fixture exact-score portfolio research — shadow only, no production betting."""
from __future__ import annotations

import csv
import json
import math
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.research.two_fixture_portfolio.engine import (
    INDEPENDENCE_NOTE,
    THREE_GOAL_OVER35_GAPS,
    build_primary_matrix,
    classify_arbitrage,
    equal_gross_stakes,
    equal_stakes,
    fixture_profile,
    fmt,
    minimax_equalize_covered,
    model_prob_stakes,
    parse_score,
    portfolio_returns,
    positive_edge_stakes,
    recommendation_label,
    scenario_coverage_for_fixture,
    select_hedge_candidates,
    synthetic_cs_odds_from_prob,
)

ART = ROOT / "artifacts" / "two_fixture_portfolio"
REPORTS = ROOT / "reports" / "owner"

# Locked budgets / thresholds (pre-declared)
BUDGETS = [10.0, 25.0, 50.0, 100.0]
MIN_STAKES = [0.10, 0.50, 1.00]
DEFAULT_BUDGET = 50.0
DEFAULT_MIN_STAKE = 0.50
MAX_HEDGE_CAP_OPTIONS = [5, 10, 15]
SYNTHETIC_REGIMES = ["low", "medium", "high"]
UNTOUCHED = "2025-10-01"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys: list[str] = []
    seen = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                keys.append(k)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in keys})


def inventory_odds(conn) -> dict[str, Any]:
    inv: dict[str, Any] = {
        "correct_score_historical_csv": 0,
        "correct_score_imports": 0,
        "over_35_rows": 0,
        "over_25_rows": 0,
        "btts_yes_rows": 0,
        "training_ou35_closing_nonnull": 0,
        "training_rows": 0,
        "real_exact_score_odds_available": False,
        "real_over35_odds_available": False,
        "note": "",
    }
    try:
        inv["correct_score_imports"] = int(
            conn.execute(
                """
                SELECT COUNT(1) FROM historical_csv_odds_imports
                WHERE lower(market) LIKE '%correct%' OR lower(market) LIKE '%exact score%'
                """
            ).fetchone()[0]
        )
    except Exception as e:
        inv["correct_score_imports_error"] = str(e)
    try:
        inv["over_35_rows"] = int(
            conn.execute(
                "SELECT COUNT(1) FROM historical_csv_odds_prematch_clean "
                "WHERE market='over_under' AND selection='over_35'"
            ).fetchone()[0]
        )
        inv["over_25_rows"] = int(
            conn.execute(
                "SELECT COUNT(1) FROM historical_csv_odds_prematch_clean "
                "WHERE market='over_under' AND selection='over_25'"
            ).fetchone()[0]
        )
        inv["btts_yes_rows"] = int(
            conn.execute(
                "SELECT COUNT(1) FROM historical_csv_odds_prematch_clean "
                "WHERE market='btts' AND selection='yes'"
            ).fetchone()[0]
        )
    except Exception as e:
        inv["prematch_clean_error"] = str(e)
    inv["real_exact_score_odds_available"] = inv["correct_score_imports"] > 0
    inv["real_over35_odds_available"] = inv["over_35_rows"] > 100
    inv["note"] = (
        "No historical correct-score market rows found in CSV imports/clean. "
        "Profitability research uses labeled SYNTHETIC exact-score odds only. "
        "Over 3.5 / BTTS closing odds from ecse_training_dataset are real when present."
    )
    return inv


def load_historical(conn) -> list[dict]:
    q = """
    SELECT
      t.registry_fixture_id AS fixture_id,
      t.kickoff_utc,
      t.league,
      t.season,
      t.home_team,
      t.away_team,
      t.exact_score,
      t.home_goals,
      t.away_goals,
      t.total_goals,
      lf.lambda_home,
      lf.lambda_away,
      lf.lambda_total,
      lf.data_quality_score,
      lf.implied_home_probability,
      lf.implied_draw_probability,
      lf.implied_away_probability,
      t.ou_over_25_closing,
      t.ou_over_35_closing,
      t.btts_yes_closing,
      t.btts_no_closing
    FROM ecse_training_dataset t
    JOIN ecse_lambda_features lf ON lf.registry_fixture_id = t.registry_fixture_id
    WHERE t.exact_score IS NOT NULL
      AND t.exact_score LIKE '%-%'
      AND lf.lambda_home IS NOT NULL
      AND lf.lambda_away IS NOT NULL
      AND COALESCE(lf.insufficient_odds_flag, 0) = 0
    ORDER BY t.kickoff_utc ASC, t.registry_fixture_id ASC
    """
    rows = [dict(r) for r in conn.execute(q).fetchall()]
    return rows


def enrich(row: dict) -> dict[str, Any] | None:
    ps = parse_score(str(row["exact_score"]))
    if not ps:
        return None
    lh, la = float(row["lambda_home"]), float(row["lambda_away"])
    prof = fixture_profile(lh, la)
    ah, aw = ps
    actual = fmt(ah, aw)
    day = str(row["kickoff_utc"])[:10]
    return {
        **{k: row[k] for k in row},
        **{k: prof[k] for k in prof if k != "prob_map"},
        "prob_map": prof["prob_map"],
        "actual_score": actual,
        "actual_goals": ah + aw,
        "day": day,
        "in_top5": actual in prof["top5_scores"],
        "in_top10": actual in prof["top10_scores"],
        "in_union10": actual in prof["union_scores_upto10"],
        "in_shifted": actual in prof["shifted_complementary"],
    }


def pair_eligible(a: dict, b: dict) -> bool:
    if a["fixture_id"] == b["fixture_id"]:
        return False
    if a["suitability"] == "NO_PORTFOLIO" or b["suitability"] == "NO_PORTFOLIO":
        return False
    return True


def joint_coverage(a: dict, b: dict, mode: str) -> float:
    """Independence joint coverage estimate."""
    if mode == "canonical":
        return float(a["top5_mass"]) * float(b["top5_mass"])
    if mode == "union10":
        return float(a["canonical_union_shifted_mass"]) * float(b["canonical_union_shifted_mass"])
    if mode == "hit_actual_canon":
        return float(a["in_top5"] and b["in_top5"])
    if mode == "hit_actual_union":
        return float(a["in_union10"] and b["in_union10"])
    return 0.0


def select_pair(day_rows: list[dict], strategy: str, rng: random.Random) -> tuple[dict, dict] | None:
    elig = [r for r in day_rows if r["suitability"] in {"PORTFOLIO_ELIGIBLE", "HEDGE_ONLY", "EXACT_SCORE_WEAK"}]
    elig = [r for r in elig if r["suitability"] != "NO_PORTFOLIO"]
    if len(elig) < 2:
        return None
    if strategy == "random_eligible":
        a, b = rng.sample(elig, 2)
        return a, b
    if strategy == "highest_top5_mass":
        ranked = sorted(elig, key=lambda r: -float(r["top5_mass"]))
        return ranked[0], ranked[1]
    if strategy == "lowest_entropy":
        ranked = sorted(elig, key=lambda r: float(r["entropy"]))
        return ranked[0], ranked[1]
    if strategy == "strongest_suitability":
        order = {"PORTFOLIO_ELIGIBLE": 0, "HEDGE_ONLY": 1, "EXACT_SCORE_WEAK": 2}
        ranked = sorted(
            elig,
            key=lambda r: (order.get(r["suitability"], 9), -float(r["top5_mass"])),
        )
        return ranked[0], ranked[1]
    if strategy == "highest_expected_joint":
        best = None
        best_j = -1.0
        for i in range(len(elig)):
            for j in range(i + 1, len(elig)):
                jv = float(elig[i]["top5_mass"]) * float(elig[j]["top5_mass"])
                if jv > best_j:
                    best_j = jv
                    best = (elig[i], elig[j])
        return best
    if strategy == "domain_diverse":
        # prefer different leagues
        by_lg: dict[str, list] = defaultdict(list)
        for r in elig:
            by_lg[str(r.get("league") or "UNK")].append(r)
        leagues = list(by_lg.keys())
        if len(leagues) >= 2:
            lg = rng.sample(leagues, 2)
            return by_lg[lg[0]][0], by_lg[lg[1]][0]
        ranked = sorted(elig, key=lambda r: -float(r["top5_mass"]))
        return ranked[0], ranked[1]
    if strategy == "same_league":
        by_lg = defaultdict(list)
        for r in elig:
            by_lg[str(r.get("league") or "UNK")].append(r)
        cands = [v for v in by_lg.values() if len(v) >= 2]
        if not cands:
            return None
        group = max(cands, key=len)
        ranked = sorted(group, key=lambda r: -float(r["top5_mass"]))
        return ranked[0], ranked[1]
    if strategy == "cross_league":
        return select_pair(day_rows, "domain_diverse", rng)
    return None


def evaluate_pair_hit(a: dict, b: dict, hedge_a: list[str], hedge_b: list[str]) -> dict[str, Any]:
    cover_a = set(a["top5_scores"]) | set(hedge_a)
    cover_b = set(b["top5_scores"]) | set(hedge_b)
    primary_hit = bool(a["in_top5"] and b["in_top5"])
    hedge_hit = bool(a["actual_score"] in cover_a and b["actual_score"] in cover_b)
    return {
        "primary_hit": int(primary_hit),
        "hedge_hit": int(hedge_hit),
        "a_in_top5": int(a["in_top5"]),
        "b_in_top5": int(b["in_top5"]),
        "joint_canon_model": joint_coverage(a, b, "canonical"),
        "joint_union_model": joint_coverage(a, b, "union10"),
    }


def over35_structure_analysis(a: dict, b: dict, budget: float = DEFAULT_BUDGET) -> list[dict[str, Any]]:
    """Test Over 3.5 hedge structures with REAL closing odds when available."""
    oa = a.get("ou_over_35_closing")
    ob = b.get("ou_over_35_closing")
    oa = float(oa) if oa is not None else None
    ob = float(ob) if ob is not None else None
    # allocate 80% to abstract primary pot, 20% hedges for structure comparison
    primary_pot = budget * 0.80
    hedge_pot = budget * 0.20

    structures = []

    def add(name: str, legs: list[tuple[str, float | None]], gaps_note: str):
        # equal stake on legs
        n = max(1, len(legs))
        stake_each = hedge_pot / n if legs else 0.0
        total = primary_pot + stake_each * len(legs)
        # scenario returns (high-scoring = goals>=4)
        a_hi = a["actual_goals"] >= 4
        b_hi = b["actual_goals"] >= 4
        # primary wins only if both top5 — approximate payout as if equalized CS return ~ budget*1.0 when hit
        primary_win = bool(a["in_top5"] and b["in_top5"])
        # synthetic primary return assumption for structure comparison only
        primary_gross = primary_pot * 2.2 if primary_win else 0.0  # SYNTHETIC primary payout factor

        hedge_gross = 0.0
        for sel, odd in legs:
            if odd is None:
                continue
            pays = False
            if sel == "O35_A" and a_hi:
                pays = True
            elif sel == "O35_B" and b_hi:
                pays = True
            elif sel == "O35_AxB" and a_hi and b_hi:
                pays = True
            if pays:
                hedge_gross += stake_each * odd

        # overlap: if high score already in top5 exact on that match
        overlap_a = a_hi and a["in_top5"]
        overlap_b = b_hi and b["in_top5"]

        # three-goal gaps (never covered by O3.5 alone)
        a_gap = a["actual_score"] in THREE_GOAL_OVER35_GAPS
        b_gap = b["actual_score"] in THREE_GOAL_OVER35_GAPS

        net = primary_gross + hedge_gross - total
        structures.append(
            {
                "structure": name,
                "odds_a_over35": oa,
                "odds_b_over35": ob,
                "combo_over35_odds": (oa * ob) if oa and ob else None,
                "legs": ";".join(s for s, _ in legs) if legs else "none",
                "total_stake": total,
                "primary_pot_synthetic": primary_pot,
                "hedge_stake": stake_each * len(legs),
                "primary_win_top5x5": int(primary_win),
                "return_if_only_a_high": (
                    (primary_gross if primary_win else 0.0)
                    + (stake_each * oa if oa and a_hi and any(s == "O35_A" for s, _ in legs) else 0.0)
                    - total
                ),
                "return_if_only_b_high": (
                    (primary_gross if primary_win else 0.0)
                    + (stake_each * ob if ob and b_hi and any(s == "O35_B" for s, _ in legs) else 0.0)
                    - total
                ),
                "return_if_both_high": net if (a_hi and b_hi) else None,
                "realized_net_this_pair": net,
                "overlap_high_already_in_top5_a": int(overlap_a),
                "overlap_high_already_in_top5_b": int(overlap_b),
                "actual_a_three_goal_gap": int(a_gap),
                "actual_b_three_goal_gap": int(b_gap),
                "three_goal_gaps": ",".join(THREE_GOAL_OVER35_GAPS),
                "odds_provenance": "real_closing" if (oa or ob) else "missing",
                "primary_payout_note": "SYNTHETIC primary pot factor 2.2× — not real CS odds",
                "gaps_note": gaps_note,
            }
        )

    gaps = "Over 3.5 does NOT cover 2-1, 1-2, 3-0, 0-3"
    add("PRIMARY_ONLY", [], gaps)
    if oa:
        add("PRIMARY_PLUS_O35_A", [("O35_A", oa)], gaps)
    if ob:
        add("PRIMARY_PLUS_O35_B", [("O35_B", ob)], gaps)
    if oa and ob:
        add("PRIMARY_PLUS_O35_A_AND_B", [("O35_A", oa), ("O35_B", ob)], gaps)
        add(
            "PRIMARY_PLUS_O35_A_B_AND_COMBO",
            [("O35_A", oa), ("O35_B", ob), ("O35_AxB", oa * ob)],
            gaps,
        )
        # higher-tail fixture only
        if float(a["model_p_over35"]) >= float(b["model_p_over35"]):
            add("PRIMARY_PLUS_O35_HIGHER_TAIL", [("O35_A", oa)], gaps)
        else:
            add("PRIMARY_PLUS_O35_HIGHER_TAIL", [("O35_B", ob)], gaps)
    # Over 2.5 / BTTS alternatives
    oa25 = a.get("ou_over_25_closing")
    ob25 = b.get("ou_over_25_closing")
    if oa25:
        add(
            "PRIMARY_PLUS_O25_A",
            [("O35_A", float(oa25))],  # reuse slot naming for stake engine; interpret as O25
            "Over 2.5 covers 2-1/1-2/3-0/0-3 but not 0-0/1-0/0-1/1-1 low scores",
        )
    by = a.get("btts_yes_closing")
    if by:
        add(
            "PRIMARY_PLUS_BTTS_YES_A",
            [("O35_A", float(by))],
            "BTTS Yes does not cover 1-0/2-0/3-0/0-1/0-2/0-0",
        )
    return structures


def stake_strategy_rows(
    tickets: list[dict],
    budget: float,
    min_stake: float,
    regime: str,
) -> list[dict[str, Any]]:
    # attach synthetic odds
    odds = []
    probs = []
    for t in tickets:
        p = float(t["joint_p_independence"])
        probs.append(p)
        odds.append(synthetic_cs_odds_from_prob(p, regime))

    strategies = {
        "EQUAL": equal_stakes(len(tickets), budget, min_stake),
        "EQUAL_GROSS_RETURN": equal_gross_stakes(odds, budget, min_stake),
        "MODEL_PROB_WEIGHTED": model_prob_stakes(probs, budget, min_stake),
        "POSITIVE_EDGE": positive_edge_stakes(probs, odds, budget, min_stake, 0.05),
    }
    mm_stakes, mm_worst = minimax_equalize_covered(odds, budget, min_stake)
    strategies["MINIMAX_LOSS"] = mm_stakes

    rows = []
    for name, stakes in strategies.items():
        total = sum(stakes)
        # expected net under independence
        exp_gross = sum(s * o * p for s, o, p in zip(stakes, odds, probs))
        # but each ticket mutual exclusive within exact covered set — correct EV:
        # E[return] = sum_i P(i) * (stake_i * odds_i) - total, with P approximating joint
        exp_net = sum(p * (s * o) for s, o, p in zip(stakes, odds, probs)) - total
        # worst covered
        covered_nets = [s * o - total for s, o in zip(stakes, odds) if s > 0]
        worst_covered = min(covered_nets) if covered_nets else -total
        full_loss = -total
        arb = classify_arbitrage(odds)
        rows.append(
            {
                "strategy": name,
                "odds_regime": regime,
                "odds_kind": "SYNTHETIC_SENSITIVITY",
                "budget": budget,
                "min_stake": min_stake,
                "total_stake": total,
                "expected_net_independence": exp_net,
                "min_covered_scenario_net": worst_covered if name != "MINIMAX_LOSS" else mm_worst,
                "worst_case_uncovered_net": full_loss,
                "n_tickets_funded": sum(1 for s in stakes if s > 0),
                "inverse_sum_25": arb["inverse_sum"],
                "arbitrage_class": arb["classification"],
                "outcome_space_complete": False,
                "independence_note": INDEPENDENCE_NOTE,
            }
        )
    # Tiered: weight primary top (i<=2,j<=2) heavier
    tier_w = []
    for t in tickets:
        ra, rb = t["rank_a"], t["rank_b"]
        if ra <= 2 and rb <= 2:
            tier_w.append(3.0 * t["joint_p_independence"])
        elif ra <= 3 and rb <= 3:
            tier_w.append(2.0 * t["joint_p_independence"])
        else:
            tier_w.append(1.0 * t["joint_p_independence"])
    tier_stakes = model_prob_stakes(tier_w, budget, min_stake)
    total = sum(tier_stakes)
    exp_net = sum(p * (s * o) for s, o, p in zip(tier_stakes, odds, probs)) - total
    covered_nets = [s * o - total for s, o in zip(tier_stakes, odds) if s > 0]
    rows.append(
        {
            "strategy": "TIERED_PROFIT_RECOVERY",
            "odds_regime": regime,
            "odds_kind": "SYNTHETIC_SENSITIVITY",
            "budget": budget,
            "min_stake": min_stake,
            "total_stake": total,
            "expected_net_independence": exp_net,
            "min_covered_scenario_net": min(covered_nets) if covered_nets else -total,
            "worst_case_uncovered_net": -total,
            "n_tickets_funded": sum(1 for s in tier_stakes if s > 0),
            "inverse_sum_25": classify_arbitrage(odds)["inverse_sum"],
            "arbitrage_class": "INCOMPLETE_COVERAGE",
            "outcome_space_complete": False,
            "independence_note": INDEPENDENCE_NOTE,
        }
    )
    return rows


def walk_forward(enriched: list[dict], rng: random.Random) -> tuple[list[dict], list[dict]]:
    by_day: dict[str, list] = defaultdict(list)
    for r in enriched:
        by_day[r["day"]].append(r)

    strategies = [
        "random_eligible",
        "highest_top5_mass",
        "lowest_entropy",
        "strongest_suitability",
        "highest_expected_joint",
        "domain_diverse",
        "same_league",
        "cross_league",
    ]
    results = []
    drawdown_rows = []

    # sample days for speed: all untouched days + every 3rd earlier day
    days = sorted(by_day.keys())
    for strategy in strategies:
        equity = 0.0
        peak = 0.0
        max_dd = 0.0
        streak_loss = 0
        max_streak = 0
        stats = defaultdict(float)
        n = 0
        for day in days:
            if day < "2024-01-01":
                continue
            # thin early days
            if day < UNTOUCHED and hash(day + strategy) % 3 != 0:
                continue
            pair = select_pair(by_day[day], strategy, rng)
            if not pair:
                continue
            a, b = pair
            if not pair_eligible(a, b):
                continue
            ha = [c["selection"] for c in select_hedge_candidates(a, max_extra=5)]
            hb = [c["selection"] for c in select_hedge_candidates(b, max_extra=5)]
            hit = evaluate_pair_hit(a, b, ha, hb)
            n += 1
            stats["primary_hits"] += hit["primary_hit"]
            stats["hedge_hits"] += hit["hedge_hit"]
            stats["sum_joint_canon"] += hit["joint_canon_model"]
            stats["sum_joint_union"] += hit["joint_union_model"]
            # coverage-only PnL proxy: +1 hit primary, +0.5 hedge-only, -1 miss (NOT money)
            if hit["primary_hit"]:
                pnl = 1.0
                streak_loss = 0
            elif hit["hedge_hit"]:
                pnl = 0.25
                streak_loss = 0
            else:
                pnl = -1.0
                streak_loss += 1
                max_streak = max(max_streak, streak_loss)
            equity += pnl
            peak = max(peak, equity)
            max_dd = max(max_dd, peak - equity)
            stats["full_loss"] += int(not hit["hedge_hit"])
            stats["stake_recovery_proxy"] += int(hit["hedge_hit"] and not hit["primary_hit"])

        results.append(
            {
                "selection_strategy": strategy,
                "n_portfolios": n,
                "primary_25_hit_rate": (stats["primary_hits"] / n) if n else None,
                "hedge_enhanced_hit_rate": (stats["hedge_hits"] / n) if n else None,
                "avg_model_joint_canon": (stats["sum_joint_canon"] / n) if n else None,
                "avg_model_joint_union": (stats["sum_joint_union"] / n) if n else None,
                "full_loss_rate": (stats["full_loss"] / n) if n else None,
                "stake_recovery_proxy_rate": (stats["stake_recovery_proxy"] / n) if n else None,
                "max_drawdown_coverage_units": max_dd,
                "max_losing_streak": max_streak,
                "profitability_roi": None,
                "profitability_note": "UNAVAILABLE — no historical exact-score odds",
                "chronological": True,
                "postmatch_leakage": False,
            }
        )
        drawdown_rows.append(
            {
                "selection_strategy": strategy,
                "max_drawdown_coverage_units": max_dd,
                "max_losing_streak": max_streak,
                "n_portfolios": n,
                "metric_kind": "coverage_unit_proxy_not_currency",
            }
        )
    return results, drawdown_rows


def coverage_cost_curve(enriched_sample: list[dict]) -> list[dict]:
    rows = []
    for cap in [0, 5, 10, 15, 25]:
        gains = []
        costs = []  # synthetic: unit cost per hedge ticket
        for r in enriched_sample:
            base = set(r["top5_scores"])
            hedges = [c["selection"] for c in select_hedge_candidates(r, max_extra=cap)]
            union = base | set(hedges)
            mass_base = r["top5_mass"]
            mass_u = sum(r["prob_map"].get(s, 0.0) for s in union)
            gains.append(mass_u - mass_base)
            costs.append(float(cap))  # ticket count budget as cost proxy
        rows.append(
            {
                "max_extra_hedge_tickets": cap,
                "n_fixtures": len(enriched_sample),
                "avg_coverage_gain": sum(gains) / len(gains) if gains else 0,
                "avg_ticket_budget_cost_proxy": sum(costs) / len(costs) if costs else 0,
                "gain_per_ticket": (
                    (sum(gains) / len(gains) / cap) if cap and gains else None
                ),
                "note": "per-fixture coverage; joint ≈ product under independence",
            }
        )
    return rows


def write_reports(summary: dict[str, Any]) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    status = summary["final_status"]
    q = summary["answers"]
    inv = summary["odds_inventory"]
    wf = summary["walk_forward_best"]

    en = f"""# TWO-FIXTURE EXACT-SCORE PORTFOLIO RESEARCH

**Mode:** Research / shadow only — no production deployment, no automatic betting, no ECSE/freeze changes.

**Final status:** `{status}`

**Generated:** {summary["generated_at"]}

## Prior research locked

- Canonical Top5 untouched-test ≈ **43.34%**
- Shift Both +1 Top5 ≈ **23.66%** (not a model)
- Canonical ∪ Shifted ≤10 ≈ **53.24%**
- Policy: `ECSE_SCORE_SHIFT_COMPLEMENTARY_ONLY_FOR_TOP10_OR_HEDGE`

Canonical Top5 is **never replaced**. Shifted scores appear only in the hedge candidate pool.

## Odds inventory

| Source | Count / flag |
|---|---|
| Correct-score import rows | {inv.get("correct_score_imports")} |
| Real exact-score odds available | **{inv.get("real_exact_score_odds_available")}** |
| Over 3.5 clean rows | {inv.get("over_35_rows")} |
| BTTS yes clean rows | {inv.get("btts_yes_rows")} |

{inv.get("note")}

## Structural result (25 primary combos)

For eligible fixtures A and B:

```text
5 canonical scores(A) × 5 canonical scores(B) = 25 primary tickets
ComboOdds(i,j) = OddsA(i) × OddsB(j)   # when real odds exist
P(Ai ∧ Bj) ≈ P(Ai)×P(Bj)               # independence approximation
```

{INDEPENDENCE_NOTE}

Exact-score Top5×Top5 is **incomplete** outcome space → inverse-sum on 25 tickets is **not** arbitrage.

## Walk-forward coverage (chronological, prematch features only)

Best selection gate by hedge-enhanced hit rate: **{wf.get("selection_strategy")}**

| Metric | Value |
|---|---|
| Portfolios | {wf.get("n_portfolios")} |
| Primary 25 hit rate | {wf.get("primary_25_hit_rate")} |
| Hedge-enhanced hit rate | {wf.get("hedge_enhanced_hit_rate")} |
| Avg model joint Top5×Top5 | {wf.get("avg_model_joint_canon")} |
| Avg model joint union10×union10 | {wf.get("avg_model_joint_union")} |
| Full-loss rate (vs hedge union) | {wf.get("full_loss_rate")} |
| ROI (currency) | UNAVAILABLE (no historical CS odds) |

## Over 3.5 hedge

Over 3.5 **does not** cover: {", ".join(THREE_GOAL_OVER35_GAPS)}.

Real Over 3.5 closing odds were used for market-hedge structure comparisons when present.
Primary exact-score payouts in those comparisons are **synthetic** and labeled as such.

## Answers (1–20)

1. Viable mathematically as a **coverage structure**? **{q["q1"]}**
2. Historical primary 25-combo hit rate? **{q["q2"]}**
3. Approx joint Top5 coverage (model)? **{q["q3"]}**
4. Shifted/hedge pool coverage gain? **{q["q4"]}**
5. Optimal hedge ticket count (marginal)? **{q["q5"]}**
6. Best hedge type per unit? **{q["q6"]}**
7. Over 3.5 useful recovery? **{q["q7"]}**
8. Uncovered three-goal scenarios? **{q["q8"]}**
9. Can hedge recover full stake? **{q["q9"]}**
10. Under what odds/stake conditions? **{q["q10"]}**
11. Worst-case loss? **{q["q11"]}**
12. Full-loss probability estimate? **{q["q12"]}**
13. Equal staking vs optimized? **{q["q13"]}**
14. Minimax reduce drawdown? **{q["q14"]}**
15. Exact-score odds after margin? **{q["q15"]}**
16. Historical CS odds for ROI? **{q["q16"]}**
17. Best fixture-selection gate? **{q["q17"]}**
18. Daily pipeline owner-only? **{q["q18"]}**
19. Production deployment justified? **{q["q19"]}**
20. Exact next step? **{q["q20"]}**

## Daily pipeline (design only — not deployed)

Command concept: `دو بازی مناسب امروز برای پکیج ۲۵تایی و پوشش‌ها را نشان بده`

1. Use already frozen daily predictions  
2. Select two highest-quality exact-score fixtures  
3. Fetch **current legitimate** exact-score odds  
4. Build 25 primary tickets + limited hedges  
5. Optimize stakes / show worst-case  
6. Manual owner approval only  
7. Never auto-place bets  
8. Keep separate from public SaaS predictions  

## Constraints respected

- No production model change  
- No freeze edits  
- No automatic betting  
- No fabricated historical CS odds  
- Synthetic sensitivity clearly separated  
- Shadow research only  

## Artifacts

See `artifacts/two_fixture_portfolio/`.

## Final status

`{status}`

STOP.
"""
    (REPORTS / "TWO_FIXTURE_EXACT_SCORE_PORTFOLIO_RESEARCH.md").write_text(en, encoding="utf-8")

    fa = f"""# پژوهش پورتفوی دو بازی — اسکور دقیق (۲۵ ترکیب اصلی + پوشش)

**حالت:** فقط تحقیق و سایه — بدون استقرار تولید، بدون شرط‌بندی خودکار، بدون تغییر ECSE/فریز.

**وضعیت نهایی:** `{status}`

**زمان تولید:** {summary["generated_at"]}

## نتیجه پژوهش قبلی (قفل‌شده)

- Canonical Top5 ≈ **۴۳٫۳۴٪**
- Shift Both +1 به‌عنوان مدل جایگزین **رد** شد (≈۲۳٫۶۶٪)
- اتحاد Canonical ∪ Shifted تا ۱۰ ≈ **۵۳٫۲۴٪**
- سیاست: شیفت فقط به‌عنوان نامزد پوشش مکمل

Canonical Top5 **هرگز جایگزین نمی‌شود**.

## موجودی ضرایب

- ضرایب تاریخی اسکور دقیق در CSV: **یافت نشد** (`real_exact_score_odds_available={inv.get("real_exact_score_odds_available")}`)
- Over 3.5 واقعی (در صورت وجود closing): موجود در دیتاست آموزشی
- سودآوری ارزی پکیج ۲۵تایی **قابل اثبات نیست** تا ضرایب واقعی اسکور دقیق گردآوری شوند

## ساختار

```text
۵ اسکور کنونیکال بازی A × ۵ اسکور کنونیکال بازی B = ۲۵ بلیت اصلی
```

احتمال مشترک با فرض استقلال تقریب زده می‌شود و وابستگی مسابقات هم‌روز ممکن است اثر بگذارد.

فضای تمام اسکورها با Top5 کامل نیست → ادعای آربیتراژ برای ۲۵ بلیت **ممنوع**.

## پوشش Walk-Forward

بهترین دروازه انتخاب: **{wf.get("selection_strategy")}**

- نرخ برخورد ۲۵تایی: **{q["q2"]}**
- پوشش مشترک مدل Top5×Top5: **{q["q3"]}**
- بهبود پوشش با پوشش‌ها: **{q["q4"]}**
- ROI تاریخی با ضرایب واقعی اسکور دقیق: **در دسترس نیست**

## Over 3.5

پوشش نمی‌کند: {", ".join(THREE_GOAL_OVER35_GAPS)}.

## پاسخ به ۲۰ سؤال

1. {q["q1"]}
2. {q["q2"]}
3. {q["q3"]}
4. {q["q4"]}
5. {q["q5"]}
6. {q["q6"]}
7. {q["q7"]}
8. {q["q8"]}
9. {q["q9"]}
10. {q["q10"]}
11. {q["q11"]}
12. {q["q12"]}
13. {q["q13"]}
14. {q["q14"]}
15. {q["q15"]}
16. {q["q16"]}
17. {q["q17"]}
18. {q["q18"]}
19. {q["q19"]}
20. {q["q20"]}

## یکپارچه‌سازی روزانه (فقط طراحی)

جدا از پیش‌بینی عمومی SaaS؛ فقط گزارش مالک؛ تأیید دستی؛ بدون شرط خودکار.

## وضعیت نهایی

`{status}`

توقف.
"""
    (REPORTS / "TWO_FIXTURE_EXACT_SCORE_PORTFOLIO_RESEARCH_FA.md").write_text(fa, encoding="utf-8")


def main() -> int:
    ART.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    rng = random.Random(42)
    settings = get_settings()
    conn = connect(settings.sqlite_path)

    print("Inventory odds...", flush=True)
    odds_inv = inventory_odds(conn)
    (ART / "odds_inventory.json").write_text(json.dumps(odds_inv, indent=2), encoding="utf-8")

    print("Loading historical...", flush=True)
    hist = load_historical(conn)
    odds_inv["training_rows"] = len(hist)
    odds_inv["training_ou35_closing_nonnull"] = sum(
        1 for r in hist if r.get("ou_over_35_closing") is not None
    )
    (ART / "odds_inventory.json").write_text(json.dumps(odds_inv, indent=2), encoding="utf-8")
    print(f"Loaded {len(hist)} fixtures", flush=True)

    # Enrich — sample stride for speed on train; full untouched for WF metrics quality
    print("Enriching fixtures (stride)...", flush=True)
    enriched: list[dict] = []
    for i, row in enumerate(hist):
        day = str(row["kickoff_utc"])[:10]
        # denser on untouched test
        if day >= UNTOUCHED:
            if i % 2 != 0:
                continue
        else:
            if i % 8 != 0:
                continue
        e = enrich(row)
        if e:
            enriched.append(e)
    print(f"Enriched {len(enriched)}", flush=True)

    untouched = [e for e in enriched if e["day"] >= UNTOUCHED]
    eligible = [e for e in untouched if e["suitability"] in {"PORTFOLIO_ELIGIBLE", "HEDGE_ONLY"}]

    # Pair selection sample table
    pair_rows = []
    # pick demo pair: two highest top5 mass eligible on a shared day if possible
    by_day = defaultdict(list)
    for e in eligible:
        by_day[e["day"]].append(e)
    demo = None
    for day in sorted(by_day.keys(), reverse=True):
        demo = select_pair(by_day[day], "highest_top5_mass", rng)
        if demo:
            break
    if not demo and len(eligible) >= 2:
        demo = (eligible[0], eligible[1])

    if demo:
        a, b = demo
        pair_rows.append(
            {
                "fixture_a": a["fixture_id"],
                "fixture_b": b["fixture_id"],
                "match_a": f"{a.get('home_team')} vs {a.get('away_team')}",
                "match_b": f"{b.get('home_team')} vs {b.get('away_team')}",
                "league_a": a.get("league"),
                "league_b": b.get("league"),
                "kickoff_a": a.get("kickoff_utc"),
                "kickoff_b": b.get("kickoff_utc"),
                "suitability_a": a["suitability"],
                "suitability_b": b["suitability"],
                "top5_mass_a": a["top5_mass"],
                "top5_mass_b": b["top5_mass"],
                "entropy_a": a["entropy"],
                "entropy_b": b["entropy"],
                "data_quality_a": a.get("data_quality_score"),
                "data_quality_b": b.get("data_quality_score"),
                "joint_canon_model": joint_coverage(a, b, "canonical"),
                "joint_union_model": joint_coverage(a, b, "union10"),
                "decision": (
                    "PORTFOLIO_ELIGIBLE"
                    if a["suitability"] == "PORTFOLIO_ELIGIBLE"
                    and b["suitability"] == "PORTFOLIO_ELIGIBLE"
                    else "HEDGE_ONLY"
                ),
                "main_forensic_risk": "independence_approx_and_missing_cs_odds",
                "selection_gate": "highest_top5_mass",
            }
        )
    write_csv(ART / "fixture_pair_selection.csv", pair_rows)

    # Primary 25 + hedges + coverage for demo
    primary_rows: list[dict] = []
    hedge_rows: list[dict] = []
    scenario_rows: list[dict] = []
    stake_rows: list[dict] = []
    over35_rows: list[dict] = []
    template: dict[str, Any] = {}

    if demo:
        a, b = demo
        tickets = build_primary_matrix(a["top5"], b["top5"], odds_a=None, odds_b=None)
        # synthetic odds for stake/template
        for t in tickets:
            p = float(t["joint_p_independence"])
            o = synthetic_cs_odds_from_prob(p, "medium")
            t["combo_odds_synthetic_medium"] = o
            t["odds_kind"] = "SYNTHETIC_SENSITIVITY"
            t["odds_a_real"] = None
            t["odds_b_real"] = None
            t["combo_odds_real"] = None
        stakes = equal_gross_stakes(
            [t["combo_odds_synthetic_medium"] for t in tickets],
            DEFAULT_BUDGET,
            DEFAULT_MIN_STAKE,
        )
        total_stake = sum(stakes)
        for t, s in zip(tickets, stakes):
            gross = s * t["combo_odds_synthetic_medium"]
            primary_rows.append(
                {
                    **{k: t[k] for k in t},
                    "stake": s,
                    "gross_return_if_win": gross,
                    "net_portfolio_if_win": gross - total_stake,
                    "total_portfolio_stake": total_stake,
                    "canonical_preserved": True,
                }
            )

        for side, fx in (("A", a), ("B", b)):
            hedges = select_hedge_candidates(fx, max_extra=10)
            for h in hedges:
                p = float(h["probability"])
                syn = synthetic_cs_odds_from_prob(max(p, 1e-6), "medium")
                # stake aiming partial recovery: stake = total_stake / syn
                rec_stake = min(DEFAULT_BUDGET * 0.05, total_stake / syn if syn > 0 else 0)
                hedge_rows.append(
                    {
                        "fixture_side": side,
                        "fixture_id": fx["fixture_id"],
                        "selection": h["selection"],
                        "kind": h["kind"],
                        "model_probability": p,
                        "odds_synthetic_medium": syn,
                        "odds_real": None,
                        "odds_kind": "SYNTHETIC_SENSITIVITY",
                        "stake_recovery_attempt": rec_stake,
                        "gross_if_win": rec_stake * syn,
                        "recovers_full_portfolio_stake": bool(rec_stake * syn >= total_stake - 1e-9),
                        "failure_scenario": h["failure_scenario"],
                        "reason_selected": h["reason"],
                        "replaces_top5": False,
                        "canonical_preserved": True,
                        "overlap_with_top5": h["selection"] in fx["top5_scores"],
                    }
                )

        # scenario coverage matrices (per fixture + paired flag)
        for side, fx in (("A", a), ("B", b)):
            top5 = fx["top5_scores"]
            shifted = fx["shifted_complementary"]
            top6_10 = [s for s in fx["top10_scores"] if s not in top5]
            for row in scenario_coverage_for_fixture(top5, shifted, top6_10):
                scenario_rows.append({"fixture_side": side, "fixture_id": fx["fixture_id"], **row})
        # paired coverage for exact grid
        for ha in range(0, 6):
            for aa in range(0, 6):
                for hb in range(0, 6):
                    for ab in range(0, 6):
                        sa, sb = fmt(ha, aa), fmt(hb, ab)
                        # only write condensed: when either is cover-relevant sample — too big 6^4=1296 ok
                        covered_primary = sa in a["top5_scores"] and sb in b["top5_scores"]
                        covered_hedge = (
                            sa in (set(a["top5_scores"]) | set(a["shifted_complementary"]) | set(a["top10_scores"]))
                            and sb in (set(b["top5_scores"]) | set(b["shifted_complementary"]) | set(b["top10_scores"]))
                        )
                        if covered_primary or covered_hedge or (ha + aa + hb + ab) % 7 == 0:
                            scenario_rows.append(
                                {
                                    "fixture_side": "PAIR",
                                    "fixture_id": f"{a['fixture_id']}x{b['fixture_id']}",
                                    "scenario": f"{sa}|{sb}",
                                    "bucket": "paired_exact",
                                    "canonical_top5": covered_primary,
                                    "shifted_hedge": (
                                        sa in a["shifted_complementary"] or sb in b["shifted_complementary"]
                                    ),
                                    "top6_10_hedge": (
                                        sa in a["top10_scores"] or sb in b["top10_scores"]
                                    ),
                                    "over_25": (ha + aa >= 3) or (hb + ab >= 3),
                                    "over_35": (ha + aa >= 4) or (hb + ab >= 4),
                                    "btts_yes": (ha >= 1 and aa >= 1) or (hb >= 1 and ab >= 1),
                                    "three_goal_over35_gap": sa in THREE_GOAL_OVER35_GAPS
                                    or sb in THREE_GOAL_OVER35_GAPS,
                                    "paired_covered_primary": covered_primary,
                                    "paired_covered_hedge_union": covered_hedge,
                                }
                            )

        for budget in BUDGETS:
            for ms in MIN_STAKES:
                for regime in SYNTHETIC_REGIMES:
                    stake_rows.extend(stake_strategy_rows(tickets, budget, ms, regime))

        over35_rows = over35_structure_analysis(a, b, DEFAULT_BUDGET)

        arb = classify_arbitrage(
            [synthetic_cs_odds_from_prob(t["joint_p_independence"], "medium") for t in tickets]
        )
        template = {
            "mode": "shadow_research_template",
            "deploy": False,
            "auto_bet": False,
            "canonical_top5_preserved": True,
            "shifted_as_hedge_only": True,
            "independence_approximation": True,
            "independence_note": INDEPENDENCE_NOTE,
            "fixture_a": {
                "fixture_id": a["fixture_id"],
                "match": f"{a.get('home_team')} vs {a.get('away_team')}",
                "league": a.get("league"),
                "kickoff": a.get("kickoff_utc"),
                "suitability": a["suitability"],
                "top5": a["top5"],
                "top5_mass": a["top5_mass"],
                "entropy": a["entropy"],
            },
            "fixture_b": {
                "fixture_id": b["fixture_id"],
                "match": f"{b.get('home_team')} vs {b.get('away_team')}",
                "league": b.get("league"),
                "kickoff": b.get("kickoff_utc"),
                "suitability": b["suitability"],
                "top5": b["top5"],
                "top5_mass": b["top5_mass"],
                "entropy": b["entropy"],
            },
            "primary_tickets_n": 25,
            "primary_tickets": primary_rows,
            "hedge_tickets": hedge_rows,
            "portfolio_metrics": {
                "total_stake": total_stake,
                "canonical_joint_coverage_model": joint_coverage(a, b, "canonical"),
                "hedge_union_joint_coverage_model": joint_coverage(a, b, "union10"),
                "worst_case_loss_if_uncovered": -total_stake,
                "full_loss_probability_est": 1.0 - joint_coverage(a, b, "union10"),
                "arbitrage_on_primary_25": arb,
                "real_cs_odds": False,
                "recommendation": recommendation_label(
                    joint_canon=joint_coverage(a, b, "canonical"),
                    joint_hedge=joint_coverage(a, b, "union10"),
                    worst_case_net=-total_stake,
                    hedge_cost_share=0.2,
                    has_real_cs_odds=False,
                    synthetic_ev=None,
                ),
            },
            "three_goal_over35_gaps": list(THREE_GOAL_OVER35_GAPS),
            "allowed_recommendations": [
                "PORTFOLIO_QUALIFIED",
                "PORTFOLIO_PARTIAL_RECOVERY",
                "PRIMARY_ONLY",
                "HEDGE_TOO_EXPENSIVE",
                "ODDS_UNFAVORABLE",
                "COVERAGE_TOO_LOW",
                "NO_PORTFOLIO",
            ],
        }

    write_csv(ART / "primary_25_combo_matrix.csv", primary_rows)
    write_csv(ART / "hedge_candidate_pool.csv", hedge_rows)
    write_csv(ART / "scenario_coverage_matrix.csv", scenario_rows)
    write_csv(ART / "stake_strategy_comparison.csv", stake_rows)
    write_csv(ART / "over35_hedge_analysis.csv", over35_rows)
    (ART / "recommended_portfolio_template.json").write_text(
        json.dumps(template, indent=2, default=str), encoding="utf-8"
    )

    print("Walk-forward simulation...", flush=True)
    wf_rows, dd_rows = walk_forward(enriched, rng)
    write_csv(ART / "walk_forward_portfolio_results.csv", wf_rows)
    write_csv(ART / "drawdown_analysis.csv", dd_rows)

    sample = untouched[:: max(1, len(untouched) // 2000)][:2000]
    curve = coverage_cost_curve(sample if sample else enriched[:500])
    write_csv(ART / "coverage_cost_curve.csv", curve)

    # Hedge type efficiency on sample
    type_gain: dict[str, list[float]] = defaultdict(list)
    for r in sample[:800]:
        base = set(r["top5_scores"])
        for h in select_hedge_candidates(r, max_extra=15):
            if h["selection"] in base:
                continue
            type_gain[h["kind"]].append(float(h["probability"]))
    hedge_type_eff = [
        {
            "hedge_kind": k,
            "avg_added_prob_mass": sum(v) / len(v) if v else 0,
            "n": len(v),
            "note": "marginal model mass of candidate (not euro ROI)",
        }
        for k, v in sorted(type_gain.items(), key=lambda kv: -sum(kv[1]) / max(1, len(kv[1])))
    ]
    write_csv(ART / "hedge_type_efficiency.csv", hedge_type_eff)

    # Aggregate walk-forward answers
    best_wf = max(wf_rows, key=lambda r: (r.get("hedge_enhanced_hit_rate") or 0)) if wf_rows else {}
    avg_primary = (
        sum(r["primary_25_hit_rate"] for r in wf_rows if r.get("primary_25_hit_rate") is not None) / len(wf_rows)
        if wf_rows
        else None
    )
    # stake comparison: equal vs minimax on synthetic for demo tickets
    equal_vs_mm = "unavailable"
    if stake_rows:
        eq = [r for r in stake_rows if r["strategy"] == "EQUAL" and r["budget"] == 50 and r["min_stake"] == 0.5 and r["odds_regime"] == "medium"]
        mm = [r for r in stake_rows if r["strategy"] == "MINIMAX_LOSS" and r["budget"] == 50 and r["min_stake"] == 0.5 and r["odds_regime"] == "medium"]
        if eq and mm:
            equal_vs_mm = (
                f"EQUAL expected_net={eq[0]['expected_net_independence']:.3f} "
                f"min_covered={eq[0]['min_covered_scenario_net']:.3f}; "
                f"MINIMAX expected_net={mm[0]['expected_net_independence']:.3f} "
                f"min_covered={mm[0]['min_covered_scenario_net']:.3f} "
                f"(SYNTHETIC only)"
            )

    best_hedge_type = hedge_type_eff[0]["hedge_kind"] if hedge_type_eff else "n/a"
    opt_cap = max(curve, key=lambda r: (r.get("gain_per_ticket") or 0) if r["max_extra_hedge_tickets"] else -1)

    # Over35 usefulness from demo rows
    o35_useful = "inconclusive_without_cs_odds"
    if over35_rows:
        with_h = [r for r in over35_rows if r["structure"] != "PRIMARY_ONLY" and r.get("odds_provenance") == "real_closing"]
        if with_h:
            o35_useful = (
                "Partial market recovery only when goals≥4; leaves three-goal gaps; "
                "cannot certify full stake recovery without real CS primary odds"
            )

    joint_model = pair_rows[0]["joint_canon_model"] if pair_rows else None
    joint_union = pair_rows[0]["joint_union_model"] if pair_rows else None
    cov_gain = (joint_union - joint_model) if joint_union is not None and joint_model is not None else None

    final_status = "TWO_FIXTURE_PORTFOLIO_REAL_ODDS_DATA_REQUIRED"
    if odds_inv.get("real_exact_score_odds_available"):
        # would require ROI proof; not present
        final_status = "TWO_FIXTURE_PORTFOLIO_COVERAGE_IMPROVED_NO_PROFIT_EDGE"

    answers = {
        "q1": "Yes as a coverage/upside structure; not proven as a profitable betting system",
        "q2": f"{best_wf.get('primary_25_hit_rate')} (best gate); mean across gates ≈ {avg_primary}",
        "q3": f"{joint_model} on demo pair; walk-forward avg {best_wf.get('avg_model_joint_canon')}",
        "q4": f"demo Δjoint={cov_gain}; walk-forward union avg {best_wf.get('avg_model_joint_union')}",
        "q5": f"~{opt_cap.get('max_extra_hedge_tickets')} extra tickets by gain/ticket on curve (research)",
        "q6": best_hedge_type,
        "q7": o35_useful,
        "q8": ", ".join(THREE_GOAL_OVER35_GAPS),
        "q9": "Only if hedge odds × stake ≥ total portfolio stake; not guaranteed; not proven with real CS odds",
        "q10": "Requires stake_h ≥ TotalStake / Odds_h and non-overlapping win conditions; bookmaker min stake may block",
        "q11": f"Full stake loss on uncovered outcomes (demo −€{DEFAULT_BUDGET} if budget={DEFAULT_BUDGET})",
        "q12": f"≈ 1 − joint_union_model (demo {1.0 - joint_union if joint_union is not None else 'n/a'}); WF full-loss {best_wf.get('full_loss_rate')}",
        "q13": equal_vs_mm,
        "q14": "Minimax equalizes covered-scenario return (synthetic); does not eliminate uncovered full-loss drawdown",
        "q15": "Unknown historically — no CS odds; synthetic medium margin implies negative EV on average",
        "q16": "NO — trustworthy currency ROI test blocked",
        "q17": best_wf.get("selection_strategy"),
        "q18": "Yes — owner-only shadow report after real CS odds wired; never public auto-bet",
        "q19": "NO",
        "q20": "Ingest legitimate prematch exact-score odds (bookmaker+timestamp+settlement) then rerun stake/ROI validation",
    }

    summary = {
        "generated_at": utc_now(),
        "final_status": final_status,
        "promote": False,
        "deploy": False,
        "auto_bet": False,
        "canonical_unchanged": True,
        "shifted_as_hedge_only": True,
        "odds_inventory": odds_inv,
        "n_enriched": len(enriched),
        "n_untouched_enriched": len(untouched),
        "walk_forward_best": best_wf,
        "answers": answers,
        "validation_hints": {
            "primary_ticket_count": 25,
            "three_goal_gaps": list(THREE_GOAL_OVER35_GAPS),
            "outcome_space_complete_for_top5": False,
            "independence_disclosed": True,
        },
    }
    (ART / "research_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    write_reports(summary)
    print(json.dumps({"final_status": final_status, "n_enriched": len(enriched), "best_gate": best_wf.get("selection_strategy")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
