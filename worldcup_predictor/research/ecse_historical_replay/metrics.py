"""Rank forensic, Hit@K, bootstrap CI, segments, reliability gate, reranking."""

from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from dataclasses import asdict
from typing import Any, Sequence

from worldcup_predictor.research.ecse_historical_replay.replay_engine import ReplayRow


def bootstrap_ci(values: list[float], n_boot: int = 1000, alpha: float = 0.05, seed: int = 42) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    n = len(values)
    if n and all(v in (0.0, 1.0, 0, 1) for v in values):
        successes = sum(values)
        p = successes / n
        z = 1.96
        denom = 1.0 + (z * z) / n
        center = (p + (z * z) / (2 * n)) / denom
        margin = z * math.sqrt((p * (1 - p) + (z * z) / (4 * n)) / n) / denom
        return round(max(0.0, center - margin) * 100, 2), round(min(1.0, center + margin) * 100, 2)
    if n > 5000:
        successes = sum(values)
        p = successes / n
        z = 1.96
        denom = 1.0 + (z * z) / n
        center = (p + (z * z) / (2 * n)) / denom
        margin = z * math.sqrt((p * (1 - p) + (z * z) / (4 * n)) / n) / denom
        return round(max(0.0, center - margin) * 100, 2), round(min(1.0, center + margin) * 100, 2)
    rng = random.Random(seed)
    stats = []
    for _ in range(n_boot):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        stats.append(sum(sample) / n)
    stats.sort()
    lo = stats[int((alpha / 2) * n_boot)]
    hi = stats[int((1 - alpha / 2) * n_boot) - 1]
    return round(lo * 100, 2), round(hi * 100, 2)


def rank_metrics(rows: Sequence[ReplayRow], max_rank: int = 10) -> dict[str, Any]:
    n = len(rows)
    if not n:
        return {"n": 0}
    table = []
    total_top10_hits = sum(1 for r in rows if r.top10_hit)
    for rank in range(1, max_rank + 1):
        hits = sum(1 for r in rows if r.actual_rank == rank)
        expected = sum(
            next((x["probability"] for x in r.top10 if x["rank"] == rank), 0.0)
            if rank <= 10
            else 0.0
            for r in rows
        )
        hit_rate = hits / n
        hr_samples = [1.0 if r.actual_rank == rank else 0.0 for r in rows]
        ci_lo, ci_hi = bootstrap_ci(hr_samples)
        table.append(
            {
                "rank": rank,
                "hits": hits,
                "hit_rate_pct": round(hit_rate * 100, 3),
                "ci_95_lo": ci_lo,
                "ci_95_hi": ci_hi,
                "share_of_top10_hits_pct": round(100 * hits / max(total_top10_hits, 1), 2) if rank <= 10 else None,
                "expected_hit_rate_pct": round(100 * expected / n, 3) if rank <= 10 else None,
                "calibration_delta_pp": round(100 * (hit_rate - expected / n), 3) if rank <= 10 else None,
            }
        )
    comparisons = {}
    for a, b in ((1, 2), (1, 3), (1, 4), (1, 5), (2, 3), (2, 4)):
        ha = table[a - 1]["hits"]
        hb = table[b - 1]["hits"]
        comparisons[f"rank{a}_vs_rank{b}"] = {
            "rank_a_hits": ha,
            "rank_b_hits": hb,
            "rank_a_hr_pct": table[a - 1]["hit_rate_pct"],
            "rank_b_hr_pct": table[b - 1]["hit_rate_pct"],
            "rank_b_beats_a": hb > ha,
        }
    return {"n": n, "rank_table": table, "rank_comparisons": comparisons}


def hit_at_k(rows: Sequence[ReplayRow]) -> dict[str, Any]:
    n = len(rows)
    if not n:
        return {"n": 0}
    out = {}
    prev = 0.0
    for k in (1, 2, 3, 4, 5, 10):
        hits = sum(1 for r in rows if r.actual_rank <= k)
        rate = hits / n
        out[f"hit_at_{k}"] = {
            "hits": hits,
            "rate_pct": round(rate * 100, 3),
            "marginal_pp": round(100 * (rate - prev), 3),
            "ci_95": bootstrap_ci([1.0 if r.actual_rank <= k else 0.0 for r in rows]),
        }
        prev = rate
    return {"n": n, **out}


def yearly_stability(rows: Sequence[ReplayRow]) -> dict[str, Any]:
    by_year: dict[str, list[ReplayRow]] = defaultdict(list)
    for r in rows:
        by_year[r.year].append(r)
    out = {}
    for year, subset in sorted(by_year.items()):
        rm = rank_metrics(subset)
        hk = hit_at_k(subset)
        ranks = rm.get("rank_table") or []
        best = max(ranks, key=lambda x: x["hit_rate_pct"]) if ranks else {}
        out[year] = {
            "n": len(subset),
            "best_rank": best.get("rank"),
            "rank1_hr": ranks[0]["hit_rate_pct"] if ranks else None,
            "rank2_hr": ranks[1]["hit_rate_pct"] if len(ranks) > 1 else None,
            "rank3_hr": ranks[2]["hit_rate_pct"] if len(ranks) > 2 else None,
            "rank4_hr": ranks[3]["hit_rate_pct"] if len(ranks) > 3 else None,
            "rank5_hr": ranks[4]["hit_rate_pct"] if len(ranks) > 4 else None,
            "hit_at_1": hk.get("hit_at_1", {}).get("rate_pct"),
            "hit_at_3": hk.get("hit_at_3", {}).get("rate_pct"),
            "hit_at_5": hk.get("hit_at_5", {}).get("rate_pct"),
        }
    return out


def competition_metrics(rows: Sequence[ReplayRow], min_n: int = 200) -> dict[str, Any]:
    by_comp: dict[str, list[ReplayRow]] = defaultdict(list)
    for r in rows:
        by_comp[r.competition].append(r)
    table = []
    for comp, subset in sorted(by_comp.items(), key=lambda x: -len(x[1])):
        n = len(subset)
        entry: dict[str, Any] = {"competition": comp, "n": n, "label": "LOW_SAMPLE" if n < min_n else "OK"}
        if n >= min_n:
            rm = rank_metrics(subset)
            hk = hit_at_k(subset)
            ranks = rm.get("rank_table") or []
            best = max(ranks[:5], key=lambda x: x["hit_rate_pct"]) if len(ranks) >= 5 else {}
            entry.update(
                {
                    "best_rank": best.get("rank"),
                    "rank1_hr": ranks[0]["hit_rate_pct"] if ranks else None,
                    "rank2_hr": ranks[1]["hit_rate_pct"] if len(ranks) > 1 else None,
                    "hit_at_3": hk.get("hit_at_3", {}).get("rate_pct"),
                    "hit_at_5": hk.get("hit_at_5", {}).get("rate_pct"),
                }
            )
        table.append(entry)
    return {"competition_table": table, "min_n_threshold": min_n}


def _fav_regime(r: ReplayRow) -> str:
    if r.odds_home + 0.2 < r.odds_away and r.odds_home < 1.8:
        return "strong_home_favorite"
    if r.odds_home + 0.2 < r.odds_away:
        return "medium_home_favorite"
    if r.odds_away + 0.2 < r.odds_home and r.odds_away < 1.8:
        return "strong_away_favorite"
    if r.odds_away + 0.2 < r.odds_home:
        return "medium_away_favorite"
    return "balanced_market"


def regime_metrics(rows: Sequence[ReplayRow], min_n: int = 100) -> dict[str, Any]:
    buckets: dict[str, list[ReplayRow]] = defaultdict(list)
    for r in rows:
        buckets[_fav_regime(r)].append(r)
        if r.lambda_total < 2.3:
            buckets["low_expected_goals"].append(r)
        elif r.lambda_total <= 3.2:
            buckets["medium_expected_goals"].append(r)
        else:
            buckets["high_expected_goals"].append(r)
    out = {}
    for name, subset in buckets.items():
        n = len(subset)
        if n < min_n:
            out[name] = {"n": n, "label": "LOW_SAMPLE"}
            continue
        rm = rank_metrics(subset)
        hk = hit_at_k(subset)
        ranks = rm.get("rank_table") or []
        best = max(ranks[:5], key=lambda x: x["hit_rate_pct"]) if len(ranks) >= 5 else {}
        out[name] = {
            "n": n,
            "best_rank": best.get("rank"),
            "rank1_hr": ranks[0]["hit_rate_pct"] if ranks else None,
            "rank2_hr": ranks[1]["hit_rate_pct"] if len(ranks) > 1 else None,
            "rank3_hr": ranks[2]["hit_rate_pct"] if len(ranks) > 2 else None,
            "rank4_hr": ranks[3]["hit_rate_pct"] if len(ranks) > 3 else None,
            "rank5_hr": ranks[4]["hit_rate_pct"] if len(ranks) > 4 else None,
            "hit_at_3": hk.get("hit_at_3", {}).get("rate_pct"),
            "hit_at_5": hk.get("hit_at_5", {}).get("rate_pct"),
        }
    return out


def hit_vs_miss_forensic(rows: Sequence[ReplayRow]) -> dict[str, Any]:
    hits = [r for r in rows if r.top5_hit]
    misses = [r for r in rows if not r.top5_hit]

    def avg(subset, fn):
        return round(sum(fn(r) for r in subset) / max(len(subset), 1), 4)

    return {
        "top5_hit_n": len(hits),
        "top5_miss_n": len(misses),
        "hit_avg_lambda_total": avg(hits, lambda r: r.lambda_total),
        "miss_avg_lambda_total": avg(misses, lambda r: r.lambda_total),
        "hit_avg_top1_prob": avg(hits, lambda r: r.top1_prob),
        "miss_avg_top1_prob": avg(misses, lambda r: r.top1_prob),
        "hit_avg_top5_mass": avg(hits, lambda r: r.top5_mass),
        "miss_avg_top5_mass": avg(misses, lambda r: r.top5_mass),
        "hit_avg_entropy": avg(hits, lambda r: r.entropy),
        "miss_avg_entropy": avg(misses, lambda r: r.entropy),
        "hit_avg_lambda_gap": avg(hits, lambda r: abs(r.lambda_home - r.lambda_away)),
        "miss_avg_lambda_gap": avg(misses, lambda r: abs(r.lambda_home - r.lambda_away)),
    }


def reliability_gate_walkforward(rows: Sequence[ReplayRow]) -> dict[str, Any]:
    """Chronological OOS reliability gate using top5_mass + entropy thresholds fit on prior history."""
    ordered = sorted(rows, key=lambda r: (r.event_date, r.fixture_key))
    n = len(ordered)
    if n < 500:
        return {"n": n, "status": "LOW_SAMPLE"}
    split = int(n * 0.7)
    train, test = ordered[:split], ordered[split:]
    top5_mass_median = sorted(r.top5_mass for r in train)[len(train) // 2]
    entropy_median = sorted(r.entropy for r in train)[len(train) // 2]

    def classify(r: ReplayRow) -> str:
        score = 0
        if r.top5_mass >= top5_mass_median:
            score += 1
        if r.entropy <= entropy_median:
            score += 1
        if r.data_quality_score >= 0.5:
            score += 1
        if score >= 2:
            return "HIGH_RELIABILITY"
        if score == 1:
            return "MEDIUM_RELIABILITY"
        return "LOW_RELIABILITY"

    overall_hit5 = sum(1 for r in test if r.top5_hit) / max(len(test), 1)
    classes: dict[str, list[ReplayRow]] = defaultdict(list)
    for r in test:
        classes[classify(r)].append(r)

    table = []
    for cls in ("HIGH_RELIABILITY", "MEDIUM_RELIABILITY", "LOW_RELIABILITY"):
        subset = classes[cls]
        cn = len(subset)
        if not cn:
            table.append({"class": cls, "coverage_pct": 0, "n": 0})
            continue
        top1 = sum(1 for r in subset if r.actual_rank == 1) / cn
        h3 = sum(1 for r in subset if r.actual_rank <= 3) / cn
        h5 = sum(1 for r in subset if r.top5_hit) / cn
        table.append(
            {
                "class": cls,
                "coverage_pct": round(100 * cn / len(test), 2),
                "n": cn,
                "top1_accuracy_pct": round(top1 * 100, 2),
                "hit_at_3_pct": round(h3 * 100, 2),
                "hit_at_5_pct": round(h5 * 100, 2),
                "ci_hit5": bootstrap_ci([1.0 if r.top5_hit else 0.0 for r in subset]),
                "vs_overall_hit5_pp": round(100 * (h5 - overall_hit5), 2),
            }
        )
    high = next((x for x in table if x["class"] == "HIGH_RELIABILITY"), {})
    useful = high.get("n", 0) >= 50 and (high.get("vs_overall_hit5_pp") or 0) >= 2.0
    return {
        "train_n": len(train),
        "test_n": len(test),
        "thresholds": {"top5_mass_median": top5_mass_median, "entropy_median": entropy_median},
        "overall_test_hit5_pct": round(overall_hit5 * 100, 2),
        "classes": table,
        "gate_useful": useful,
    }


def reranking_walkforward(rows: Sequence[ReplayRow]) -> dict[str, Any]:
    """Shadow reranking — must preserve Top5 membership."""
    ordered = sorted(rows, key=lambda r: (r.event_date, r.fixture_key))
    n = len(ordered)
    split = int(n * 0.7)
    test = ordered[split:]

    def metrics(subset: list[ReplayRow], picker) -> dict[str, float]:
        if not subset:
            return {"top1": 0, "hit3": 0, "hit5": 0, "mrr": 0}
        top1 = sum(1 for r in subset if picker(r)[0] == r.actual_score) / len(subset)
        hit3 = sum(1 for r in subset if r.actual_score in picker(r)[:3]) / len(subset)
        hit5 = sum(1 for r in subset if r.actual_score in picker(r)[:5]) / len(subset)
        mrr_vals = []
        for r in subset:
            order = picker(r)
            if r.actual_score in order:
                mrr_vals.append(1.0 / (order.index(r.actual_score) + 1))
            else:
                mrr_vals.append(1.0 / r.actual_rank if r.actual_rank <= 10 else 0)
        mrr = sum(mrr_vals) / len(subset)
        return {"top1": round(top1 * 100, 2), "hit3": round(hit3 * 100, 2), "hit5": round(hit5 * 100, 2), "mrr": round(mrr, 4)}

    def raw_picker(r: ReplayRow) -> list[str]:
        return r.top5

    # historical rank correction from train: which rank hits most often
    train = ordered[:split]
    rank_hits = Counter(r.actual_rank for r in train if r.actual_rank <= 5)
    best_rank = rank_hits.most_common(1)[0][0] if rank_hits else 1

    def global_correction(r: ReplayRow) -> list[str]:
        top5 = [x["scoreline"] for x in r.top10[:5]]
        if best_rank <= len(top5):
            promoted = top5[best_rank - 1]
            rest = [s for s in top5 if s != promoted]
            return [promoted] + rest
        return top5

    comp_rank_hits: dict[str, Counter] = defaultdict(Counter)
    for r in train:
        if r.actual_rank <= 5:
            comp_rank_hits[r.competition][r.actual_rank] += 1

    def comp_correction(r: ReplayRow) -> list[str]:
        br = comp_rank_hits[r.competition].most_common(1)
        br_rank = br[0][0] if br else 1
        top5 = [x["scoreline"] for x in r.top10[:5]]
        if br_rank <= len(top5):
            promoted = top5[br_rank - 1]
            rest = [s for s in top5 if s != promoted]
            return [promoted] + rest
        return top5

    raw_m = metrics(test, raw_picker)
    a_m = metrics(test, global_correction)
    b_m = metrics(test, comp_correction)

    # verify membership preserved
    membership_ok = all(set(global_correction(r)) == set(r.top5) for r in test[:100])

    return {
        "test_n": len(test),
        "membership_preserved": membership_ok,
        "comparison": {
            "Raw ECSE": raw_m,
            "A_global_rank_correction": a_m,
            "B_competition_correction": b_m,
        },
    }


def frozen_vs_replay(replay_rows: Sequence[ReplayRow], frozen: list[dict]) -> dict[str, Any]:
    replay_rm = rank_metrics(replay_rows)
    replay_hk = hit_at_k(replay_rows)
    ranks = replay_rm.get("rank_table") or []

    def frozen_rates(items: list[dict]) -> dict[str, Any]:
        n = len(items)
        if not n:
            return {"n": 0}
        return {
            "n": n,
            "rank1_hr": round(100 * sum(1 for x in items if x.get("actual_rank") == 1) / n, 2),
            "rank2_hr": round(100 * sum(1 for x in items if x.get("actual_rank") == 2) / n, 2),
            "rank3_hr": round(100 * sum(1 for x in items if x.get("actual_rank") == 3) / n, 2),
            "rank4_hr": round(100 * sum(1 for x in items if x.get("actual_rank") == 4) / n, 2),
            "rank5_hr": round(100 * sum(1 for x in items if x.get("actual_rank") == 5) / n, 2),
            "hit_at_3": round(100 * sum(1 for x in items if (x.get("actual_rank") or 999) <= 3) / n, 2),
            "hit_at_5": round(100 * sum(1 for x in items if x.get("top5_hit")) / n, 2),
        }

    return {
        "HISTORICAL_REPLAY_BACKTEST": {
            "dataset": "HISTORICAL_REPLAY_BACKTEST",
            **{f"rank{i}_hr": ranks[i - 1]["hit_rate_pct"] for i in range(1, 6) if len(ranks) >= i},
            "hit_at_3": replay_hk.get("hit_at_3", {}).get("rate_pct"),
            "hit_at_5": replay_hk.get("hit_at_5", {}).get("rate_pct"),
            "n": len(replay_rows),
        },
        "REAL_FROZEN_PREMATCH_EVALUATION": frozen_rates(frozen),
        "note": "Do not merge samples into one headline metric",
    }
