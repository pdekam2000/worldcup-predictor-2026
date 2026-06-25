"""Phase 54F-3 — Sportmonks historical xG discovery (audit only)."""

from worldcup_predictor.feature_store.xg_discovery.discovery_engine import XgDiscoveryEngine
from worldcup_predictor.feature_store.xg_discovery.coverage_matrix import build_coverage_matrix

__all__ = ["XgDiscoveryEngine", "build_coverage_matrix"]
