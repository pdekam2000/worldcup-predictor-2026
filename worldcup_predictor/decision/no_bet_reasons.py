"""Canonical no_bet reason taxonomy — Phase 1.

Typed, stable machine codes for reason-based no_bet recomputation.
Does not change runtime behavior by itself; consumers opt in via evaluator.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final


class NoBetSeverity(str, Enum):
    BLOCKING = "blocking"
    INFORMATIONAL = "informational"


class NoBetSourceStage(str, Enum):
    SCORING_ENGINE = "SCORING_ENGINE"
    WDE_DECIDE = "WDE_DECIDE"
    ADAPTIVE_CONFIDENCE = "ADAPTIVE_CONFIDENCE"
    FINAL_POST_ENRICHMENT = "FINAL_POST_ENRICHMENT"
    PICK_VISIBILITY = "PICK_VISIBILITY"
    ODDS_GATE = "ODDS_GATE"
    MANUAL = "MANUAL"
    LEGACY = "LEGACY"
    RESEARCH = "RESEARCH"


@dataclass(frozen=True, slots=True)
class NoBetReasonMeta:
    """Static metadata for one reason code."""

    code: str
    source_stage: NoBetSourceStage
    severity: NoBetSeverity
    clearable: bool
    user_facing_description: str


class NoBetReason(str, Enum):
    """Stable machine codes for active no_bet reasons."""

    CONFIDENCE_BELOW_60 = "CONFIDENCE_BELOW_60"
    WDE_DATA_QUALITY_BELOW_50 = "WDE_DATA_QUALITY_BELOW_50"
    VISIBILITY_DATA_QUALITY_BELOW_45 = "VISIBILITY_DATA_QUALITY_BELOW_45"
    SCORING_DATA_QUALITY_BELOW_45 = "SCORING_DATA_QUALITY_BELOW_45"
    PLACEHOLDER_DATA = "PLACEHOLDER_DATA"
    STALE_ODDS = "STALE_ODDS"
    INCOMPLETE_ODDS = "INCOMPLETE_ODDS"
    MISSING_ODDS = "MISSING_ODDS"
    UNSUPPORTED_FIXTURE = "UNSUPPORTED_FIXTURE"
    UNSUPPORTED_MARKET = "UNSUPPORTED_MARKET"
    MODEL_CONFLICT = "MODEL_CONFLICT"
    WDE_ECSE_CONFLICT = "WDE_ECSE_CONFLICT"
    HIGH_CONFLICT = "HIGH_CONFLICT"
    INSUFFICIENT_PREMATCH_DATA = "INSUFFICIENT_PREMATCH_DATA"
    INVALID_PREDICTION_STATE = "INVALID_PREDICTION_STATE"
    PROVIDER_DATA_INVALID = "PROVIDER_DATA_INVALID"
    FIXTURE_ALREADY_STARTED = "FIXTURE_ALREADY_STARTED"
    MANUAL_BLOCK = "MANUAL_BLOCK"
    LEGACY_UNKNOWN_REASON = "LEGACY_UNKNOWN_REASON"

    @property
    def meta(self) -> NoBetReasonMeta:
        return REASON_META[self]


# Thresholds — must match production gates (do not change without explicit approval).
CONFIDENCE_NO_BET_THRESHOLD: Final[float] = 60.0
WDE_DATA_QUALITY_NO_BET_THRESHOLD: Final[float] = 50.0
VISIBILITY_DATA_QUALITY_THRESHOLD: Final[float] = 45.0
SCORING_DATA_QUALITY_THRESHOLD: Final[float] = 45.0

REASON_META: Final[dict[NoBetReason, NoBetReasonMeta]] = {
    NoBetReason.CONFIDENCE_BELOW_60: NoBetReasonMeta(
        code=NoBetReason.CONFIDENCE_BELOW_60.value,
        source_stage=NoBetSourceStage.FINAL_POST_ENRICHMENT,
        severity=NoBetSeverity.BLOCKING,
        clearable=True,
        user_facing_description="Final confidence is below the official minimum of 60.",
    ),
    NoBetReason.WDE_DATA_QUALITY_BELOW_50: NoBetReasonMeta(
        code=NoBetReason.WDE_DATA_QUALITY_BELOW_50.value,
        source_stage=NoBetSourceStage.WDE_DECIDE,
        severity=NoBetSeverity.BLOCKING,
        clearable=True,
        user_facing_description="WDE data quality is below the no-bet threshold of 50.",
    ),
    NoBetReason.VISIBILITY_DATA_QUALITY_BELOW_45: NoBetReasonMeta(
        code=NoBetReason.VISIBILITY_DATA_QUALITY_BELOW_45.value,
        source_stage=NoBetSourceStage.PICK_VISIBILITY,
        severity=NoBetSeverity.BLOCKING,
        clearable=True,
        user_facing_description="Pick-visibility data quality is below 45.",
    ),
    NoBetReason.SCORING_DATA_QUALITY_BELOW_45: NoBetReasonMeta(
        code=NoBetReason.SCORING_DATA_QUALITY_BELOW_45.value,
        source_stage=NoBetSourceStage.SCORING_ENGINE,
        severity=NoBetSeverity.BLOCKING,
        clearable=True,
        user_facing_description="Scoring-engine data quality is below 45.",
    ),
    NoBetReason.PLACEHOLDER_DATA: NoBetReasonMeta(
        code=NoBetReason.PLACEHOLDER_DATA.value,
        source_stage=NoBetSourceStage.SCORING_ENGINE,
        severity=NoBetSeverity.BLOCKING,
        clearable=True,
        user_facing_description="Prediction is based on placeholder / incomplete table data.",
    ),
    NoBetReason.STALE_ODDS: NoBetReasonMeta(
        code=NoBetReason.STALE_ODDS.value,
        source_stage=NoBetSourceStage.ODDS_GATE,
        severity=NoBetSeverity.BLOCKING,
        clearable=True,
        user_facing_description="Odds are stale relative to kickoff freshness rules.",
    ),
    NoBetReason.INCOMPLETE_ODDS: NoBetReasonMeta(
        code=NoBetReason.INCOMPLETE_ODDS.value,
        source_stage=NoBetSourceStage.ODDS_GATE,
        severity=NoBetSeverity.BLOCKING,
        clearable=True,
        user_facing_description="Odds payload is incomplete for required markets.",
    ),
    NoBetReason.MISSING_ODDS: NoBetReasonMeta(
        code=NoBetReason.MISSING_ODDS.value,
        source_stage=NoBetSourceStage.ODDS_GATE,
        severity=NoBetSeverity.BLOCKING,
        clearable=True,
        user_facing_description="Required odds are missing.",
    ),
    NoBetReason.UNSUPPORTED_FIXTURE: NoBetReasonMeta(
        code=NoBetReason.UNSUPPORTED_FIXTURE.value,
        source_stage=NoBetSourceStage.SCORING_ENGINE,
        severity=NoBetSeverity.BLOCKING,
        clearable=True,
        user_facing_description="Fixture type is unsupported for official prediction.",
    ),
    NoBetReason.UNSUPPORTED_MARKET: NoBetReasonMeta(
        code=NoBetReason.UNSUPPORTED_MARKET.value,
        source_stage=NoBetSourceStage.SCORING_ENGINE,
        severity=NoBetSeverity.BLOCKING,
        clearable=True,
        user_facing_description="Requested market is unsupported.",
    ),
    NoBetReason.MODEL_CONFLICT: NoBetReasonMeta(
        code=NoBetReason.MODEL_CONFLICT.value,
        source_stage=NoBetSourceStage.WDE_DECIDE,
        severity=NoBetSeverity.BLOCKING,
        clearable=True,
        user_facing_description="Model signals conflict beyond accepted tolerance.",
    ),
    NoBetReason.WDE_ECSE_CONFLICT: NoBetReasonMeta(
        code=NoBetReason.WDE_ECSE_CONFLICT.value,
        source_stage=NoBetSourceStage.WDE_DECIDE,
        severity=NoBetSeverity.BLOCKING,
        clearable=True,
        user_facing_description="WDE and ECSE disagree on a governed conflict gate.",
    ),
    NoBetReason.HIGH_CONFLICT: NoBetReasonMeta(
        code=NoBetReason.HIGH_CONFLICT.value,
        source_stage=NoBetSourceStage.WDE_DECIDE,
        severity=NoBetSeverity.BLOCKING,
        clearable=True,
        user_facing_description="High-severity specialist conflict remains active.",
    ),
    NoBetReason.INSUFFICIENT_PREMATCH_DATA: NoBetReasonMeta(
        code=NoBetReason.INSUFFICIENT_PREMATCH_DATA.value,
        source_stage=NoBetSourceStage.SCORING_ENGINE,
        severity=NoBetSeverity.BLOCKING,
        clearable=True,
        user_facing_description="Prematch data is insufficient for an official recommendation.",
    ),
    NoBetReason.INVALID_PREDICTION_STATE: NoBetReasonMeta(
        code=NoBetReason.INVALID_PREDICTION_STATE.value,
        source_stage=NoBetSourceStage.FINAL_POST_ENRICHMENT,
        severity=NoBetSeverity.BLOCKING,
        clearable=True,
        user_facing_description="Prediction state is invalid or inconsistent.",
    ),
    NoBetReason.PROVIDER_DATA_INVALID: NoBetReasonMeta(
        code=NoBetReason.PROVIDER_DATA_INVALID.value,
        source_stage=NoBetSourceStage.ODDS_GATE,
        severity=NoBetSeverity.BLOCKING,
        clearable=True,
        user_facing_description="Provider data failed validation.",
    ),
    NoBetReason.FIXTURE_ALREADY_STARTED: NoBetReasonMeta(
        code=NoBetReason.FIXTURE_ALREADY_STARTED.value,
        source_stage=NoBetSourceStage.SCORING_ENGINE,
        severity=NoBetSeverity.BLOCKING,
        clearable=True,
        user_facing_description="Fixture has already started — prematch prediction blocked.",
    ),
    NoBetReason.MANUAL_BLOCK: NoBetReasonMeta(
        code=NoBetReason.MANUAL_BLOCK.value,
        source_stage=NoBetSourceStage.MANUAL,
        severity=NoBetSeverity.BLOCKING,
        clearable=False,
        user_facing_description="Manually blocked — does not clear automatically.",
    ),
    NoBetReason.LEGACY_UNKNOWN_REASON: NoBetReasonMeta(
        code=NoBetReason.LEGACY_UNKNOWN_REASON.value,
        source_stage=NoBetSourceStage.LEGACY,
        severity=NoBetSeverity.BLOCKING,
        clearable=False,
        user_facing_description="Legacy no_bet with no traceable reason — remains blocked until investigated.",
    ),
}

# Canonical serialization order (deterministic).
REASON_SERIALIZATION_ORDER: Final[tuple[NoBetReason, ...]] = tuple(REASON_META.keys())

# Map historical WDE / scoring string reasons → canonical codes.
LEGACY_REASON_ALIASES: Final[dict[str, NoBetReason]] = {
    "confidence_below_60": NoBetReason.CONFIDENCE_BELOW_60,
    "data_quality_below_50": NoBetReason.WDE_DATA_QUALITY_BELOW_50,
    "placeholder_data": NoBetReason.PLACEHOLDER_DATA,
    "confidence_level_low": NoBetReason.CONFIDENCE_BELOW_60,
    "confidence_level_unavailable": NoBetReason.CONFIDENCE_BELOW_60,
    "stale_odds": NoBetReason.STALE_ODDS,
    "incomplete_odds": NoBetReason.INCOMPLETE_ODDS,
    "missing_odds": NoBetReason.MISSING_ODDS,
    "manual_block": NoBetReason.MANUAL_BLOCK,
    "unsupported_fixture": NoBetReason.UNSUPPORTED_FIXTURE,
    "unsupported_market": NoBetReason.UNSUPPORTED_MARKET,
    NoBetReason.CONFIDENCE_BELOW_60.value: NoBetReason.CONFIDENCE_BELOW_60,
    NoBetReason.WDE_DATA_QUALITY_BELOW_50.value: NoBetReason.WDE_DATA_QUALITY_BELOW_50,
    NoBetReason.VISIBILITY_DATA_QUALITY_BELOW_45.value: NoBetReason.VISIBILITY_DATA_QUALITY_BELOW_45,
    NoBetReason.SCORING_DATA_QUALITY_BELOW_45.value: NoBetReason.SCORING_DATA_QUALITY_BELOW_45,
    NoBetReason.PLACEHOLDER_DATA.value: NoBetReason.PLACEHOLDER_DATA,
    NoBetReason.STALE_ODDS.value: NoBetReason.STALE_ODDS,
    NoBetReason.INCOMPLETE_ODDS.value: NoBetReason.INCOMPLETE_ODDS,
    NoBetReason.MISSING_ODDS.value: NoBetReason.MISSING_ODDS,
    NoBetReason.UNSUPPORTED_FIXTURE.value: NoBetReason.UNSUPPORTED_FIXTURE,
    NoBetReason.UNSUPPORTED_MARKET.value: NoBetReason.UNSUPPORTED_MARKET,
    NoBetReason.MODEL_CONFLICT.value: NoBetReason.MODEL_CONFLICT,
    NoBetReason.WDE_ECSE_CONFLICT.value: NoBetReason.WDE_ECSE_CONFLICT,
    NoBetReason.HIGH_CONFLICT.value: NoBetReason.HIGH_CONFLICT,
    NoBetReason.INSUFFICIENT_PREMATCH_DATA.value: NoBetReason.INSUFFICIENT_PREMATCH_DATA,
    NoBetReason.INVALID_PREDICTION_STATE.value: NoBetReason.INVALID_PREDICTION_STATE,
    NoBetReason.PROVIDER_DATA_INVALID.value: NoBetReason.PROVIDER_DATA_INVALID,
    NoBetReason.FIXTURE_ALREADY_STARTED.value: NoBetReason.FIXTURE_ALREADY_STARTED,
    NoBetReason.MANUAL_BLOCK.value: NoBetReason.MANUAL_BLOCK,
    NoBetReason.LEGACY_UNKNOWN_REASON.value: NoBetReason.LEGACY_UNKNOWN_REASON,
}


def normalize_reason_code(raw: str | NoBetReason | None) -> NoBetReason | None:
    """Map a raw reason string to a canonical enum; unknown → LEGACY_UNKNOWN_REASON."""
    if raw is None:
        return None
    if isinstance(raw, NoBetReason):
        return raw
    text = str(raw).strip()
    if not text:
        return None
    if text in LEGACY_REASON_ALIASES:
        return LEGACY_REASON_ALIASES[text]
    # Tolerate prefixed legacy forms like data_quality_below_50
    lowered = text.lower()
    if lowered in LEGACY_REASON_ALIASES:
        return LEGACY_REASON_ALIASES[lowered]
    if "confidence_below" in lowered:
        return NoBetReason.CONFIDENCE_BELOW_60
    if "data_quality_below_50" in lowered or lowered.startswith("data_quality_below_5"):
        return NoBetReason.WDE_DATA_QUALITY_BELOW_50
    if "data_quality_below_45" in lowered:
        return NoBetReason.VISIBILITY_DATA_QUALITY_BELOW_45
    if "placeholder" in lowered:
        return NoBetReason.PLACEHOLDER_DATA
    if "stale_odds" in lowered or lowered == "stale":
        return NoBetReason.STALE_ODDS
    if "incomplete_odds" in lowered:
        return NoBetReason.INCOMPLETE_ODDS
    if "missing_odds" in lowered:
        return NoBetReason.MISSING_ODDS
    if "manual" in lowered:
        return NoBetReason.MANUAL_BLOCK
    return NoBetReason.LEGACY_UNKNOWN_REASON


def ordered_reason_codes(reasons: list[NoBetReason] | set[NoBetReason]) -> list[str]:
    """Deterministic serialization order for reason codes."""
    present = set(reasons)
    return [r.value for r in REASON_SERIALIZATION_ORDER if r in present]
