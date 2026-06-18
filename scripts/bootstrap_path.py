"""Add repository root to sys.path for scripts run as ``python scripts/<name>.py``."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def ensure_project_root() -> Path:
    """Insert project root on sys.path if missing (idempotent)."""
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    return PROJECT_ROOT


ensure_project_root()
