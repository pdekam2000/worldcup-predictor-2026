"""Exact-score consensus ranking across approved model distributions."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.bet_coverage_optimizer.models import ExactSelection, ModelTopScores, ScoreEntry


def _rank_map(model: ModelTopScores) -> dict[str, int]:
    out: dict[str, int] = {}
    for i, s in enumerate(model.scores, start=1):
        key = str(s.score).replace(" ", "")
        out[key] = int(s.rank) if s.rank is not None else i
    return out


def _prob_map(model: ModelTopScores) -> dict[str, float]:
    return {str(s.score).replace(" ", ""): float(s.probability or 0.0) for s in model.scores}


def build_consensus_pool(models: list[ModelTopScores]) -> dict[str, dict[str, Any]]:
    pool: dict[str, dict[str, Any]] = {}
    for model in models:
        ranks = _rank_map(model)
        probs = _prob_map(model)
        for score, rank in ranks.items():
            row = pool.setdefault(
                score,
                {
                    "score": score,
                    "consensus_count": 0,
                    "weighted_probability": 0.0,
                    "appearances": [],
                    "canonical_rank": None,
                    "exact_v2_rank": None,
                    "lambda_v2_rank": None,
                },
            )
            row["consensus_count"] += 1
            row["weighted_probability"] += float(model.weight) * float(probs.get(score) or 0.0)
            row["appearances"].append({"model_id": model.model_id, "rank": rank, "probability": probs.get(score)})
            mid = str(model.model_id).lower()
            if mid in {"canonical", "ecse", "wde_ecse", "canonical_ecse"}:
                row["canonical_rank"] = rank
            elif mid in {"exact_v2", "exact-v2", "exactv2"}:
                row["exact_v2_rank"] = rank
            elif mid in {"lambda_v2", "lambda-v2", "lambdav2"}:
                row["lambda_v2_rank"] = rank
    return pool


def rank_consensus_scores(models: list[ModelTopScores]) -> list[dict[str, Any]]:
    """
    Rank primarily by repeated appearance, then:
      1. consensus_count
      2. weighted aggregate probability
      3. canonical rank (lower better; missing -> large)
      4. exact-v2 rank (lower better; missing -> large)
    """
    pool = build_consensus_pool(models)
    rows = list(pool.values())

    def sort_key(r: dict[str, Any]) -> tuple:
        return (
            -int(r["consensus_count"]),
            -float(r["weighted_probability"]),
            int(r["canonical_rank"]) if r["canonical_rank"] is not None else 10_000,
            int(r["exact_v2_rank"]) if r["exact_v2_rank"] is not None else 10_000,
            str(r["score"]),
        )

    rows.sort(key=sort_key)
    for i, r in enumerate(rows, start=1):
        r["consensus_rank"] = i
    return rows


def select_exact_scores(models: list[ModelTopScores], *, exact_count: int = 3) -> list[ExactSelection]:
    ranked = rank_consensus_scores(models)
    selected: list[ExactSelection] = []
    seen: set[str] = set()
    for row in ranked:
        score = str(row["score"])
        if score in seen:
            continue
        seen.add(score)
        selected.append(
            ExactSelection(
                score=score,
                consensus_count=int(row["consensus_count"]),
                weighted_probability=round(float(row["weighted_probability"]), 8),
                canonical_rank=row.get("canonical_rank"),
                exact_v2_rank=row.get("exact_v2_rank"),
                selection_id=f"exact:{score}",
                label=f"Exact {score}",
            )
        )
        if len(selected) >= int(exact_count):
            break
    return selected


def merge_top_n_targets(
    models: list[ModelTopScores],
    *,
    top_n: int = 8,
) -> list[ScoreEntry]:
    """Union Top-N targets: prefer consensus ranking, attach max model probability."""
    ranked = rank_consensus_scores(models)
    out: list[ScoreEntry] = []
    for i, row in enumerate(ranked[: int(top_n)], start=1):
        # Use max appearance probability as display mass contribution
        probs = [float(a.get("probability") or 0.0) for a in row.get("appearances") or []]
        p = max(probs) if probs else float(row.get("weighted_probability") or 0.0)
        # Prefer canonical probability when present
        for a in row.get("appearances") or []:
            if str(a.get("model_id") or "").lower() in {"canonical", "ecse", "canonical_ecse", "wde_ecse"}:
                if a.get("probability") is not None:
                    p = float(a["probability"])
                    break
        out.append(ScoreEntry(score=str(row["score"]), probability=float(p), rank=i, source="consensus"))
    return out


def model_snapshot_hash(models: list[ModelTopScores]) -> str:
    import hashlib
    import json

    payload = [
        {
            "model_id": m.model_id,
            "weight": m.weight,
            "scores": [(s.score, round(float(s.probability), 8), s.rank) for s in m.scores],
        }
        for m in models
    ]
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
