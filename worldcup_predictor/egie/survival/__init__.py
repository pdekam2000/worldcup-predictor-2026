"""Phase 52A — Survival analysis for EGIE (shadow mode)."""

from worldcup_predictor.egie.survival.backtest_runner import SurvivalBacktestRunner
from worldcup_predictor.egie.survival.dataset_builder import SurvivalDatasetBuilder
from worldcup_predictor.egie.survival.kaplan_meier import fit_kaplan_meier, goal_probability_before
from worldcup_predictor.egie.survival.shadow_runner import SurvivalShadowRunner
from worldcup_predictor.egie.survival.shadow_store import SurvivalShadowStore
from worldcup_predictor.egie.survival.survival_engine import SurvivalGoalTimingEngine

__all__ = [
    "SurvivalDatasetBuilder",
    "SurvivalBacktestRunner",
    "SurvivalGoalTimingEngine",
    "SurvivalShadowRunner",
    "SurvivalShadowStore",
    "fit_kaplan_meier",
    "goal_probability_before",
]
