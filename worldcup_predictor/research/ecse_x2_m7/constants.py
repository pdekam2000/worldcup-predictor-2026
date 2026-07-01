"""PHASE ECSE-X2-M7 — Controlled enablement constants."""

from __future__ import annotations

PHASE = "ECSE-X2-M7"
METHOD_VERSION = "ECSE-X2-M7-v1"
BACKUP_ROOT = "artifacts/ecse_x2_m7_backups"
BEFORE_SNAPSHOT = "artifacts/ecse_x2_m7_before_enable_public_output_snapshot.json"
AFTER_SNAPSHOT = "artifacts/ecse_x2_m7_after_enable_public_output_snapshot.json"
ENABLEMENT_PROOF = "artifacts/ecse_x2_m7_enablement_proof.json"
WATCH_SUMMARY = "artifacts/ecse_x2_m7_live_watch_summary.json"
ENV_SNIPPET = "deployment/ecse_x2_m7_enablement_snippet.env"

RECOMMENDATIONS = (
    "SHADOW_LIVE_COLLECTING",
    "NEED_MORE_LIVE_EVALUATIONS",
    "DISABLE_FLAG_SAFETY_RISK",
    "READY_FOR_ADMIN_UI_REVIEW",
    "READY_FOR_PUBLIC_PROMOTION_REVIEW",
)
