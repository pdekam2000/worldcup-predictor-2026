#!/usr/bin/env python3
"""Test OddAlerts dashboard probability range validation (owner/internal)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.data_import.oddalerts_csv_request import (  # noqa: E402
    RANGE_TEST_PATH,
    run_probability_range_ui_test,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Test OddAlerts dashboard probability range UI")
    parser.add_argument("--test-probability-range", action="store_true", required=True)
    parser.add_argument("--headed", action="store_true", help="Run browser headed (required for login)")
    parser.add_argument("--pause-for-login", action="store_true", help="Pause for owner login/captcha")
    args = parser.parse_args()

    result = run_probability_range_ui_test(headed=args.headed, pause_for_login=args.pause_for_login)
    RANGE_TEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    RANGE_TEST_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({k: result[k] for k in result if k not in ("tests_run",)}, indent=2, ensure_ascii=False))
    print(f"Written: {RANGE_TEST_PATH}")
    if result.get("error"):
        print(f"Note: {result['error']}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
