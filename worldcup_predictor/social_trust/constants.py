"""Social trust constants — Phase A20."""

from __future__ import annotations

SHARE_TYPES = ("pick", "combo", "paper_report", "betting_plan")

BLOCKED_PAYLOAD_KEYS = frozenset({
    "user_id",
    "user_email",
    "email",
    "password",
    "token",
    "internal",
    "debug",
    "owner",
    "shadow",
    "wde_weights",
    "factor_weights",
    "calibration_internals",
    "snapshot_id",
    "predops_snapshot",
    "agent_internals",
    "billing",
    "subscription",
    "stripe",
    "api_key",
})

DISCLAIMER = (
    "For analysis and entertainment only. Past performance does not guarantee future results."
)

OG_IMAGE_DEFAULT = "/og-image.png"
