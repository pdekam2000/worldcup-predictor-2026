"""Phase 26 — post-match outcome evaluation."""

from __future__ import annotations

from datetime import datetime, timezone

from worldcup_predictor.validation.contribution import assess_signal_usefulness
from worldcup_predictor.validation.models import RealWorldValidationRecord


def _calibration_ok(confidence: float, correct: bool) -> bool:
    if confidence >= 65:
        return correct
    if confidence < 45:
        return not correct
    return True


def apply_outcome(
    record: RealWorldValidationRecord,
    *,
    actual_1x2: str,
    actual_over_under: str,
) -> RealWorldValidationRecord:
    record.actual_1x2 = actual_1x2
    record.actual_over_under = actual_over_under
    record.one_x_two_correct = record.predicted_1x2 == actual_1x2
    record.over_under_correct = record.predicted_over_under == actual_over_under
    record.confidence_calibration_ok = _calibration_ok(record.confidence, bool(record.one_x_two_correct))
    record.signal_usefulness = assess_signal_usefulness(record)
    record.settled = True
    record.settled_at = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    return record


def settle_records_from_results(
    records: list[RealWorldValidationRecord],
    results_by_fixture: dict[int, Any],
) -> list[RealWorldValidationRecord]:
    updated: list[RealWorldValidationRecord] = []
    for record in records:
        if record.settled:
            updated.append(record)
            continue
        result = results_by_fixture.get(int(record.fixture_id))
        if result is None:
            updated.append(record)
            continue
        winner = getattr(result, "winner", None) or (result.get("winner") if isinstance(result, dict) else None)
        ou = getattr(result, "over_under_2_5_result", None) or (
            result.get("over_under_2_5_result") if isinstance(result, dict) else None
        )
        if not winner or not ou:
            updated.append(record)
            continue
        updated.append(
            apply_outcome(record, actual_1x2=str(winner), actual_over_under=str(ou))
        )
    return updated
