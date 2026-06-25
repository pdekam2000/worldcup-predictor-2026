#!/usr/bin/env python3
"""Phase 54K — Goalscorer Shadow Engine V1 (research only)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54k_goalscorer_shadow"


def main() -> int:
    from worldcup_predictor.egie.goalscorer_shadow.backtest import run_backtest
    from worldcup_predictor.egie.goalscorer_shadow.calibration import apply_calibration, calibration_summary
    from worldcup_predictor.egie.goalscorer_shadow.dataset_builder import GoalscorerDatasetBuilder
    from worldcup_predictor.egie.goalscorer_shadow.scoring import apply_baseline_scores
    from worldcup_predictor.egie.goalscorer_shadow.validation import align_odds_with_model

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    builder = GoalscorerDatasetBuilder(artifact_dir=ARTIFACT_DIR)
    eligible, unusable, summary = builder.build()
    paths = builder.export(eligible, unusable, summary)

    scored = apply_baseline_scores(eligible)
    calibrated = apply_calibration(scored)
    calibrated.to_parquet(ARTIFACT_DIR / "goalscorer_scored_dataset.parquet", index=False)

    report = run_backtest(eligible)
    report.odds_alignment = align_odds_with_model(scored)
    report_dict = report.to_dict()
    report_dict["calibration"] = calibration_summary(calibrated)

    (ARTIFACT_DIR / "backtest_report.json").write_text(
        json.dumps(report_dict, indent=2, default=str), encoding="utf-8"
    )

    print(json.dumps({
        "dataset": paths,
        "summary": summary.to_dict(),
        "recommendation": report.recommendation,
        "anytime_combined_top3": next(
            (m.to_dict() for m in report.anytime if m.model == "combined_baseline"), {}
        ),
    }, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
