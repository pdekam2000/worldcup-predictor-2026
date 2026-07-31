"""Top10 consensus ranking across approved exact-score models."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.bet_coverage_optimizer.exact_consensus import (
    rank_consensus_scores,
    select_exact_scores,
)
from worldcup_predictor.research.bet_coverage_optimizer.models import ModelTopScores, ScoreEntry
from worldcup_predictor.research.top10_to_5_optimizer.market_semantics import score_attributes


def _to_model(model_id: str, scores: list[dict[str, Any]] | list[ScoreEntry], *, weight: float = 1.0) -> ModelTopScores:
    entries: list[ScoreEntry] = []
    for i, s in enumerate(scores or [], start=1):
        if isinstance(s, ScoreEntry):
            entries.append(s)
            continue
        entries.append(
            ScoreEntry(
                score=str(s.get("score")).replace(" ", ""),
                probability=float(s.get("probability") or 0.0),
                rank=int(s["rank"]) if s.get("rank") is not None else i,
                source=str(s.get("source") or model_id),
            )
        )
    return ModelTopScores(model_id=model_id, scores=entries, weight=float(weight))


def _scores_block(block: Any) -> list[dict[str, Any]]:
    if isinstance(block, list):
        return block
    if isinstance(block, dict) and isinstance(block.get("scores"), list):
        return list(block["scores"])
    return []


def models_from_fixture_payload(payload: dict[str, Any]) -> list[ModelTopScores]:
    models: list[ModelTopScores] = []
    can = _scores_block(payload.get("canonical") or payload.get("canonical_top10"))
    if can:
        models.append(_to_model("canonical", can))
    ev = _scores_block(payload.get("exact_v2") or payload.get("exact_v2_top10"))
    if ev:
        models.append(_to_model("exact_v2", ev))
    for extra in payload.get("other_shadow_models") or []:
        if isinstance(extra, dict) and extra.get("scores"):
            models.append(
                _to_model(str(extra.get("model_id") or "shadow"), extra["scores"], weight=float(extra.get("weight") or 0.5))
            )
    if not models and payload.get("top10"):
        models.append(_to_model("canonical", _scores_block(payload["top10"]) or payload["top10"]))
    return models


def build_consensus_top10(
    payload: dict[str, Any],
    *,
    top10_source: str = "consensus",
    top_n: int = 10,
) -> list[dict[str, Any]]:
    """
    Build consensus Top10 pool without overwriting original model ranks.

    Ranking priority (consensus mode):
      1. appearance count
      2. weighted aggregate probability
      3. canonical rank
      4. Exact V2 rank
      5. deterministic scoreline tie-break
    """
    models = models_from_fixture_payload(payload)
    source = str(top10_source or "consensus").lower()

    if source == "canonical":
        can = next((m for m in models if m.model_id == "canonical"), None)
        if can is None:
            return []
        ranked_src = [
            {
                "score": s.score,
                "consensus_count": 1,
                "weighted_probability": float(s.probability),
                "canonical_rank": s.rank,
                "exact_v2_rank": None,
                "appearances": [{"model_id": "canonical", "rank": s.rank, "probability": s.probability}],
            }
            for s in can.scores[:top_n]
        ]
    elif source == "exact_v2":
        ev = next((m for m in models if m.model_id == "exact_v2"), None)
        if ev is None:
            return []
        ranked_src = [
            {
                "score": s.score,
                "consensus_count": 1,
                "weighted_probability": float(s.probability),
                "canonical_rank": None,
                "exact_v2_rank": s.rank,
                "appearances": [{"model_id": "exact_v2", "rank": s.rank, "probability": s.probability}],
            }
            for s in ev.scores[:top_n]
        ]
    else:
        ranked_src = rank_consensus_scores(models)[:top_n]

    out: list[dict[str, Any]] = []
    for i, row in enumerate(ranked_src, start=1):
        score = str(row["score"]).replace(" ", "")
        can_p = None
        ev_p = None
        for a in row.get("appearances") or []:
            mid = str(a.get("model_id") or "").lower()
            if mid in {"canonical", "ecse", "wde_ecse", "canonical_ecse"} and a.get("probability") is not None:
                can_p = float(a["probability"])
            if mid in {"exact_v2", "exact-v2", "exactv2"} and a.get("probability") is not None:
                ev_p = float(a["probability"])
        attrs = score_attributes(score)
        out.append(
            {
                **attrs,
                "scoreline": score,
                "consensus_count": int(row.get("consensus_count") or 0),
                "canonical_probability": can_p,
                "exact_v2_probability": ev_p,
                "aggregate_probability": float(row.get("weighted_probability") or 0.0),
                "canonical_rank": row.get("canonical_rank"),
                "exact_v2_rank": row.get("exact_v2_rank"),
                "consensus_rank": i,
                "probability": float(
                    can_p if can_p is not None else (ev_p if ev_p is not None else row.get("weighted_probability") or 0.0)
                ),
            }
        )
    return out


def lock_exact_three(consensus_top10: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Exact #1/#2/#3 = top three consensus ranks; never drop for low odds."""
    selected = []
    seen: set[str] = set()
    for row in consensus_top10:
        sc = str(row.get("scoreline") or row.get("score") or "").replace(" ", "")
        if not sc or sc in seen:
            continue
        seen.add(sc)
        selected.append({**row, "scoreline": sc, "selection_slot": f"exact_{len(selected)+1}"})
        if len(selected) >= 3:
            break
    return selected


# Keep BCO select available for parity checks
__all__ = [
    "build_consensus_top10",
    "lock_exact_three",
    "models_from_fixture_payload",
    "select_exact_scores",
]
