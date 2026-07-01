"""PHASE ECSE-X2-M1 — BTTS × OU exact score grid filter."""

from worldcup_predictor.research.ecse_x2_m1.backtest import run_m1_comparison_backtest
from worldcup_predictor.research.ecse_x2_m1.build import build_ecse_score_distributions_m1
from worldcup_predictor.research.ecse_x2_m1.constants import METHOD_VERSION, TABLE_NAME

__all__ = [
    "METHOD_VERSION",
    "TABLE_NAME",
    "build_ecse_score_distributions_m1",
    "run_m1_comparison_backtest",
]
