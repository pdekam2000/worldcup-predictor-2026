"""Persist Phase 3B forward-generation gate (shadow only)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
POLICY_PATH = ROOT / "artifacts" / "challenger_program" / "phase3b" / "forward_policy.json"


def load_forward_policy() -> dict[str, Any]:
    if not POLICY_PATH.exists():
        return {
            "forward_active": False,
            "reason": "PHASE3B_POLICY_MISSING",
            "pause_gbgm1_new_generation": True,
            "preserve_gbgm1_history": True,
        }
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def should_generate_gbgm1_forward() -> bool:
    """GBGM-1 new forward generation paused when below baseline or superseded by TSBP."""
    pol = load_forward_policy()
    if pol.get("pause_gbgm1_new_generation", True):
        return False
    # Explicit deny unless policy flips pause off (should not happen without redesign)
    return False


def should_generate_tsbp_forward() -> bool:
    pol = load_forward_policy()
    if pol.get("reason") == "OPERATIONAL_INSTABILITY":
        return False
    return bool(pol.get("forward_active", True)) and pol.get("active_model_id", "TSBP-1") == "TSBP-1"


def should_generate_improved_shadow() -> bool:
    return should_generate_tsbp_forward()
