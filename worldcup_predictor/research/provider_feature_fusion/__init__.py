"""Paid provider feature fusion shadow research package."""

from worldcup_predictor.research.provider_feature_fusion.ablation import build_ablation_report
from worldcup_predictor.research.provider_feature_fusion.coverage_audit import audit_coverage
from worldcup_predictor.research.provider_feature_fusion.dataset_builder import build_shadow_dataset
from worldcup_predictor.research.provider_feature_fusion.experiments import run_fusion_experiments
from worldcup_predictor.research.provider_feature_fusion.importance import compute_feature_importance

__all__ = [
    "audit_coverage",
    "build_shadow_dataset",
    "run_fusion_experiments",
    "build_ablation_report",
    "compute_feature_importance",
]
