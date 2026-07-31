"""Correlation / diversification among fixtures (research-only)."""

from __future__ import annotations

from collections import Counter
from typing import Any


def estimate_pair_correlation(a: dict[str, Any], b: dict[str, Any]) -> float:
    """Deterministic heuristic correlation in [0, 1] — not a statistical estimator of returns."""
    score = 0.0
    if str(a.get("league")) == str(b.get("league")) and a.get("league"):
        score += 0.45
    tags_a = set(a.get("market_tags") or [])
    tags_b = set(b.get("market_tags") or [])
    if tags_a and tags_b:
        jacc = len(tags_a & tags_b) / max(1, len(tags_a | tags_b))
        score += 0.35 * jacc
    # Similar favorite strength
    oa, ob = a.get("odds_home"), b.get("odds_home")
    if oa and ob:
        diff = abs(float(oa) - float(ob))
        score += 0.20 * max(0.0, 1.0 - diff / 1.5)
    return round(min(1.0, score), 6)


def analyze_diversification(fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(fixtures)
    pairs = []
    total = 0.0
    high = 0
    for i in range(n):
        for j in range(i + 1, n):
            c = estimate_pair_correlation(fixtures[i], fixtures[j])
            pairs.append(
                {
                    "fixture_a": fixtures[i]["fixture_id"],
                    "fixture_b": fixtures[j]["fixture_id"],
                    "correlation": c,
                }
            )
            total += c
            if c >= 0.55:
                high += 1
    n_pairs = len(pairs) or 1
    mean_corr = total / n_pairs
    leagues = Counter(str(f.get("league") or "unknown") for f in fixtures)
    markets = Counter()
    for f in fixtures:
        for t in f.get("market_tags") or []:
            markets[str(t)] += 1

    diversification_score = round(100.0 * max(0.0, 1.0 - mean_corr), 4)
    return {
        "research_only": True,
        "n_fixtures": n,
        "n_pairs": len(pairs),
        "mean_pairwise_correlation": round(mean_corr, 6),
        "high_correlation_pairs": high,
        "diversification_score": diversification_score,
        "league_concentration": dict(leagues),
        "market_concentration": dict(markets.most_common(12)),
        "pairs": pairs[:50],  # cap artifact size
        "over_concentrated": mean_corr >= 0.55 or (leagues and max(leagues.values()) / max(1, n) >= 0.67),
    }
