"""Settle live Rule A validation records from finished match results only."""

from __future__ import annotations

from datetime import datetime, timezone

from worldcup_predictor.prediction.rule_a_gate.live_validation_store import LiveValidationStore
from worldcup_predictor.results.match_results_store import MatchResultsStore


def settle_live_records(
    store: LiveValidationStore | None = None,
) -> tuple[int, int]:
    """
    Mark unsettled records when a finished result exists in match_results.jsonl.
    Returns (newly_settled_count, total_settled_count).
    """
    target = store or LiveValidationStore()
    records = target.latest_by_fixture()
    if not records:
        return 0, 0

    results = MatchResultsStore().by_fixture_id()
    newly = 0
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    for fid, rec in records.items():
        if rec.settled:
            continue
        result = results.get(fid)
        if result is None:
            continue
        rec.actual_result = result.winner
        rec.settled = True
        rec.settled_timestamp = now
        newly += 1

    if newly:
        target.write_consolidated(records)

    settled_total = sum(1 for r in records.values() if r.settled)
    return newly, settled_total
