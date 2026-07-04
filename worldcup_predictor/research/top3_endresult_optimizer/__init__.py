"""TOP3-ENDRESULT-OPTIMIZER-1 — Shadow-only 3-candidate End Result portfolio optimizer."""

from worldcup_predictor.research.top3_endresult_optimizer.optimizer import STRATEGIES, optimize_top3
from worldcup_predictor.research.top3_endresult_optimizer.runner import run_optimizer_backtest

__all__ = ["STRATEGIES", "optimize_top3", "run_optimizer_backtest"]
