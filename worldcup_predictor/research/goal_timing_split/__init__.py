"""PHASE GT-1 — First goal timing split (research only)."""

from worldcup_predictor.research.goal_timing_split.predictor import MODEL_VERSION, predict_goal_timing_split
from worldcup_predictor.research.goal_timing_split.runner import run_goal_timing_split_smoke

__all__ = ["MODEL_VERSION", "predict_goal_timing_split", "run_goal_timing_split_smoke"]
