#!/usr/bin/env python3
"""Phase 36C — safe provider/env diagnostic (never prints secret values)."""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))

from worldcup_predictor.config.provider_readiness import provider_diagnostic
from worldcup_predictor.config.settings import get_settings


def main() -> int:
    get_settings.cache_clear()
    diag = provider_diagnostic()
    print(json.dumps(diag, indent=2))
    return 0 if diag.get("production_prediction_allowed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
