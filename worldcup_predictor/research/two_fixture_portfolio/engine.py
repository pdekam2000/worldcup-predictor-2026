"""Core math for two-fixture exact-score portfolio research (no production betting)."""
from __future__ import annotations

import math
from typing import Any

from worldcup_predictor.research.ecse_score_distribution import generate_score_distribution

FINAL_STATUSES = {
    "TWO_FIXTURE_PORTFOLIO_HISTORICAL_EDGE_PROVEN",
    "TWO_FIXTURE_PORTFOLIO_PARTIAL_RECOVERY_PROVEN",
    "TWO_FIXTURE_PORTFOLIO_COVERAGE_IMPROVED_NO_PROFIT_EDGE",
    "TWO_FIXTURE_PORTFOLIO_REAL_ODDS_DATA_REQUIRED",
    "TWO_FIXTURE_PORTFOLIO_NOT_VIABLE",
    "TWO_FIXTURE_PORTFOLIO_VALIDATION_FAILED",
}

THREE_GOAL_OVER35_GAPS = ("2-1", "1-2", "3-0", "0-3")
INDEPENDENCE_NOTE = (
    "Joint probability uses independence approximation P(A)·P(B); "
    "same-day / same-league dependence may inflate or reduce realized joint coverage."
)


def parse_score(s: str) -> tuple[int, int] | None:
    try:
        a, b = str(s).strip().replace("–", "-").split("-")
        return int(a), int(b)
    except Exception:
        return None


def fmt(h: int, a: int) -> str:
    return f"{h}-{a}"


def entropy(probs: list[float]) -> float:
    s = 0.0
    for p in probs:
        if p > 0:
            s -= p * math.log(p)
    return s


def ranked_scores(lh: float, la: float, n: int = 15) -> list[dict[str, Any]]:
    dist = generate_score_distribution(float(lh), float(la))
    ranked = [e for e in dist if e.get("scoreline") != "OTHER"]
    ranked.sort(key=lambda x: -float(x["probability"]))
    out = []
    for e in ranked[:n]:
        out.append(
            {
                "score": str(e["scoreline"]),
                "home_goals": int(e["home_goals"]),
                "away_goals": int(e["away_goals"]),
                "probability": float(e["probability"]),
            }
        )
    return out


def fixture_profile(lh: float, la: float) -> dict[str, Any]:
    ranked = ranked_scores(lh, la, 15)
    top5 = ranked[:5]
    top10 = ranked[:10]
    top5_mass = sum(x["probability"] for x in top5)
    top3_mass = sum(x["probability"] for x in top5[:3])
    top10_mass = sum(x["probability"] for x in top10)
    probs = [x["probability"] for x in ranked]
    shifted = []
    for s in top5:
        sh, sa = s["home_goals"] + 1, s["away_goals"] + 1
        shifted.append(fmt(sh, sa))
    # unique complementary shifted (not already in top5)
    top5_set = {x["score"] for x in top5}
    shifted_unique = []
    for sc in shifted:
        if sc not in top5_set and sc not in shifted_unique:
            shifted_unique.append(sc)
    # probability of shifted scores from full ranked or regenerate lookup
    prob_map = {x["score"]: x["probability"] for x in ranked_scores(lh, la, 64)}
    shifted_mass = sum(prob_map.get(sc, 0.0) for sc in shifted_unique)
    union_scores = list(top5_set)
    for sc in shifted_unique:
        if sc not in union_scores:
            union_scores.append(sc)
    union_mass = sum(prob_map.get(sc, 0.0) for sc in union_scores[:10])
    # expand top10 union
    union10 = list(dict.fromkeys([x["score"] for x in top10] + shifted_unique))[:10]
    union10_mass = sum(prob_map.get(sc, 0.0) for sc in union10)

    # market-from-model
    p_over25 = p_over35 = p_btts = p_home = p_draw = p_away = 0.0
    for h in range(0, 8):
        for a in range(0, 8):
            p = prob_map.get(fmt(h, a), 0.0)
            tot = h + a
            if tot >= 3:
                p_over25 += p
            if tot >= 4:
                p_over35 += p
            if h >= 1 and a >= 1:
                p_btts += p
            if h > a:
                p_home += p
            elif h < a:
                p_away += p
            else:
                p_draw += p

    suitability = "PORTFOLIO_ELIGIBLE"
    if top5_mass < 0.28 or entropy(probs[:10]) > 2.85:
        suitability = "EXACT_SCORE_WEAK"
    elif top5_mass < 0.34:
        suitability = "HEDGE_ONLY"
    if top5_mass < 0.22:
        suitability = "NO_PORTFOLIO"

    return {
        "lambda_home": float(lh),
        "lambda_away": float(la),
        "total_lambda": float(lh) + float(la),
        "top5": top5,
        "top10": top10,
        "top5_scores": [x["score"] for x in top5],
        "top10_scores": [x["score"] for x in top10],
        "top3_mass": top3_mass,
        "top5_mass": top5_mass,
        "top10_mass": top10_mass,
        "entropy": entropy(probs[:15]),
        "shifted_complementary": shifted_unique,
        "shifted_mass": shifted_mass,
        "canonical_union_shifted_mass": union10_mass,
        "union_scores_upto10": union10,
        "model_p_home": p_home,
        "model_p_draw": p_draw,
        "model_p_away": p_away,
        "model_p_btts": p_btts,
        "model_p_over25": p_over25,
        "model_p_over35": p_over35,
        "prob_map": prob_map,
        "suitability": suitability,
        "independence_note": INDEPENDENCE_NOTE,
    }


def build_primary_matrix(
    top5_a: list[dict[str, Any]],
    top5_b: list[dict[str, Any]],
    odds_a: dict[str, float] | None = None,
    odds_b: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Build exactly 25 primary combo tickets. Odds optional (None → null fields)."""
    if len(top5_a) != 5 or len(top5_b) != 5:
        raise ValueError("canonical Top5 required for both fixtures (exactly 5)")
    tickets = []
    for i, sa in enumerate(top5_a, 1):
        for j, sb in enumerate(top5_b, 1):
            pa = float(sa["probability"])
            pb = float(sb["probability"])
            joint = pa * pb  # independence approximation
            oa = float(odds_a[sa["score"]]) if odds_a and sa["score"] in odds_a else None
            ob = float(odds_b[sb["score"]]) if odds_b and sb["score"] in odds_b else None
            combo = (oa * ob) if oa is not None and ob is not None else None
            implied = (1.0 / combo) if combo and combo > 0 else None
            ev = (joint * combo - 1.0) if combo is not None else None
            margin_approx = None
            if implied is not None:
                margin_approx = max(0.0, implied - joint)  # rough; not bookmaker overround of full market
            tickets.append(
                {
                    "ticket_id": f"A{i}xB{j}",
                    "rank_a": i,
                    "rank_b": j,
                    "score_a": sa["score"],
                    "score_b": sb["score"],
                    "p_a": pa,
                    "p_b": pb,
                    "joint_p_independence": joint,
                    "odds_a": oa,
                    "odds_b": ob,
                    "combo_odds": combo,
                    "implied_prob": implied,
                    "margin_approx_vs_model": margin_approx,
                    "ev_independence": ev,
                    "odds_source": "real" if combo is not None else "unavailable",
                }
            )
    return tickets


def equal_stakes(n: int, budget: float, min_stake: float) -> list[float]:
    if n <= 0:
        return []
    raw = budget / n
    if raw < min_stake:
        # take as many tickets as budget allows at min_stake
        k = max(1, int(budget // min_stake))
        stakes = [min_stake] * min(k, n) + [0.0] * max(0, n - k)
        return stakes[:n]
    return [raw] * n


def equal_gross_stakes(odds: list[float], budget: float, min_stake: float) -> list[float]:
    """stake_i ∝ 1/O_i so O_i * stake_i is equalized (among positive-odds tickets)."""
    n = len(odds)
    weights = []
    for o in odds:
        if o is None or o <= 0:
            weights.append(0.0)
        else:
            weights.append(1.0 / o)
    wsum = sum(weights)
    if wsum <= 0:
        return equal_stakes(n, budget, min_stake)
    stakes = [budget * (w / wsum) for w in weights]
    # enforce min by zeroing tiny and renormalizing among eligible
    adjusted = []
    for s, w in zip(stakes, weights):
        if w <= 0:
            adjusted.append(0.0)
        else:
            adjusted.append(max(s, min_stake) if s > 0 else 0.0)
    # scale to budget
    total = sum(adjusted)
    if total <= 0:
        return equal_stakes(n, budget, min_stake)
    scale = budget / total
    return [s * scale for s in adjusted]


def model_prob_stakes(probs: list[float], budget: float, min_stake: float) -> list[float]:
    psum = sum(max(0.0, p) for p in probs)
    if psum <= 0:
        return equal_stakes(len(probs), budget, min_stake)
    stakes = [budget * (max(0.0, p) / psum) for p in probs]
    total = sum(stakes)
    return [s * (budget / total) for s in stakes] if total > 0 else equal_stakes(len(probs), budget, min_stake)


def positive_edge_stakes(
    probs: list[float],
    odds: list[float | None],
    budget: float,
    min_stake: float,
    ev_threshold: float = 0.05,
) -> list[float]:
    weights = []
    for p, o in zip(probs, odds):
        if o is None or o <= 0:
            weights.append(0.0)
            continue
        ev = p * o - 1.0
        weights.append(max(0.0, ev) if ev >= ev_threshold else 0.0)
    wsum = sum(weights)
    if wsum <= 0:
        return [0.0] * len(probs)
    return [budget * (w / wsum) for w in weights]


def minimax_equalize_covered(
    odds: list[float | None],
    budget: float,
    min_stake: float,
) -> tuple[list[float], float]:
    """
    Classic equalized-return allocation on available tickets:
    maximizes min gross return among tickets with odds (when one of them wins).
    Worst-case among those covered scenarios = common gross return - budget
    (net). Incomplete coverage → uncovered scenarios still lose full stake.
    """
    stakes = equal_gross_stakes(
        [o if o is not None else 0.0 for o in odds],
        budget,
        min_stake,
    )
    returns = []
    for s, o in zip(stakes, odds):
        if o is not None and o > 0 and s > 0:
            returns.append(s * o)
    min_gross = min(returns) if returns else 0.0
    return stakes, min_gross - budget


def classify_arbitrage(odds: list[float]) -> dict[str, Any]:
    """Classify completeness of an odds cover set via inverse-sum."""
    if not odds:
        return {
            "classification": "INCOMPLETE_COVERAGE",
            "inverse_sum": None,
            "note": "empty odds set",
        }
    inv = sum(1.0 / o for o in odds if o and o > 0)
    if inv < 0.999:
        cls = "TRUE_ARBITRAGE"
    elif inv <= 1.01:
        cls = "BREAK_EVEN_COVER"
    else:
        cls = "PARTIAL_RECOVERY_ONLY"
    return {
        "classification": cls,
        "inverse_sum": inv,
        "note": (
            "Exact-score Top5/Top10 subsets never form a complete outcome space; "
            "do not claim arbitrage for incomplete exact-score covers."
        ),
        "outcome_space_complete": False,
    }


def scenario_coverage_for_fixture(
    top5: list[str],
    shifted: list[str],
    top6_10: list[str],
    *,
    include_over25: bool = True,
    include_over35: bool = True,
    include_btts_yes: bool = True,
) -> list[dict[str, Any]]:
    """Coverage map for scores 0-0..5-5 plus aggregated any-other buckets."""
    rows = []
    for h in range(0, 6):
        for a in range(0, 6):
            sc = fmt(h, a)
            tot = h + a
            rows.append(
                {
                    "scenario": sc,
                    "bucket": "exact_grid",
                    "canonical_top5": sc in top5,
                    "shifted_hedge": sc in shifted,
                    "top6_10_hedge": sc in top6_10,
                    "over_25": include_over25 and tot >= 3,
                    "over_35": include_over35 and tot >= 4,
                    "btts_yes": include_btts_yes and h >= 1 and a >= 1,
                    "three_goal_over35_gap": sc in THREE_GOAL_OVER35_GAPS,
                }
            )
    for bucket, pred in (
        ("Any Other Home Win", lambda h, a: h > a and (h > 5 or a > 5)),
        ("Any Other Draw", lambda h, a: h == a and (h > 5 or a > 5)),
        ("Any Other Away Win", lambda h, a: h < a and (h > 5 or a > 5)),
    ):
        # aggregated row (not enumerating all)
        rows.append(
            {
                "scenario": bucket,
                "bucket": "aggregate_tail",
                "canonical_top5": False,
                "shifted_hedge": False,
                "top6_10_hedge": False,
                "over_25": True,  # most high-score tails are over 2.5; not always over 3.5
                "over_35": True,
                "btts_yes": None,
                "three_goal_over35_gap": False,
            }
        )
    return rows


def synthetic_cs_odds_from_prob(p: float, regime: str = "medium") -> float:
    """
    Clearly labeled synthetic exact-score odds for sensitivity only.
    Applies a bookmaker margin overlay on fair 1/p.
    """
    p = max(p, 1e-6)
    fair = 1.0 / p
    # margin multipliers inflate odds denominator (worsen price)
    mult = {"low": 1.08, "medium": 1.18, "high": 1.30}.get(regime, 1.18)
    return fair / mult  # lower decimal odds = worse for bettor after margin


def portfolio_returns(
    stakes: list[float],
    odds: list[float | None],
    winning_index: int | None,
) -> dict[str, float]:
    total = sum(stakes)
    if winning_index is None or winning_index < 0:
        return {"total_stake": total, "gross": 0.0, "net": -total}
    o = odds[winning_index]
    s = stakes[winning_index]
    if o is None or o <= 0:
        return {"total_stake": total, "gross": 0.0, "net": -total}
    gross = s * o
    return {"total_stake": total, "gross": gross, "net": gross - total}


def select_hedge_candidates(
    profile: dict[str, Any],
    *,
    max_extra: int = 10,
) -> list[dict[str, Any]]:
    """Marginal hedge pool (complementary only — never replaces Top5)."""
    top5 = set(profile["top5_scores"])
    top10 = profile["top10_scores"]
    top6_10 = [s for s in top10 if s not in top5]
    candidates: list[dict[str, Any]] = []
    pm = profile["prob_map"]

    for sc in top6_10:
        candidates.append(
            {
                "selection": sc,
                "kind": "canonical_top6_10",
                "probability": pm.get(sc, 0.0),
                "failure_scenario": sc,
                "reason": "mass near Top5 cutoff",
            }
        )
    for sc in profile["shifted_complementary"]:
        candidates.append(
            {
                "selection": sc,
                "kind": "shift_both_plus1",
                "probability": pm.get(sc, 0.0),
                "failure_scenario": f"high_score_btts_complement:{sc}",
                "reason": "complementary +1/+1 hedge only",
            }
        )
    # draw recovery
    for sc in ("1-1", "2-2", "0-0"):
        if sc not in top5 and profile["model_p_draw"] >= 0.22:
            candidates.append(
                {
                    "selection": sc,
                    "kind": "draw_recovery",
                    "probability": pm.get(sc, 0.0),
                    "failure_scenario": sc,
                    "reason": "draw mass supports recovery",
                }
            )
    # direction recovery
    if profile["model_p_home"] >= 0.45:
        for sc in ("0-1", "1-2", "0-2"):
            if sc not in top5:
                candidates.append(
                    {
                        "selection": sc,
                        "kind": "direction_recovery",
                        "probability": pm.get(sc, 0.0),
                        "failure_scenario": sc,
                        "reason": "home-concentrated → away recovery",
                    }
                )
                break
    elif profile["model_p_away"] >= 0.40:
        for sc in ("1-0", "2-1", "2-0"):
            if sc not in top5:
                candidates.append(
                    {
                        "selection": sc,
                        "kind": "direction_recovery",
                        "probability": pm.get(sc, 0.0),
                        "failure_scenario": sc,
                        "reason": "away-concentrated → home recovery",
                    }
                )
                break
    # high-score tail
    if profile["total_lambda"] >= 2.6:
        for sc in ("3-1", "3-2", "2-2", "4-1", "4-2"):
            if sc not in top5:
                candidates.append(
                    {
                        "selection": sc,
                        "kind": "high_score_tail",
                        "probability": pm.get(sc, 0.0),
                        "failure_scenario": sc,
                        "reason": "elevated total_lambda tail",
                    }
                )

    # dedupe by selection, keep highest prob reason order
    seen = set()
    uniq = []
    for c in sorted(candidates, key=lambda x: -x["probability"]):
        if c["selection"] in seen or c["selection"] in top5:
            continue
        seen.add(c["selection"])
        uniq.append(c)

    # marginal score = probability (coverage) — odds applied later when available
    selected = uniq[:max_extra]
    for i, c in enumerate(selected):
        c["rank"] = i + 1
        c["canonical_preserved"] = True
        c["replaces_top5"] = False
    return selected


def recommendation_label(
    *,
    joint_canon: float,
    joint_hedge: float,
    worst_case_net: float,
    hedge_cost_share: float,
    has_real_cs_odds: bool,
    synthetic_ev: float | None,
) -> str:
    if joint_canon < 0.08:
        return "COVERAGE_TOO_LOW"
    if not has_real_cs_odds:
        return "NO_PORTFOLIO"  # cannot qualify without real CS odds for live use
    if hedge_cost_share > 0.45:
        return "HEDGE_TOO_EXPENSIVE"
    if synthetic_ev is not None and synthetic_ev < -0.15:
        return "ODDS_UNFAVORABLE"
    if worst_case_net >= -1e-9 and joint_hedge >= 0.20:
        return "PORTFOLIO_QUALIFIED"
    if joint_hedge > joint_canon + 0.03:
        return "PORTFOLIO_PARTIAL_RECOVERY"
    return "PRIMARY_ONLY"
