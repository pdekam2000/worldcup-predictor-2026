#!/usr/bin/env python3
"""Inspect external historical CSV ZIP (no import)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.data_import.external_historical_zip_importer import (  # noqa: E402
    INBOX_DIR,
    PROFILE_PATH,
    inspect_zip,
    write_profile,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect external historical CSV ZIP")
    parser.add_argument(
        "--zip",
        type=Path,
        default=INBOX_DIR / "historical_csv_data.zip",
    )
    args = parser.parse_args()

    if not args.zip.is_file():
        print(json.dumps({"error": f"ZIP not found: {args.zip}"}, indent=2))
        return 2

    profile = inspect_zip(args.zip.resolve())
    write_profile(profile)
    print(json.dumps({k: profile.to_dict()[k] for k in profile.to_dict() if k != "files"}, indent=2, ensure_ascii=False))
    print(f"Written: {PROFILE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
