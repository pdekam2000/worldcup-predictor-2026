"""Canonical prematch feature store for owner-scope shadow evaluation."""

from worldcup_predictor.provider_features.backfill_runner import run_pilot_backfill
from worldcup_predictor.provider_features.coverage import measure_coverage
from worldcup_predictor.provider_features.entitlements import verify_entitlements
from worldcup_predictor.provider_features.live_shadow_runner import prepare_live_shadow_runner

__all__ = [
    "verify_entitlements",
    "run_pilot_backfill",
    "measure_coverage",
    "prepare_live_shadow_runner",
]
