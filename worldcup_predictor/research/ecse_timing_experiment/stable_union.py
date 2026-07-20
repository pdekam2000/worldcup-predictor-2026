"""STABLE_UNION_TOP5 research comparator (non-canonical)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.ecse_timing_experiment.hashing import as_prob


def _entries(payload: dict[str, Any], snapshot_class: str) -> list[dict[str, Any]]:
    ecse = payload.get("ecse") or {}
    out: list[dict[str, Any]] = []
    scores = ecse.get("scores") or []
    for i, sc in enumerate(scores[:5], start=1):
        t = ecse.get(f"top{i}") or {}
        prob = as_prob(t.get("probability")) if isinstance(t, dict) else None
        out.append(
            {
                "score": str(sc),
                "rank": i,
                "probability": prob,
                "snapshot_class": snapshot_class,
            }
        )
    if out:
        return out
    for i in range(1, 6):
        t = ecse.get(f"top{i}") or {}
        if isinstance(t, dict) and t.get("score"):
            out.append(
                {
                    "score": str(t["score"]),
                    "rank": i,
                    "probability": as_prob(t.get("probability")),
                    "snapshot_class": snapshot_class,
                }
            )
    return out


def build_stable_union(
    snapshots: dict[str, dict[str, Any]],
    *,
    class_order: tuple[str, ...] = ("EARLY", "MID", "LATE"),
) -> dict[str, Any]:
    """Build research-only Top5 from EARLY/MID/LATE payloads.

    Ranking:
      1) number of snapshots containing the score (desc)
      2) average rank (asc)
      3) average probability (desc)
      4) recency (later snapshot preferred) as final tie-break
    Prefer scores present in >=2 snapshots when filling.
    Track scores removed only at the latest available snapshot.
    """
    present = [c for c in class_order if c in snapshots and snapshots[c]]
    if not present:
        return {
            "scores": [],
            "research_only": True,
            "canonical": False,
            "final_decision_authority": False,
            "label": "STABLE_UNION_TOP5",
            "note": "no_snapshots",
        }

    agg: dict[str, dict[str, Any]] = {}
    recency_rank = {c: i for i, c in enumerate(present)}
    for sc_class in present:
        for e in _entries(snapshots[sc_class], sc_class):
            sc = e["score"]
            bucket = agg.setdefault(
                sc,
                {"score": sc, "n": 0, "ranks": [], "probs": [], "classes": [], "max_recency": -1},
            )
            bucket["n"] += 1
            bucket["ranks"].append(int(e["rank"]))
            if e["probability"] is not None:
                bucket["probs"].append(float(e["probability"]))
            bucket["classes"].append(sc_class)
            bucket["max_recency"] = max(bucket["max_recency"], recency_rank[sc_class])

    def sort_key(item: dict[str, Any]) -> tuple:
        avg_rank = sum(item["ranks"]) / len(item["ranks"])
        avg_prob = (sum(item["probs"]) / len(item["probs"])) if item["probs"] else -1.0
        return (-item["n"], avg_rank, -avg_prob, -item["max_recency"])

    preferred = sorted([v for v in agg.values() if v["n"] >= 2], key=sort_key)
    fillers = sorted([v for v in agg.values() if v["n"] < 2], key=sort_key)
    ordered = preferred + fillers

    top5 = []
    for i, item in enumerate(ordered[:5], start=1):
        avg_rank = sum(item["ranks"]) / len(item["ranks"])
        avg_prob = (sum(item["probs"]) / len(item["probs"])) if item["probs"] else None
        top5.append(
            {
                "rank": i,
                "score": item["score"],
                "n_snapshots": item["n"],
                "avg_rank": round(avg_rank, 4),
                "avg_probability": None if avg_prob is None else round(avg_prob, 6),
                "present_in": item["classes"],
            }
        )

    latest = present[-1]
    earlier = present[:-1]
    latest_scores = {e["score"] for e in _entries(snapshots[latest], latest)}
    earlier_scores: set[str] = set()
    for c in earlier:
        earlier_scores |= {e["score"] for e in _entries(snapshots[c], c)}
    removed_only_at_latest = sorted(earlier_scores - latest_scores)

    return {
        "label": "STABLE_UNION_TOP5",
        "scores": [t["score"] for t in top5],
        "top5": top5,
        "removed_only_at_latest": removed_only_at_latest,
        "latest_class": latest,
        "source_classes": present,
        "research_only": True,
        "canonical": False,
        "final_decision_authority": False,
    }
