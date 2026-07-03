#!/usr/bin/env python3
"""Print project/git version for local and production ops checks."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.app_version import build_version_payload  # noqa: E402


def _git_rev(full: bool = False) -> str | None:
    flag = "HEAD" if full else "--short"
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", flag],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
        )
        return out.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def main() -> int:
    payload = build_version_payload()
    payload["git_short"] = _git_rev(full=False)
    payload["git_full"] = _git_rev(full=True)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
