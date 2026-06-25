#!/usr/bin/env python3
"""Phase 45B post-deploy: quarantine bogus rows and rebuild public summary."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def main() -> int:
    from worldcup_predictor.automation.worldcup_background.accuracy_summary import rebuild_accuracy_summary
    from worldcup_predictor.automation.worldcup_background.evaluation_trust import run_evaluation_quarantine_pass
    from worldcup_predictor.automation.worldcup_background.result_refresh import refresh_stored_prediction_results
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.database.migrations import ensure_schema_compat
    from worldcup_predictor.database.repository import FootballIntelligenceRepository

    settings = get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    ensure_schema_compat(repo._conn)
    repo.close()

    refresh = refresh_stored_prediction_results(settings=settings, dry_run=False)
    quarantine = run_evaluation_quarantine_pass(settings=settings)
    summary = rebuild_accuracy_summary(settings=settings)

    out = {
        "refresh": {
            "scanned": refresh.scanned,
            "fixtures_updated": refresh.fixtures_updated,
            "results_updated": refresh.results_updated,
            "api_fetches": refresh.api_fetches,
            "errors": refresh.errors,
        },
        "quarantine": {
            "scanned": quarantine.scanned,
            "quarantined": quarantine.quarantined,
            "already_quarantined": quarantine.already_quarantined,
            "details": quarantine.details,
        },
        "summary": {
            "evaluated_predictions": summary.get("evaluated_predictions"),
            "correct": summary.get("correct"),
            "wrong": summary.get("wrong"),
            "winrate": summary.get("winrate"),
        },
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
