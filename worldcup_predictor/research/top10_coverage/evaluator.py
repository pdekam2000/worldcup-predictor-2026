"""Coverage ceilings and aggregate metrics."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.top10_coverage.features import rank_bucket


def coverage_rate(matches: list[dict[str, Any]], key: str) -> dict[str, Any]:
    finished = [m for m in matches if m.get("actual_90min")]
    n = len(finished)
    if not n:
        return {"count": 0, "hits": 0, "rate_pct": None}
    hits = sum(1 for m in finished if (m.get("coverage") or {}).get(key))
    return {"count": n, "hits": hits, "rate_pct": round(100 * hits / n, 1)}


def perfect_top3_ceiling(matches: list[dict[str, Any]], pool_key: str, lines_key: str) -> dict[str, Any]:
    """How many matches have actual in pool — theoretical max Top3 if oracle picks 3."""
    finished = [m for m in matches if m.get("actual_90min")]
    n = len(finished)
    if not n:
        return {"count": 0, "hits": 0, "ceiling_pct": None}
    hits = 0
    for m in finished:
        cov = m.get("coverage") or {}
        actual = m.get("actual_90min")
        lines = cov.get(lines_key) or []
        if pool_key == "top5":
            lines = lines[:5]
        elif pool_key == "top10":
            lines = lines[:10]
        elif pool_key == "top20":
            lines = (cov.get("distribution_top20") or [])[:20]
        elif pool_key == "full":
            if cov.get("in_full_distribution"):
                hits += 1
            continue
        if actual and actual in lines:
            hits += 1
    return {"count": n, "hits": hits, "ceiling_pct": round(100 * hits / n, 1)}


def rank_distribution(matches: list[dict[str, Any]]) -> dict[str, int]:
    dist = {b: 0 for b in ("rank_1_5", "rank_6_10", "rank_11_20", "outside_stored", "unavailable")}
    for m in matches:
        if not m.get("actual_90min"):
            continue
        cov = m.get("coverage") or {}
        rank = cov.get("rank_effective")
        in_full = bool(cov.get("in_full_distribution"))
        b = rank_bucket(rank, in_full=in_full)
        dist[b] = dist.get(b, 0) + 1
    return dist


def aggregate_summary(matches: list[dict[str, Any]]) -> dict[str, Any]:
    finished = [m for m in matches if m.get("actual_90min")]
    n = len(finished)
    top3_hits = sum(1 for m in finished if (m.get("coverage") or {}).get("in_top3_snapshot"))
    top5_hits = sum(1 for m in finished if (m.get("coverage") or {}).get("in_top5_snapshot"))
    top10_hits = sum(1 for m in finished if (m.get("coverage") or {}).get("in_top10_snapshot"))
    top20_hits = sum(
        1
        for m in finished
        if (m.get("coverage") or {}).get("in_top20_distribution") is True
    )
    full_hits = sum(1 for m in finished if (m.get("coverage") or {}).get("in_full_distribution"))

    opt_hits = sum(1 for m in finished if m.get("optimized_top3_hit"))

    return {
        "finished_matches": n,
        "top1_in_rank1": sum(1 for m in finished if (m.get("coverage") or {}).get("rank_effective") == 1),
        "top3_hit_rate_pct": round(100 * top3_hits / n, 1) if n else None,
        "top5_coverage_pct": round(100 * top5_hits / n, 1) if n else None,
        "top10_coverage_pct": round(100 * top10_hits / n, 1) if n else None,
        "top20_coverage_pct": round(100 * top20_hits / n, 1) if n else None,
        "full_distribution_coverage_pct": round(100 * full_hits / n, 1) if n else None,
        "optimized_s5_top3_pct": round(100 * opt_hits / n, 1) if n else None,
        "rank_distribution": rank_distribution(matches),
        "ceilings": {
            "perfect_top3_from_top5": perfect_top3_ceiling(matches, "top5", "snapshot_top10"),
            "perfect_top3_from_top10": perfect_top3_ceiling(matches, "top10", "snapshot_top10"),
            "perfect_top3_from_top20": perfect_top3_ceiling(matches, "top20", "distribution_top20"),
            "perfect_top3_from_full": perfect_top3_ceiling(matches, "full", "distribution_top20"),
        },
        "in_top5_outside_top3": sum(
            1
            for m in finished
            if (m.get("coverage") or {}).get("in_top5_snapshot")
            and not (m.get("coverage") or {}).get("in_top3_snapshot")
        ),
    }


def can_89pct_from_candidates(summary: dict[str, Any]) -> dict[str, Any]:
    n = summary.get("finished_matches") or 0
    top10_pct = summary.get("top10_coverage_pct") or 0
    top20_pct = summary.get("top20_coverage_pct") or 0
    full_pct = summary.get("full_distribution_coverage_pct") or 0
    required = __import__("math").ceil(n * 0.89) if n else 0
    return {
        "sample_size": n,
        "required_hits_for_89pct": required,
        "top10_coverage_pct": top10_pct,
        "top20_coverage_pct": top20_pct,
        "full_coverage_pct": full_pct,
        "89pct_possible_from_top10_only": top10_pct >= 89.0,
        "89pct_possible_from_top20_only": top20_pct >= 89.0,
        "89pct_possible_from_full_pool": full_pct >= 89.0,
        "verdict": (
            "TOP10_SHOWS_89_THEORETICALLY_POSSIBLE"
            if top10_pct >= 89.0
            else "TOP10_SHOWS_CANDIDATE_GENERATION_LIMIT"
            if full_pct < 89.0
            else "RANKING_LIMIT_WITHIN_POOL"
        ),
    }
