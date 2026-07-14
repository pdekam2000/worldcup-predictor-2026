"""Canonical final-result record types and hashing for forward evaluation."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from worldcup_predictor.forward_evaluation.hashing import canonical_json

RESULT_QUALITY_CONFIRMED_REGULATION = "CONFIRMED_REGULATION_RESULT"
RESULT_QUALITY_CONFIRMED_AET = "CONFIRMED_AFTER_EXTRA_TIME_WITH_REGULATION_AVAILABLE"
RESULT_QUALITY_CONFIRMED_PEN = "CONFIRMED_PENALTIES_WITH_REGULATION_AVAILABLE"
RESULT_QUALITY_INCOMPLETE = "TERMINAL_SCORE_INCOMPLETE"
RESULT_QUALITY_CONFLICT = "PROVIDER_CONFLICT"
RESULT_QUALITY_NOT_AVAILABLE = "RESULT_NOT_AVAILABLE"
RESULT_QUALITY_NOT_TERMINAL = "STATUS_NOT_TERMINAL"
RESULT_QUALITY_ABANDONED = "ABANDONED"
RESULT_QUALITY_POSTPONED = "POSTPONED"
RESULT_QUALITY_CANCELLED = "CANCELLED"
RESULT_QUALITY_MANUAL_REVIEW = "MANUAL_REVIEW_REQUIRED"

CONFIRMED_RESULT_QUALITIES = frozenset(
    {
        RESULT_QUALITY_CONFIRMED_REGULATION,
        RESULT_QUALITY_CONFIRMED_AET,
        RESULT_QUALITY_CONFIRMED_PEN,
    }
)

ELIGIBILITY_PUBLIC = "PUBLIC_ELIGIBLE"
ELIGIBILITY_OWNER_ONLY = "OWNER_ONLY"
ELIGIBILITY_QUARANTINED = "QUARANTINED"
ELIGIBILITY_INVALID_FREEZE = "INVALID_FREEZE"
ELIGIBILITY_INVALID_RESULT = "INVALID_RESULT"
ELIGIBILITY_TEST_ONLY = "TEST_ONLY"

EVALUATION_VERSION = "FORWARD-EVAL-v1"


def result_content_hash(
    *,
    fixture_id: int,
    regulation_home: int,
    regulation_away: int,
    final_stage: str | None,
    provider: str | None,
) -> str:
    material = {
        "fixture_id": int(fixture_id),
        "regulation_home_goals": int(regulation_home),
        "regulation_away_goals": int(regulation_away),
        "final_stage": str(final_stage or "FT"),
        "provider": str(provider or "unknown"),
    }
    return hashlib.sha256(canonical_json(material).encode("utf-8")).hexdigest()


def classify_result_quality(
    *,
    terminal_status: str | None,
    regulation_home: int | None,
    regulation_away: int | None,
    final_stage: str | None,
    conflict: bool = False,
) -> str:
    status = str(terminal_status or "NS").upper()
    if conflict:
        return RESULT_QUALITY_CONFLICT
    if status in {"PST", "POSTPONED"}:
        return RESULT_QUALITY_POSTPONED
    if status in {"CANC", "CANCELLED"}:
        return RESULT_QUALITY_CANCELLED
    if status in {"ABD", "ABANDONED"}:
        return RESULT_QUALITY_ABANDONED
    if regulation_home is None or regulation_away is None:
        if status in {"FT", "AET", "PEN", "FINISHED", "COMPLETED"}:
            return RESULT_QUALITY_INCOMPLETE
        return RESULT_QUALITY_NOT_TERMINAL
    stage = str(final_stage or status or "FT").upper()
    if stage == "AET":
        return RESULT_QUALITY_CONFIRMED_AET
    if stage == "PEN":
        return RESULT_QUALITY_CONFIRMED_PEN
    return RESULT_QUALITY_CONFIRMED_REGULATION


def regulation_result_label(home: int, away: int) -> str:
    if int(home) > int(away):
        return "home_win"
    if int(home) < int(away):
        return "away_win"
    return "draw"


def build_canonical_result_record(
    *,
    fixture_id: int,
    provider_fixture_id: int | None,
    competition: str | None,
    kickoff_utc: str | None,
    terminal_status: str | None,
    regulation_home: int | None,
    regulation_away: int | None,
    halftime_home: int | None = None,
    halftime_away: int | None = None,
    extra_time_home: int | None = None,
    extra_time_away: int | None = None,
    penalty_home: int | None = None,
    penalty_away: int | None = None,
    provider: str | None = None,
    provider_result_timestamp: str | None = None,
    synced_at_utc: str | None = None,
    result_provenance: str | None = None,
    conflict: bool = False,
) -> dict[str, Any]:
    quality = classify_result_quality(
        terminal_status=terminal_status,
        regulation_home=regulation_home,
        regulation_away=regulation_away,
        final_stage=terminal_status,
        conflict=conflict,
    )
    r_hash = None
    if regulation_home is not None and regulation_away is not None:
        r_hash = result_content_hash(
            fixture_id=fixture_id,
            regulation_home=int(regulation_home),
            regulation_away=int(regulation_away),
            final_stage=terminal_status,
            provider=provider,
        )
    return {
        "fixture_id": int(fixture_id),
        "provider_fixture_id": provider_fixture_id,
        "competition": competition,
        "kickoff_utc": kickoff_utc,
        "terminal_status": terminal_status,
        "regulation_home_goals": regulation_home,
        "regulation_away_goals": regulation_away,
        "regulation_result": (
            regulation_result_label(int(regulation_home), int(regulation_away))
            if regulation_home is not None and regulation_away is not None
            else None
        ),
        "halftime_home_goals": halftime_home,
        "halftime_away_goals": halftime_away,
        "extra_time_home_goals": extra_time_home,
        "extra_time_away_goals": extra_time_away,
        "penalty_home_goals": penalty_home,
        "penalty_away_goals": penalty_away,
        "provider": provider,
        "provider_result_timestamp": provider_result_timestamp,
        "synced_at_utc": synced_at_utc,
        "result_quality_status": quality,
        "result_provenance": result_provenance,
        "result_content_hash": r_hash,
        "evaluable": quality in CONFIRMED_RESULT_QUALITIES,
    }
