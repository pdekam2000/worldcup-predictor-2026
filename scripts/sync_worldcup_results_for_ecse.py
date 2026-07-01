#!/usr/bin/env python3
"""Backward-compatible wrapper — delegates to sync_ecse_snapshot_results."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        ids = [x for x in sys.argv[1:] if x.isdigit()]
        sys.argv = [str(ROOT / "scripts" / "sync_ecse_snapshot_results.py"), "--fixture-ids", *ids]
    else:
        sys.argv[0] = str(ROOT / "scripts" / "sync_ecse_snapshot_results.py")
    runpy.run_path(str(ROOT / "scripts" / "sync_ecse_snapshot_results.py"), run_name="__main__")
