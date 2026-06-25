#!/usr/bin/env python3
"""Apply Phase 59B surgical patches on production (no full App.jsx replace)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def patch_app_jsx(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "EliteShadowPreview" in text:
        return
    text = text.replace(
        "import SuperAdminPanel from './pages/SuperAdminPanel';",
        "import SuperAdminPanel from './pages/SuperAdminPanel';\nimport EliteShadowPreview from './pages/EliteShadowPreview';\nimport SuperAdminRoute from './components/SuperAdminRoute';",
    )
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


def patch_saas(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "fetchAdminEliteShadowSummary" in text:
        # upgrade admin gate -> super admin gate
        text = text.replace("{ adminGate: true }", "{ superAdminGate: true }")
        path.write_text(text, encoding="utf-8")
        return
    marker = "/** Phase 51 — Elite Goal Timing engine */"
    block = '''
/** Phase 59A/59B — Elite Shadow owner preview */
export async function fetchAdminEliteShadowSummary() {
  return saasFetch("/api/admin/elite-shadow/summary", { superAdminGate: true });
}

export async function fetchAdminEliteShadowPredictions(params = {}) {
  const qs = new URLSearchParams({
    market: params.market || "all",
    tier: params.tier || "all",
    status: params.status || "all",
    limit: String(params.limit ?? 50),
    offset: String(params.offset ?? 0),
  });
  return saasFetch(`/api/admin/elite-shadow/predictions?${qs}`, { superAdminGate: true });
}

export async function fetchAdminEliteShadowFixture(fixtureId) {
  return saasFetch(`/api/admin/elite-shadow/predictions/${encodeURIComponent(fixtureId)}`, { superAdminGate: true });
}

export async function fetchAdminEliteShadowEvaluations(params = {}) {
  const qs = new URLSearchParams({
    outcome: params.outcome || "all",
    market: params.market || "all",
    limit: String(params.limit ?? 100),
    offset: String(params.offset ?? 0),
  });
  return saasFetch(`/api/admin/elite-shadow/evaluations?${qs}`, { superAdminGate: true });
}

export async function fetchAdminEliteShadowRootCause(params = {}) {
  const qs = new URLSearchParams({
    market: params.market || "all",
    limit: String(params.limit ?? 100),
    offset: String(params.offset ?? 0),
  });
  if (params.fixture_id != null) qs.set("fixture_id", String(params.fixture_id));
  return saasFetch(`/api/admin/elite-shadow/root-cause?${qs}`, { superAdminGate: true });
}

'''
    text = text.replace(marker, block + marker)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    app = ROOT / "base44-d/src/App.jsx"
    nav = ROOT / "base44-d/src/lib/navConfig.js"
    saas = ROOT / "base44-d/src/api/saasApi.js"
    patch_app_jsx(app)
    patch_nav(nav)
    patch_saas(saas)
    print("PATCH_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
