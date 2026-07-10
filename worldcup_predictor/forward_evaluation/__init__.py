"""Unified forward evaluation — read-only observational tracking (Tier A + Tier B)."""

from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
    if name == "run_daily_forward_evaluation":
        from worldcup_predictor.forward_evaluation.runner import run_daily_forward_evaluation

        return run_daily_forward_evaluation
    if name == "sync_and_evaluate_pending":
        from worldcup_predictor.forward_evaluation.runner import sync_and_evaluate_pending

        return sync_and_evaluate_pending
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["run_daily_forward_evaluation", "sync_and_evaluate_pending"]
