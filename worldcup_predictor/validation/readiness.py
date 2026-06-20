"""Phase 26 — World Cup readiness monitor."""

from __future__ import annotations

from worldcup_predictor.validation.coverage import compute_coverage
from worldcup_predictor.validation.models import RealWorldValidationRecord, WorldCupReadinessScore


def compute_readiness_score(records: list[RealWorldValidationRecord]) -> WorldCupReadinessScore:
    notes: list[str] = []
    if not records:
        return WorldCupReadinessScore(
            score=0.0,
            data_quality=0.0,
            lineup_coverage=0.0,
            context_coverage=0.0,
            xg_coverage=0.0,
            prediction_quality=0.0,
            sample_size=0,
            notes=["No validation records yet — capture begins on next shadow prediction."],
        )

    coverage = compute_coverage(records)
    settled = [r for r in records if r.settled]
    dq_avg = sum(r.data_quality_score for r in records) / len(records)
    dq_component = min(100.0, dq_avg)

    lineup_component = coverage.lineup_coverage * 100
    context_component = coverage.context_coverage * 100
    xg_component = coverage.xg_coverage * 100

    if settled:
        acc = sum(1 for r in settled if r.one_x_two_correct) / len(settled)
        calib = sum(1 for r in settled if r.confidence_calibration_ok) / len(settled)
        pred_component = (acc * 0.65 + calib * 0.35) * 100
    else:
        pred_component = 50.0
        notes.append("Prediction quality uses neutral 50 until settled outcomes exist.")

    weights = {
        "data_quality": 0.25,
        "lineup": 0.20,
        "context": 0.20,
        "xg": 0.15,
        "prediction": 0.20,
    }
    score = (
        dq_component * weights["data_quality"]
        + lineup_component * weights["lineup"]
        + context_component * weights["context"]
        + xg_component * weights["xg"]
        + pred_component * weights["prediction"]
    )
    if len(records) < 20:
        notes.append(f"Sample size {len(records)} — readiness score provisional.")
    if coverage.sportmonks_coverage < 0.2:
        notes.append("Sportmonks coverage low — benchmark layer still sparse.")

    return WorldCupReadinessScore(
        score=round(min(100.0, max(0.0, score)), 1),
        data_quality=round(dq_component, 1),
        lineup_coverage=round(lineup_component, 1),
        context_coverage=round(context_component, 1),
        xg_coverage=round(xg_component, 1),
        prediction_quality=round(pred_component, 1),
        sample_size=len(records),
        notes=notes,
    )
