#!/usr/bin/env python3
"""Phase 63A — restore missing Settings fields on production (config drift only)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "worldcup_predictor" / "config" / "settings.py"

MARKER_AFTER = '        alias="AUTONOMOUS_DRY_RUN",\n    )\n'
INSERT_BLOCK = """
    # Phase 61 — unified hybrid prediction engine (orchestration only; specialists unchanged)
    unified_engine_enabled: bool = Field(
        default=False,
        alias="UNIFIED_ENGINE_ENABLED",
    )
    unified_engine_admin_preview: bool = Field(
        default=True,
        alias="UNIFIED_ENGINE_ADMIN_PREVIEW",
    )
    unified_engine_public: bool = Field(
        default=False,
        alias="UNIFIED_ENGINE_PUBLIC",
    )
    unified_engine_compare_mode: bool = Field(
        default=True,
        alias="UNIFIED_ENGINE_COMPARE_MODE",
    )

    # Phase A23 — prediction lifecycle & knowledge database (storage only)
    prediction_lifecycle_enabled: bool = Field(
        default=True,
        alias="PREDICTION_LIFECYCLE_ENABLED",
    )
    prediction_lifecycle_eval_limit: int = Field(
        default=100,
        alias="PREDICTION_LIFECYCLE_EVAL_LIMIT",
    )

"""


def apply(*, dry_run: bool = False) -> dict[str, str]:
    text = SETTINGS.read_text(encoding="utf-8")
    if "UNIFIED_ENGINE_PUBLIC" in text and "PREDICTION_LIFECYCLE_ENABLED" in text:
        return {"status": "already_synced", "path": str(SETTINGS)}

    if MARKER_AFTER not in text:
        raise SystemExit(f"Anchor not found in {SETTINGS}")

    updated = text.replace(MARKER_AFTER, MARKER_AFTER + INSERT_BLOCK, 1)
    if dry_run:
        return {"status": "would_patch", "path": str(SETTINGS)}

    SETTINGS.write_text(updated, encoding="utf-8")
    return {"status": "patched", "path": str(SETTINGS)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = apply(dry_run=args.dry_run)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
