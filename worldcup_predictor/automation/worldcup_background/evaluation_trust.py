"""Phase 45B — quarantine bogus/test evaluation rows from public metrics."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcomeResolver
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository

logger = logging.getLogger(__name__)

_KNOWN_TEST_FIXTURES = frozenset({1489393, 1539007})
_TEST_SOURCES = frozenset({"phase35_test", "phase33_test", "test_validation"})


@dataclass
class QuarantinePassResult:
    scanned: int = 0
    quarantined: int = 0
    already_quarantined: int = 0
    details: list[dict[str, Any]] = field(default_factory=list)


def _parse_payload(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row or not row.get("payload_json"):
        return {}
    try:
        data = json.loads(row["payload_json"])
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def detect_quarantine_reason(
    evaluation: dict[str, Any],
    *,
    stored_row: dict[str, Any] | None,
    fixture_row: dict[str, Any] | None,
    outcome_finished: bool,
) -> str | None:
    """Return quarantine reason or None if row appears authoritative."""
    fixture_id = int(evaluation.get("fixture_id") or 0)
    if fixture_id in _KNOWN_TEST_FIXTURES:
        return "known_validation_fixture"

    stored_source = str((stored_row or {}).get("source") or "").strip().lower()
    if stored_source in _TEST_SOURCES or "test" in stored_source:
        return f"stored_source={stored_source}"

    eval_source = str(evaluation.get("evaluation_source") or "").strip().lower()
    if eval_source in _TEST_SOURCES or eval_source == "test_validation":
        return f"evaluation_source={eval_source}"

    payload = _parse_payload(stored_row)
    home = str(payload.get("home_team") or "").strip()
    away = str(payload.get("away_team") or "").strip()
    if home.lower() == "home" and away.lower() == "away":
        return "placeholder_team_names"

    fixture_status = str((fixture_row or {}).get("status") or "").strip().upper()
    overall = str(evaluation.get("overall_status") or "").lower()
    if overall in {"correct", "wrong"} and not outcome_finished:
        if fixture_status in {"", "NS", "TBD", "PST"}:
            return "evaluated_before_fixture_finished"

    return None


def run_evaluation_quarantine_pass(
    *,
    settings: Settings | None = None,
    competition_key: str = "world_cup_2026",
) -> QuarantinePassResult:
    """Mark bogus evaluation rows as quarantined (no hard delete)."""
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    resolver = FixtureOutcomeResolver(settings)
    result = QuarantinePassResult()

    rows = repo.list_worldcup_prediction_evaluations(
        competition_key=competition_key,
        include_quarantined=True,
    )
    result.scanned = len(rows)

    for ev in rows:
        fixture_id = int(ev["fixture_id"])
        if bool(ev.get("is_quarantined")):
            result.already_quarantined += 1
            continue

        stored = repo.get_worldcup_stored_prediction(fixture_id)
        fixture = repo.get_fixture_row(fixture_id)
        outcome = resolver.resolve(fixture_id)
        reason = detect_quarantine_reason(
            ev,
            stored_row=stored,
            fixture_row=fixture,
            outcome_finished=outcome.is_finished,
        )
        if not reason:
            continue

        repo.set_evaluation_quarantine(
            fixture_id,
            quarantined=True,
            evaluation_source="test_validation",
            quarantine_reason=reason,
        )
        result.quarantined += 1
        result.details.append({"fixture_id": fixture_id, "reason": reason})
        logger.info("Quarantined evaluation fixture_id=%s reason=%s", fixture_id, reason)

    return result
