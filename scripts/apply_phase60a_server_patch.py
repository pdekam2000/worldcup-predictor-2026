#!/usr/bin/env python3
"""Apply Phase 60A surgical patches on production (App/nav only — no full App.jsx replace)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def patch_app_jsx(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "EliteShadowPreview" in text and "SuperAdminRoute" in text and "/admin/elite-shadow" in text:
        return
    if "import EliteShadowPreview" not in text:
        text = text.replace(
            "import SuperAdminPanel from './pages/SuperAdminPanel';",
            "import SuperAdminPanel from './pages/SuperAdminPanel';\nimport EliteShadowPreview from './pages/EliteShadowPreview';\nimport SuperAdminRoute from './components/SuperAdminRoute';",
        )
    if "/admin/elite-shadow" not in text:
        text = text.replace(
            '          <Route path="/super-admin" element={<SuperAdminPanel />} />',
            '          <Route path="/admin/elite-shadow" element={<SuperAdminRoute><EliteShadowPreview /></SuperAdminRoute>} />\n'
            '          <Route path="/super-admin" element={<SuperAdminPanel />} />',
        )
    path.write_text(text, encoding="utf-8")


def patch_nav(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "/admin/elite-shadow" in text:
        return
    if "Eye," not in text:
        text = text.replace(
            "  Brain,\n\n} from \"lucide-react\";",
            "  Brain,\n\n  Eye,\n\n} from \"lucide-react\";",
        )
    text = text.replace(
        '    { label: "Learning", path: "/admin/learning", icon: Zap, roles: ["admin"] },\n\n    { label: "Super Admin"',
        '    { label: "Learning", path: "/admin/learning", icon: Zap, roles: ["admin"] },\n\n    { label: "Elite Shadow", path: "/admin/elite-shadow", icon: Eye, roles: ["super_admin"] },\n\n    { label: "Super Admin"',
    )
    if 'item.path === "/admin/elite-shadow"' not in text:
        text = text.replace(
            '    if (item.path === "/super-admin") return showSuperAdminNav;\n\n    if (item.path === "/api-settings")',
            '    if (item.path === "/super-admin") return showSuperAdminNav;\n\n    if (item.path === "/admin/elite-shadow") return showSuperAdminNav;\n\n    if (item.path === "/api-settings")',
        )
    path.write_text(text, encoding="utf-8")


def patch_saas_comparison_only(path: Path) -> None:
    """Ensure comparison helper exists; elite-shadow block may already be deployed from 59B tarball."""
    text = path.read_text(encoding="utf-8")
    text = text.replace("{ adminGate: true }", "{ superAdminGate: true }")
    if "fetchAdminEliteShadowComparison" in text:
        path.write_text(text, encoding="utf-8")
        return
    marker = "export async function fetchAdminEliteShadowRootCause"
    block = '''export async function fetchAdminEliteShadowComparison(params = {}) {
  const qs = new URLSearchParams({
    market: params.market || "all",
    tier: params.tier || "all",
    status: params.status || "all",
    disagreement_only: String(Boolean(params.disagreement_only)),
    limit: String(params.limit ?? 200),
    offset: String(params.offset ?? 0),
  });
  if (params.fixture_id != null && params.fixture_id !== "") {
    qs.set("fixture_id", String(params.fixture_id));
  }
  return saasFetch(`/api/admin/elite-shadow/comparison?${qs}`, { superAdminGate: true });
}

'''
    if marker in text:
        text = text.replace(marker, block + marker)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    patch_app_jsx(ROOT / "base44-d/src/App.jsx")
    patch_nav(ROOT / "base44-d/src/lib/navConfig.js")
    patch_saas_comparison_only(ROOT / "base44-d/src/api/saasApi.js")
    print("PATCH_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
