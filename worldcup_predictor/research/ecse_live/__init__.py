"""PHASE ECSE-LIVE-1 — ECSE live research package."""

from __future__ import annotations

from typing import Any

__all__ = ["run_ecse_live_cycle"]


def run_ecse_live_cycle(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Lazy import the scheduler so lightweight store users avoid full app imports."""
    from worldcup_predictor.research.ecse_live.scheduler import (
        run_ecse_live_cycle as _run_ecse_live_cycle,
    )

    return _run_ecse_live_cycle(*args, **kwargs)
