#!/usr/bin/env python3
"""Sync app_version.manifest.json to frontend constants and public build metadata."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "app_version.manifest.json"
FRONTEND_JS = ROOT / "base44-d" / "src" / "lib" / "appVersion.js"
PUBLIC_JSON = ROOT / "base44-d" / "public" / "build-metadata.json"


def main() -> int:
    if not MANIFEST.is_file():
        print(f"Missing manifest: {MANIFEST}", file=sys.stderr)
        return 1

    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for key in ("app_version", "build_label", "build_date", "commit"):
        if not data.get(key):
            print(f"Manifest missing {key}", file=sys.stderr)
            return 1

    public_payload = {
        "app_version": data["app_version"],
        "build_label": data["build_label"],
        "build_date": data["build_date"],
        "commit": data["commit"],
        "frontend_version": data["app_version"],
    }
    PUBLIC_JSON.write_text(json.dumps(public_payload, indent=2) + "\n", encoding="utf-8")

    js = FRONTEND_JS.read_text(encoding="utf-8")
    replacements = {
        "APP_VERSION": data["app_version"],
        "BUILD_LABEL": data["build_label"],
        "BUILD_DATE": data["build_date"],
        "COMMIT_HASH": data["commit"],
    }
    for const, value in replacements.items():
        js, count = re.subn(
            rf'export const {const} = "[^"]*";',
            f'export const {const} = "{value}";',
            js,
            count=1,
        )
        if count != 1:
            print(f"Failed to update {const} in appVersion.js", file=sys.stderr)
            return 1

    FRONTEND_JS.write_text(js, encoding="utf-8")
    print(f"Synced version {data['app_version']} ({data['build_label']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
