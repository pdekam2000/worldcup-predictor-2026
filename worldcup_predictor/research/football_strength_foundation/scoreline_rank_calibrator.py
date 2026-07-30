"""Diagnostic rank calibrator (shadow only — must not conceal bad lambdas)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.football_strength_foundation.score_v2 import rank_bias_table


def analyze_rank_bias(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expect rows with actual_score, predicted_rank, top5."""
    return rank_bias_table(rows)


def suggest_rank_adjustments(bias_rows: list[dict[str, Any]], *, min_n: int = 8) -> list[dict[str, Any]]:
    """
    Non-binding suggestions: scorelines with systematically poor mean ranks.
    Never auto-apply to canonical outputs.
    """
    out = []
    for r in bias_rows:
        n = int(r.get("n") or 0)
        if n < min_n:
            continue
        mean_rank = r.get("mean_predicted_rank")
        if mean_rank is None:
            continue
        if mean_rank > 8:
            out.append(
                {
                    "scoreline": r["scoreline"],
                    "n": n,
                    "mean_predicted_rank": mean_rank,
                    "suggestion": "under-ranked; inspect lambda means before any rank remap",
                    "apply_to_canonical": False,
                }
            )
    return out
