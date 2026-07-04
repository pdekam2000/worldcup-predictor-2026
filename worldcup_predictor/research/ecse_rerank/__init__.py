"""ECSE-RERANK-1 — Shadow-only End Result consistency re-ranker."""

from worldcup_predictor.research.ecse_rerank.evaluator import evaluate_shadow_vs_baseline
from worldcup_predictor.research.ecse_rerank.reranker import rerank_ecse_top10_shadow

__all__ = ["rerank_ecse_top10_shadow", "evaluate_shadow_vs_baseline"]
