"""Constants for Top10-to-5 research optimizer."""

from __future__ import annotations

WIN = "WIN"
LOSS = "LOSS"
PUSH = "PUSH"
UNSUPPORTED = "UNSUPPORTED"

CLASS_PROFIT = "PROFIT"
CLASS_BREAK_EVEN = "BREAK_EVEN"
CLASS_PARTIAL = "PARTIAL_RECOVERY"
CLASS_FULL_LOSS = "FULL_LOSS"
CLASS_UNKNOWN = "UNKNOWN_DUE_TO_MISSING_ODDS"

STATUS_READY = "TOP10_TO_5_READY"
STATUS_PARTIAL = "TOP10_TO_5_PARTIAL"
STATUS_UNPRICED = "TOP10_TO_5_UNPRICED"
STATUS_MARKET_INSUFFICIENT = "TOP10_TO_5_MARKET_INSUFFICIENT"
STATUS_STALE = "TOP10_TO_5_BLOCKED_STALE_ODDS"
STATUS_RESEARCH = "TOP10_TO_5_RESEARCH_ONLY"

STAKE_MODES = (
    "equal_stake",
    "probability_weighted",
    "profit_floor",
    "minmax_loss",
    "score_weighted",
    "fractional_kelly_research",
)

TOP10_SOURCES = ("canonical", "exact_v2", "consensus")

COUPON_CAPS = (25, 40, 64, 125)

MANUAL_SOURCE = "manual_screenshot_transcription"
REAL_SOURCE_TYPES = frozenset(
    {
        "live_provider_api",
        "structured_bookmaker_feed",
        MANUAL_SOURCE,
        "manual_screenshot_transcription",
    }
)

STALE_MARKERS = frozenset({"STALE_ODDS", "STALE", "EXPIRED", "TOO_OLD"})
