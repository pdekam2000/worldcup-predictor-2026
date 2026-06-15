"""Apply fusion enrichment to predictions — additive, conservative."""

from __future__ import annotations

import json
from dataclasses import replace

from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.domain.prediction import MatchPrediction
from worldcup_predictor.domain.specialist import MatchSpecialistReport
from worldcup_predictor.fusion.final_decision_fusion_engine_v2 import build_final_decision_fusion


def apply_fusion_enrichment(
    prediction: MatchPrediction,
    *,
    report: MatchIntelligenceReport | None = None,
    specialist_report: MatchSpecialistReport | None = None,
    explainability_report: dict | None = None,
) -> tuple[MatchPrediction, dict]:
    """Attach fusion report and apply capped confidence refinement — never raises."""
    try:
        fusion = build_final_decision_fusion(
            prediction,
            report=report,
            specialist_report=specialist_report,
            explainability_report=explainability_report,
        )
        fusion_dict = fusion.to_dict()
        metadata = dict(prediction.metadata)
        metadata["fusion_report_v2"] = json.dumps(fusion_dict, ensure_ascii=False)
        metadata["fusion_quality_band"] = fusion.decision_quality_band
        metadata["fusion_consensus"] = str(fusion.consensus_strength)

        new_conf = fusion.fusion_prediction.get("confidence_score", prediction.confidence_score)
        try:
            new_conf = float(new_conf)
        except (TypeError, ValueError):
            new_conf = prediction.confidence_score

        updated = replace(
            prediction,
            confidence_score=round(new_conf, 1),
            metadata=metadata,
        )
        return updated, fusion_dict
    except Exception:
        return prediction, {}
