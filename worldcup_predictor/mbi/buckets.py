"""Part B/C — bucket aggregation and calibration metrics."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from worldcup_predictor.mbi.models import BucketStats, OddsSelection, TARGET_MARKETS, odds_bucket_edges


def build_bucket_table(selections: list[OddsSelection]) -> list[dict[str, Any]]:
    """Aggregate hit rate vs implied probability per market/bucket/selection."""
    groups: dict[tuple[str, str, str], list[OddsSelection]] = defaultdict(list)
    for row in selections:
        if row.hit is None or not row.bucket:
            continue
        if row.market_key not in TARGET_MARKETS:
            continue
        groups[(row.market_key, row.bucket, row.selection)].append(row)

    stats: list[BucketStats] = []
    for (market_key, bucket, selection), rows in sorted(groups.items()):
        n = len(rows)
        if n == 0:
            continue
        hits = sum(1 for r in rows if r.hit)
        hit_rate = round(hits / n, 4)
        implied_mean = round(sum(r.implied_probability or 0 for r in rows) / n, 4)
        gap = round(hit_rate - implied_mean, 4)
        over = max(0.0, gap)
        under = max(0.0, -gap)
        stats.append(
            BucketStats(
                market_key=market_key,
                bucket=bucket,
                selection=selection,
                count=n,
                hit_rate=hit_rate,
                implied_mean=implied_mean,
                calibration_gap=gap,
                overperformance=round(over, 4),
                underperformance=round(under, 4),
            )
        )
    return [s.to_dict() for s in stats]


def market_bucket_summary(bucket_table: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-market rollup across buckets."""
    by_market: dict[str, dict[str, Any]] = {}
    for row in bucket_table:
        mk = row["market_key"]
        entry = by_market.setdefault(
            mk,
            {
                "market_key": mk,
                "buckets": 0,
                "selections": 0,
                "total_count": 0,
                "weighted_gap": 0.0,
                "abs_gap_sum": 0.0,
            },
        )
        entry["buckets"] += 1
        entry["selections"] += 1
        n = int(row["count"])
        entry["total_count"] += n
        entry["weighted_gap"] += float(row["calibration_gap"]) * n
        entry["abs_gap_sum"] += abs(float(row["calibration_gap"])) * n

    for mk, entry in by_market.items():
        tc = entry["total_count"] or 1
        entry["mean_calibration_gap"] = round(entry["weighted_gap"] / tc, 4)
        entry["mean_abs_gap"] = round(entry["abs_gap_sum"] / tc, 4)
    return by_market


def overall_calibration(selections: list[OddsSelection]) -> dict[str, Any]:
    """Global Brier and ECE using implied probability vs binary hit."""
    scored = [r for r in selections if r.hit is not None and r.implied_probability]
    if not scored:
        return {"brier": None, "ece": None, "n": 0}

    brier = sum(((1.0 if r.hit else 0.0) - r.implied_probability) ** 2 for r in scored) / len(scored)
    # 10-bin ECE on implied probability
    bins: list[list[OddsSelection]] = [[] for _ in range(10)]
    for r in scored:
        idx = min(9, int((r.implied_probability or 0) * 10))
        bins[idx].append(r)
    ece = 0.0
    total = len(scored)
    for b in bins:
        if not b:
            continue
        conf = sum(r.implied_probability or 0 for r in b) / len(b)
        acc = sum(1 for r in b if r.hit) / len(b)
        ece += (len(b) / total) * abs(acc - conf)

    return {"brier": round(brier, 4), "ece": round(ece, 4), "n": len(scored)}


def bucket_labels() -> list[str]:
    return [label for _, _, label in odds_bucket_edges()]
