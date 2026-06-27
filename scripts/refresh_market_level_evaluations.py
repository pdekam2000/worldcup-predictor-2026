#!/usr/bin/env python3
"""One-time refresh — attach market_evaluations to finished prediction evaluations (detail_json only)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.api.archive_evaluation_join import is_quarantined_evaluation
from worldcup_predictor.api.market_level_evaluation import limited_historical_payload
from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcomeResolver
from worldcup_predictor.automation.worldcup_background.pick_evaluator import evaluate_stored_prediction
from worldcup_predictor.automation.worldcup_background.result_evaluation_job import (
    _evaluation_unchanged,
    _existing_evaluation,
    _load_stored_payload,
)
from worldcup_predictor.automation.worldcup_background.prediction_store import WorldcupPredictionStore
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository


def _parse_detail(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def scan_and_refresh(*, dry_run: bool, limit: int | None, competition_key: str) -> dict[str, int]:
    settings = get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    store = WorldcupPredictionStore(settings)
    resolver = FixtureOutcomeResolver(settings)

    counts = {
        "scanned": 0,
        "updated": 0,
        "skipped_pending": 0,
        "skipped_no_payload": 0,
        "limited_historical_payload": 0,
        "skipped_quarantined": 0,
        "skipped_unchanged": 0,
        "errors": 0,
    }

    try:
        rows = repo.list_worldcup_stored_prediction_rows(competition_key=competition_key)
        if limit is not None:
            rows = rows[: max(0, int(limit))]

        for row in rows:
            counts["scanned"] += 1
            fixture_id = int(row["fixture_id"])
            existing = _existing_evaluation(repo, fixture_id)
            if is_quarantined_evaluation(existing):
                counts["skipped_quarantined"] += 1
                continue

            stored = _load_stored_payload(fixture_id, store=store, repo=repo, stored_row=row)
            if stored is None:
                counts["skipped_no_payload"] += 1
                continue

            if limited_historical_payload(stored):
                counts["limited_historical_payload"] += 1

            outcome = resolver.resolve(fixture_id)
            if not outcome.is_finished:
                counts["skipped_pending"] += 1
                continue

            try:
                evaluation = evaluate_stored_prediction(stored, outcome)
                eval_status = str(evaluation.get("status") or "pending")
                if dry_run:
                    detail = _parse_detail((existing or {}).get("detail_json"))
                    has_market_eval = bool(detail.get("market_evaluations"))
                    unchanged = _evaluation_unchanged(
                        existing,
                        outcome_final_score=outcome.final_score,
                        evaluation_status=eval_status,
                    )
                    if unchanged and has_market_eval:
                        counts["skipped_unchanged"] += 1
                    else:
                        counts["updated"] += 1
                else:
                    if _evaluation_unchanged(
                        existing,
                        outcome_final_score=outcome.final_score,
                        evaluation_status=eval_status,
                    ):
                        detail = _parse_detail((existing or {}).get("detail_json"))
                        if detail.get("market_evaluations"):
                            counts["skipped_unchanged"] += 1
                            continue
                    repo.upsert_worldcup_prediction_evaluation(
                        fixture_id=fixture_id,
                        evaluation=evaluation,
                        outcome={
                            "actual_result": outcome.actual_result,
                            "final_score": outcome.final_score,
                            "is_finished": outcome.is_finished,
                        },
                    )
                    counts["updated"] += 1
            except Exception as exc:
                counts["errors"] += 1
                print(f"ERROR fixture_id={fixture_id}: {exc}", file=sys.stderr)
    finally:
        repo.close()
        store._repo.close()

    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh market-level evaluation detail_json")
    parser.add_argument("--dry-run", action="store_true", help="Scan only; do not write")
    parser.add_argument("--limit", type=int, default=None, help="Max fixtures to scan")
    parser.add_argument("--competition", default="world_cup_2026", help="Competition key")
    args = parser.parse_args()

    counts = scan_and_refresh(dry_run=args.dry_run, limit=args.limit, competition_key=args.competition)
    mode = "DRY_RUN" if args.dry_run else "APPLY"
    print(f"REFRESH_{mode}: {json.dumps(counts, sort_keys=True)}")
    return 0 if counts["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
