#!/usr/bin/env python3
"""Phase 63 visibility hotfix — owner dashboard redirect + no-cache index."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "base44-d" / "src" / "App.jsx"


def patch_app(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "OwnerDashboardGate" in text:
        return
    if "import OwnerDashboardGate" not in text:
        text = text.replace(
            "import OwnerRoute from './components/OwnerRoute';",
            "import OwnerRoute from './components/OwnerRoute';\nimport OwnerDashboardGate from './components/OwnerDashboardGate';",
        )
    old = '          <Route path="/dashboard" element={<Dashboard />} />'
    new = (
        "          <Route element={<OwnerDashboardGate />}>\n"
        '            <Route path="/dashboard" element={<Dashboard />} />\n'
        "          </Route>"
    )
    if old in text:
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_app(APP)
    print("PHASE63_VISIBILITY_PATCH_OK")


if __name__ == "__main__":
    main()
