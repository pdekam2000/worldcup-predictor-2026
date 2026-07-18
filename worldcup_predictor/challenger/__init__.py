"""Challenger Model Program — isolated shadow framework.

PUBLIC_VISIBLE = False
FINAL_DECISION_AUTHORITY = False
Does not modify WDE / ECSE / BTTS / O/U.
"""

from __future__ import annotations

from worldcup_predictor.challenger.constants import (
    CHALLENGER_ENGINE_MODE,
    CHALLENGER_FINAL_DECISION_AUTHORITY,
    CHALLENGER_IS_SHADOW,
    CHALLENGER_PUBLIC_VISIBLE,
)

__all__ = [
    "CHALLENGER_ENGINE_MODE",
    "CHALLENGER_FINAL_DECISION_AUTHORITY",
    "CHALLENGER_IS_SHADOW",
    "CHALLENGER_PUBLIC_VISIBLE",
]
