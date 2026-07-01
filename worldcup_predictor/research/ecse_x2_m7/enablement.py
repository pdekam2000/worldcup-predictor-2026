"""PHASE ECSE-X2-M7 — Flag enablement and service restart helpers."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.ecse_x2_m7.constants import ENABLEMENT_PROOF, ENV_SNIPPET


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def enable_shadow_live_flag() -> dict[str, Any]:
    os.environ["ECSE_X2_M6_SHADOW_LIVE_ENABLED"] = "1"
    root = _repo_root()

    snippet_path = root / ENV_SNIPPET
    snippet_path.parent.mkdir(parents=True, exist_ok=True)
    snippet = (
        "# ECSE-X2-M7 controlled enablement — append to production .env\n"
        "ECSE_X2_M6_SHADOW_LIVE_ENABLED=1\n"
        "# ECSE-LIVE must also be enabled for snapshot hook to fire:\n"
        "# ECSE_LIVE_ENABLED=1\n"
    )
    snippet_path.write_text(snippet, encoding="utf-8")

    proof = {
        "enabled_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "ECSE_X2_M6_SHADOW_LIVE_ENABLED": os.environ.get("ECSE_X2_M6_SHADOW_LIVE_ENABLED"),
        "env_snippet": str(snippet_path.relative_to(root)).replace("\\", "/"),
        "restart_command": "sudo systemctl restart worldcup-api",
        "rollback_command": (
            "Set ECSE_X2_M6_SHADOW_LIVE_ENABLED=0 in production .env; "
            "sudo systemctl restart worldcup-api"
        ),
    }

    proof_path = root / ENABLEMENT_PROOF
    proof_path.parent.mkdir(parents=True, exist_ok=True)
    proof_path.write_text(json.dumps(proof, indent=2), encoding="utf-8")
    return proof


def attempt_service_restart() -> dict[str, Any]:
    result: dict[str, Any] = {"attempted": True, "success": False}
    try:
        proc = subprocess.run(
            ["sudo", "systemctl", "restart", "worldcup-api"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        result["exit_code"] = proc.returncode
        result["stdout"] = (proc.stdout or "").strip()[:500]
        result["stderr"] = (proc.stderr or "").strip()[:500]
        result["success"] = proc.returncode == 0
    except FileNotFoundError:
        result["note"] = "systemctl not available on this host (local/dev); flag set in process env only"
        result["attempted"] = False
    except subprocess.TimeoutExpired:
        result["note"] = "systemctl restart timed out"
    return result


def verify_flag_active() -> bool:
    from worldcup_predictor.config.settings import get_settings

    get_settings.cache_clear()
    return bool(get_settings().ecse_x2_m6_shadow_live_enabled)
