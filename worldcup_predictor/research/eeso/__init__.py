"""EESO — Exact Score Enhancement Shadow Optimization (research only)."""

from worldcup_predictor.research.eeso.constants import PHASE, SHADOW_ONLY, PUBLIC_PUBLISH
from worldcup_predictor.research.eeso.runner import run_eeso_shadow_research

__all__ = ["PHASE", "SHADOW_ONLY", "PUBLIC_PUBLISH", "run_eeso_shadow_research"]
