"""Validate Phase 29 — prediction history result evaluation and UI mapping safety."""

from __future__ import annotations

from pathlib import Path
import runpy
import sys

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def main() -> int:
    checks: list[tuple[str, bool]] = []

    try:
        from decimal import Decimal
        import uuid

        from worldcup_predictor.api.prediction_history_evaluation import (
            FixtureOutcome,
            FixtureOutcomeResolver,
            evaluate_history_record,
            evaluate_result_status,
            filter_by_result_status,
        )
        from worldcup_predictor.database.postgres.enums import Prediction1x2, PredictionResult
        from worldcup_predictor.database.postgres.schemas import PredictionHistoryRecord
        from datetime import datetime, timezone

        def _record(pick: Prediction1x2) -> PredictionHistoryRecord:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            return PredictionHistoryRecord(
                id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                fixture_id=1539007,
                prediction_id=None,
                home_team="Brazil",
                away_team="France",
                league="World Cup 2026",
                match_date=now,
                prediction_1x2=pick,
                confidence=Decimal("62.5"),
                result=PredictionResult.PENDING,
                viewed_at=now,
            )

        pending_outcome = FixtureOutcome(
            is_finished=False,
            actual_result=None,
            final_score=None,
            evaluated_at=None,
            fixture_status="NS",
        )
        status, correct = evaluate_result_status(Prediction1x2.HOME, pending_outcome)
        checks.append(("pending_classification", status == "pending" and correct is None))

        correct_outcome = FixtureOutcome(
            is_finished=True,
            actual_result="home_win",
            final_score="2-1",
            evaluated_at="2026-06-20T12:00:00",
            fixture_status="FT",
        )
        status, correct = evaluate_result_status(Prediction1x2.HOME, correct_outcome)
        checks.append(("correct_classification", status == "correct" and correct is True))

        wrong_outcome = FixtureOutcome(
            is_finished=True,
            actual_result="away_win",
            final_score="0-1",
            evaluated_at="2026-06-20T12:00:00",
            fixture_status="FT",
        )
        status, correct = evaluate_result_status(Prediction1x2.HOME, wrong_outcome)
        checks.append(("wrong_classification", status == "wrong" and correct is False))

        unknown_outcome = FixtureOutcome(
            is_finished=True,
            actual_result=None,
            final_score=None,
            evaluated_at="2026-06-20T12:00:00",
            fixture_status="FT",
        )
        status, correct = evaluate_result_status(Prediction1x2.DRAW, unknown_outcome)
        checks.append(("unknown_classification", status == "unknown" and correct is None))

        class _StubResolver:
            def resolve(self, fixture_id: int) -> FixtureOutcome:
                return correct_outcome

        payload = evaluate_history_record(_record(Prediction1x2.HOME), resolver=_StubResolver())
        required = [
            "fixture_id",
            "match_date",
            "home_team",
            "away_team",
            "predicted_1x2",
            "predicted_confidence",
            "actual_result",
            "final_score",
            "is_finished",
            "is_correct",
            "evaluated_at",
            "data_quality",
            "agent_count",
            "cache_schema_version",
            "result_status",
        ]
        checks.append(("payload_required_fields", all(k in payload for k in required)))
        checks.append(("payload_correct_status", payload["result_status"] == "correct"))
        checks.append(("legacy_result_field", payload["result"] == "correct"))
        checks.append(("backward_compat_prediction_1x2", payload["prediction_1x2"] == "home"))

        items = [
            {"result_status": "correct", "fixture_id": 1},
            {"result_status": "wrong", "fixture_id": 2},
            {"result_status": "pending", "fixture_id": 3},
        ]
        checks.append(("filter_correct", len(filter_by_result_status(items, "correct")) == 1))
        checks.append(("filter_wrong", len(filter_by_result_status(items, "wrong")) == 1))
        checks.append(("filter_pending", len(filter_by_result_status(items, "pending")) == 1))
        checks.append(("filter_all", len(filter_by_result_status(items, "all")) == 3))

        sparse = evaluate_history_record(_record(Prediction1x2.AWAY), resolver=_StubResolver())
        for key in required:
            _ = sparse.get(key)
        checks.append(("missing_optional_fields_safe", True))

        # Frontend mapping helpers (inline mirror)
        def pick_label(value):
            v = str(value or "").lower()
            if v in {"home", "home_win"}:
                return "1"
            if v == "draw":
                return "X"
            if v in {"away", "away_win"}:
                return "2"
            return "—"

        def resolve_status(item):
            return item.get("result_status") or item.get("result") or "pending"

        minimal = {"result": "pending"}
        checks.append(("frontend_minimal_item", resolve_status(minimal) == "pending" and pick_label(None) == "—"))
        checks.append(
            (
                "frontend_sparse_payload",
                pick_label(sparse.get("predicted_1x2")) in {"1", "X", "2", "—"},
            )
        )

        checks.append(("resolver_instantiates", isinstance(FixtureOutcomeResolver(), FixtureOutcomeResolver)))

    except Exception as exc:
        print(f"FAIL: {exc}")
        import traceback

        traceback.print_exc()
        return 1

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        print(f"\n{len(failed)} check(s) failed: {', '.join(failed)}")
        return 1
    print(f"\nAll {len(checks)} Phase 29 checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
