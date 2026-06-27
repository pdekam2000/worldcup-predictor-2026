#!/usr/bin/env python3
"""Hotfix Pack 4 — global app version badge validation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
if runpy_path.is_file():
    import runpy

    runpy.run_path(str(runpy_path))

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "app_version.manifest.json"


def record(checks: list, name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    for rel in (
        "app_version.manifest.json",
        "worldcup_predictor/config/app_version.py",
        "base44-d/src/lib/appVersion.js",
        "base44-d/src/components/layout/AppVersionBadge.jsx",
        "base44-d/public/build-metadata.json",
        "scripts/sync_app_version_metadata.py",
    ):
        record(checks, f"file_{Path(rel).name}", (ROOT / rel).is_file())

    wde = (ROOT / "worldcup_predictor/decision/weighted_decision_engine.py").read_text(encoding="utf-8")
    record(checks, "wde_unchanged", "class WeightedDecisionEngine" in wde)

    layout = (ROOT / "base44-d/src/components/dashboard/DashboardLayout.jsx").read_text(encoding="utf-8")
    record(checks, "header_badge_wired", "AppVersionBadge" in layout)

    owner = (ROOT / "base44-d/src/components/owner/OwnerLayout.jsx").read_text(encoding="utf-8")
    record(checks, "owner_layout_badge", "AppVersionBadge" in owner)

    badge = (ROOT / "base44-d/src/components/layout/AppVersionBadge.jsx").read_text(encoding="utf-8")
    record(checks, "mobile_compact_version", "sm:hidden" in badge and "frontendDisplayShort" in badge)
    record(checks, "owner_detail_popover", "Popover" in badge and "isOwnerUser" in badge)
    record(checks, "public_short_version", "privileged" in badge)

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    fe = (ROOT / "base44-d/src/lib/appVersion.js").read_text(encoding="utf-8")
    for key, const in (
        ("app_version", "APP_VERSION"),
        ("build_label", "BUILD_LABEL"),
        ("build_date", "BUILD_DATE"),
        ("commit", "COMMIT_HASH"),
    ):
        record(checks, f"sync_{key}", f'{const} = "{manifest[key]}"' in fe)

    public_meta = json.loads((ROOT / "base44-d/public/build-metadata.json").read_text(encoding="utf-8"))
    record(checks, "public_build_metadata", public_meta.get("app_version") == manifest["app_version"])

    vite = (ROOT / "base44-d/vite.config.js").read_text(encoding="utf-8")
    record(checks, "vite_version_define", "__APP_VERSION__" in vite)

    try:
        from worldcup_predictor.config.app_version import build_version_payload

        payload = build_version_payload()
        record(checks, "api_payload_fields", all(
            payload.get(k) for k in ("app_version", "build_label", "build_date", "commit", "environment")
        ))
        record(checks, "api_display_full", "display_full" in payload and manifest["build_label"] in payload["display_full"])

        from worldcup_predictor.api.routes.health import version as version_endpoint

        api = version_endpoint()
        record(checks, "version_endpoint", api.get("app_version") == manifest["app_version"])
        record(checks, "version_endpoint_commit", bool(api.get("commit")))
    except Exception as exc:
        record(checks, "runtime_api", False, str(exc))

    passed = sum(1 for _, ok, _ in checks if ok)
    for name, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'} {name} {detail}")

    status = "APP_VERSION_BADGE_DEPLOYED_OK" if passed == len(checks) else "PARTIAL"
    print(f"\n{status} ({passed}/{len(checks)})")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
